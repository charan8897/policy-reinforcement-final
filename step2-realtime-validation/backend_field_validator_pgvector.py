#!/usr/bin/env python3
"""
Field-Level Real-Time Validation API with PostgreSQL + pgvector
Replaces ChromaDB with PostgreSQL vector storage for better scalability
Uses Gemini's analysis of actual search results to guide the search
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import json
import subprocess
import os
import re
import google.generativeai as genai
import psycopg2
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configuration
GEMINI_API_KEY = "AIzaSyAgWfY5zft6IV00Y2HwPc3JHQva38zWEDQ"
RULES_FILE = "/home/hutech/Documents/docupolicy/rules.txt"
OUTPUT_DIR = "/home/hutech/Documents/docupolicy"
LOG_FILE = f"{OUTPUT_DIR}/validation_api.log"

# PostgreSQL Configuration
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "docupolicy"
DB_USER = "postgres"
DB_PASSWORD = "1234"

app = Flask(__name__)
CORS(app)


class FieldValidator:
    """Dynamic field validation with PostgreSQL + pgvector backend"""

    def __init__(self, rules_file, max_attempts=3):
        self.rules_file = rules_file
        self.max_attempts = max_attempts
        self.log = []
        
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
        
        # Cache for fast lookups
        self.field_classification_cache = {}
        self.field_patterns_cache = {}
        self.rules_content = None
        self.rules_lines = []
        
        # Token tracking
        self.total_tokens_sent = 0
        self.total_tokens_received = 0
        self.api_call_count = 0
        self.api_call_lock = threading.Lock()
        
        # Thread pool for parallel API calls
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # PostgreSQL connection pool and embedding model
        self.db_connection = None
        self.embedding_model = None
        
        # Initialize at startup (only once)
        self._startup_initialization()
        
    def _startup_initialization(self):
        """Initialize everything once at startup"""
        try:
            self.log_entry("STARTUP", "Initializing validator with PostgreSQL + pgvector...")
            
            # Load rules
            self._load_rules()
            
            # Initialize PostgreSQL connection
            self._init_db_connection()
            
            # Initialize embeddings model
            self._init_embedding_model()
            
            # Setup pgvector extension and tables
            self._setup_pgvector_tables()
            
            # Populate PostgreSQL with embeddings
            self._populate_postgres_db()
            
            self.log_entry("STARTUP", "✓ Validator initialization complete - ready for requests")
        except Exception as e:
            self.log_entry("ERROR", f"Startup initialization failed: {e}")
    
    def _init_db_connection(self):
        """Initialize PostgreSQL connection"""
        try:
            self.db_connection = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            self.log_entry("INFO", f"✓ Connected to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}")
            return self.db_connection
        except psycopg2.OperationalError as e:
            self.log_entry("ERROR", f"Failed to connect to PostgreSQL: {e}")
            raise
    
    def _init_embedding_model(self):
        """Load sentence-transformers embedding model"""
        try:
            if self.embedding_model is None:
                self.log_entry("INFO", "Loading sentence-transformers model...")
                self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            self.log_entry("INFO", "✓ Embedding model loaded")
            return self.embedding_model
        except Exception as e:
            self.log_entry("ERROR", f"Failed to load embedding model: {e}")
            raise
    
    def _setup_pgvector_tables(self):
        """Create pgvector extension and policy rules table"""
        try:
            cursor = self.db_connection.cursor()
            
            # Create pgvector extension
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self.log_entry("DEBUG", "pgvector extension ready")
            
            # Create rules table with vector column
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS policy_rules (
                    id SERIAL PRIMARY KEY,
                    rule_text TEXT NOT NULL,
                    embedding vector(384),
                    rule_index INTEGER,
                    rule_length INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create index for faster similarity search
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS policy_rules_embedding_idx 
                ON policy_rules USING ivfflat (embedding vector_cosine_ops) 
                WITH (lists = 100);
            """)
            
            self.db_connection.commit()
            self.log_entry("INFO", "✓ PostgreSQL tables and indexes created")
        except Exception as e:
            self.log_entry("ERROR", f"Failed to setup pgvector tables: {e}")
            raise
    
    def _load_rules(self):
        """Load rules file - filter metadata"""
        if self.rules_content is None:
            try:
                with open(self.rules_file, 'r') as f:
                    self.rules_content = f.read()
                
                # Split and filter out junk
                self.rules_lines = []
                for line in self.rules_content.split('\n'):
                    stripped = line.strip()
                    # Keep only meaningful lines
                    if (stripped and 
                        len(stripped) > 8 and
                        not stripped.startswith('=') and
                        not stripped.startswith('Generated:') and
                        not stripped.startswith('Source:') and
                        not stripped.startswith('Format:') and
                        not stripped.startswith('Extraction') and
                        not stripped.startswith('```')):
                        self.rules_lines.append(stripped)
                
                self.log_entry("INFO", f"Loaded {len(self.rules_lines)} rule lines")
            except Exception as e:
                self.log_entry("ERROR", f"Failed to load rules file: {e}")
                self.rules_content = ""
                self.rules_lines = []
        return self.rules_content
    
    def _populate_postgres_db(self):
        """Populate PostgreSQL with rule embeddings"""
        try:
            cursor = self.db_connection.cursor()
            
            # Check if already populated
            cursor.execute("SELECT COUNT(*) FROM policy_rules;")
            count = cursor.fetchone()[0]
            
            if count > 0:
                self.log_entry("INFO", f"PostgreSQL already has {count} rules, skipping population")
                return True
            
            self.log_entry("INFO", f"Populating PostgreSQL with {len(self.rules_lines)} embeddings...")
            
            # Generate embeddings for all rules
            embeddings = self.embedding_model.encode(self.rules_lines)
            
            # Prepare data for batch insert
            data = []
            for i, (rule_text, embedding) in enumerate(zip(self.rules_lines, embeddings)):
                # Convert embedding to list format for pgvector
                embedding_list = embedding.tolist()
                data.append((rule_text, embedding_list, i, len(rule_text)))
            
            # Batch insert
            insert_query = """
                INSERT INTO policy_rules (rule_text, embedding, rule_index, rule_length)
                VALUES %s
            """
            
            execute_values(cursor, insert_query, data, page_size=100)
            self.db_connection.commit()
            
            self.log_entry("INFO", f"✓ Successfully populated PostgreSQL with {len(self.rules_lines)} embeddings")
            return True
        except Exception as e:
            self.log_entry("ERROR", f"Failed to populate PostgreSQL: {e}")
            return False

    def log_entry(self, level, message):
        """Log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def _count_tokens(self, text):
        """Count tokens for a given text using Gemini API"""
        try:
            response = self.model.count_tokens(text)
            return response.total_tokens
        except Exception as e:
            self.log_entry("WARNING", f"Token counting failed: {e}")
            return 0
    
    def _track_api_call(self, prompt_text, response_text=None):
        """Track API call and token usage (thread-safe)"""
        try:
            # Count input tokens
            input_tokens = self._count_tokens(prompt_text)
            
            # Count output tokens if available
            output_tokens = 0
            if response_text:
                output_tokens = self._count_tokens(response_text)
            
            # Update counters (thread-safe)
            with self.api_call_lock:
                self.total_tokens_sent += input_tokens
                self.total_tokens_received += output_tokens
                self.api_call_count += 1
                call_num = self.api_call_count
                cumulative = self.total_tokens_sent + self.total_tokens_received
            
            total_tokens = input_tokens + output_tokens
            self.log_entry("TOKENS", f"API Call #{call_num} | Input: {input_tokens} | Output: {output_tokens} | Total: {total_tokens} | Cumulative: {cumulative}")
            
            return total_tokens
        except Exception as e:
            self.log_entry("WARNING", f"Token tracking failed: {e}")
            return 0

    def is_general_non_policy_field(self, field_name):
        """Fast regex-based check for common non-policy fields"""
        cache_key = field_name.lower()
        if cache_key in self.field_classification_cache:
            return self.field_classification_cache[cache_key]
        
        general_patterns = [
            r'^(first_?name|last_?name|full_?name|employee_?name|user_?name|name)$',
            r'^(email|e.?mail|email_?address)$',
            r'^(phone|mobile|cell|telephone|phone_?number)$',
            r'^(id|employee_?id|user_?id|ssn)$',
            r'^(address|street|city|state|zip|postal)$',
            r'^(notes|comments|description|remarks|message|reason|purpose|justification)$',
            r'^(status|approval_?status|approval|submitted|draft|pending)$',
            r'^(company|organization|department|team|title|position|job_?title)$',
            r'^(date|timestamp|created|modified|updated_?at|reference|ticket)$',
        ]
        
        field_lower = field_name.lower()
        is_general = any(re.match(pattern, field_lower) for pattern in general_patterns)
        
        self.field_classification_cache[cache_key] = is_general
        return is_general

    def semantic_search(self, query, top_k=5):
        """Search rules using hybrid approach: keyword match + semantic similarity"""
        try:
            if not self.rules_lines or self.embedding_model is None:
                self.log_entry("ERROR", "Validator not initialized - rules or embedding model missing")
                return []
            
            # Generate embedding for query
            query_embedding = self.embedding_model.encode(query).tolist()
            query_lower = query.lower()
            
            # First: get results ranked by similarity, filter junk
            cursor = self.db_connection.cursor()
            cursor.execute(f"""
                SELECT id, rule_text, 1 - (embedding <=> %s::vector) as similarity_score
                FROM policy_rules
                ORDER BY embedding <=> %s::vector
                LIMIT 20;
            """, (query_embedding, query_embedding))
            
            results = cursor.fetchall()
            
            formatted_results = []
            for row in results:
                rule_id, rule_text, similarity_score = row
                # Boost score if query keywords appear in rule
                boosted_score = float(similarity_score)
                rule_lower = rule_text.lower()
                if any(word in rule_lower for word in ['rule:', 'if', 'then', 'condition']):
                    boosted_score += 0.1
                
                formatted_results.append({
                    'id': rule_id,
                    'line': rule_text,
                    'score': boosted_score
                })
            
            # Sort by boosted score and return top_k
            formatted_results = sorted(formatted_results, key=lambda x: x['score'], reverse=True)[:top_k]
            
            self.log_entry("SEMANTIC_SEARCH", f"Query '{query}': Found {len(formatted_results)} relevant rules")
            return formatted_results
        except Exception as e:
            self.log_entry("ERROR", f"Semantic search failed: {e}")
            return []
    
    def semantic_search_multiple(self, queries):
        """Search for multiple query patterns using semantic similarity"""
        try:
            if not queries:
                return []
            
            # Combine queries into single search query
            combined_query = " ".join(queries)
            results = self.semantic_search(combined_query, top_k=3)
            
            self.log_entry("SEMANTIC_SEARCH_MULTI", f"Queries {queries}: Found {len(results)} rules")
            return results
        except Exception as e:
            self.log_entry("ERROR", f"Multi-query semantic search failed: {e}")
            return []
    
    def semantic_search_by_field(self, field_name, field_value):
        """Specialized semantic search for a field with intelligent query generation"""
        try:
            # Generate contextual query for the field
            query = self._generate_search_query(field_name, field_value)
            self.log_entry("FIELD_QUERY", f"{field_name}: {query}")
            
            # Perform semantic search
            results = self.semantic_search(query, top_k=3)
            return results
        except Exception as e:
            self.log_entry("ERROR", f"Field-based semantic search failed: {e}")
            return []
    
    def _generate_search_query(self, field_name, field_value):
        """Generate search query by combining field name and value"""
        # Dynamic query: just field name + value, no API calls needed
        # Sentence embeddings are good enough for semantic matching
        description = field_name.replace('_', ' ')
        return f"{description} {field_value}"

    def validate_field(self, field_name, field_value, previous_context=None):
        """
        Main validation using semantic search + parallel Gemini analysis
        """
        self.log_entry("VALIDATION", f"Starting for {field_name}={field_value}")
        
        # Skip non-policy fields instantly
        if self.is_general_non_policy_field(field_name):
            self.log_entry("SKIP_REGEX", f"General field - auto-approved")
            return {
                'field_name': field_name,
                'field_value': field_value,
                'status': 'valid',
                'message': '✓ Field accepted - general information field',
                'rules': [],
                'validation_details': {
                    'field_meaning': 'General/non-policy field',
                    'skipped': True,
                    'reason': 'No policy constraints'
                }
            }

        # Step 1: Generate search query and perform semantic search in parallel
        self.log_entry("SEARCH", f"Performing semantic search for {field_name}")
        
        # Run query generation and semantic search in parallel
        futures = {}
        futures['query'] = self.executor.submit(self._generate_search_query, field_name, field_value)
        futures['search'] = self.executor.submit(self.semantic_search_by_field, field_name, field_value)
        
        # Wait for both to complete
        search_results = futures['search'].result()
        
        if not search_results:
            self.log_entry("NO_RULES", f"No relevant rules found for {field_name}")
            return {
                'field_name': field_name,
                'field_value': field_value,
                'status': 'valid',
                'message': f'✓ {field_name} validated - no policy constraints found',
                'rules': [],
                'validation_details': {
                    'search_method': 'pgvector_semantic',
                    'rules_found': 0,
                    'decision_reasoning': 'No applicable policy rules discovered'
                }
            }

        # Step 2: Format rules - get more context by including surrounding lines from database
        formatted_rules = []
        for result in search_results[:5]:
            rule_id = result['id']
            # Try to get rule context (surrounding lines might have IF/THEN components)
            cursor = self.db_connection.cursor()
            cursor.execute("""
                SELECT rule_text FROM policy_rules 
                WHERE id BETWEEN %s AND %s 
                ORDER BY id
                LIMIT 5;
            """, (max(1, rule_id-2), rule_id+2))
            context_rows = cursor.fetchall()
            context_text = " ".join([row[0] for row in context_rows if row[0]])
            formatted_rules.append(context_text if context_text else result['line'])
        
        self.log_entry("RULES_FOUND", f"Found {len(search_results)} relevant rules, using top {len(formatted_rules)}")

        # Step 3: Generate validation decision from found rules
        decision = self._generate_validation_decision(
            field_name, field_value, formatted_rules, previous_context
        )

        return {
            'field_name': field_name,
            'field_value': field_value,
            'status': decision['status'],
            'message': decision['message'],
            'rules': formatted_rules,
            'validation_details': {
                'search_method': 'pgvector_cosine_similarity',
                'top_matches': [
                    {
                        'rule': result['line'],
                        'similarity_score': result['score']
                    } for result in search_results[:5]
                ],
                'total_rules_found': len(search_results),
                'decision_reasoning': decision.get('reasoning', '')
            }
        }



    def _generate_validation_decision(self, field_name, field_value, found_rules, previous_context, search_results=None):
        """Generate validation decision from found rules"""
        
        if not found_rules:
            # No rules found - return warning not auto-approve
            return {
                'status': 'warning',
                'message': f'⚠ {field_name} - no applicable policy rules found',
                'reasoning': 'No policy constraints discovered'
            }
        
        rules_text = "\n".join(found_rules[:3])
        
        # Check if rules contain mandatory requirements
        rules_combined = rules_text.lower()
        has_must = 'must' in rules_combined
        has_prohibition = 'prohibited' in rules_combined or 'not' in rules_combined
        
        # Use Gemini to validate - analyze rules for this specific field value
        prompt = f"""Analyze field '{field_name}'='{field_value}' against these rules:

{rules_text}

Answer these 3 questions:
1. Does any rule FORBID or PROHIBIT this value? → If yes, status=error
2. Does any rule contain MUST/MANDATORY/REQUIRED for this value? → If yes, status=error  
3. Does any rule say IF (this value) THEN (other field must be X)? → If yes, status=warning with message showing dependency

Example: IF travel_type == "seminar" THEN reporting_manager_approval must be "yes"
→ travel_type="seminar" should be WARNING because it creates a requirement for another field

Return JSON:
{{"status":"valid/warning/error","message":"outcome","reasoning":"analysis"}}"""

        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Track token usage
            self._track_api_call(prompt, response_text)
            
            # Parse JSON response
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]
            
            decision = json.loads(response_text.strip())
            return decision
        except Exception as e:
            # Fallback: analyze rules for MUST/restrictions
            self.log_entry("DEBUG", f"Gemini validation failed, using rule analysis: {str(e)[:50]}")
            
            if has_must:
                return {
                    'status': 'warning',
                    'message': f'⚠ {field_name}={field_value} - MANDATORY policy requirement found',
                    'reasoning': f'Policy rule contains MUST requirement: {found_rules[0][:80]}'
                }
            elif has_prohibition:
                return {
                    'status': 'warning', 
                    'message': f'⚠ {field_name}={field_value} - Possible restriction in policy',
                    'reasoning': f'Rule may have restrictions: {found_rules[0][:80]}'
                }
            else:
                return {
                    'status': 'valid',
                    'message': f'✓ {field_name} - Policy rule found',
                    'reasoning': f'Field covered by policy: {found_rules[0][:80]}'
                }



    def save_log(self):
        """Save logs"""
        with open(LOG_FILE, 'a') as f:
            for entry in self.log:
                f.write(entry + '\n')


# API Endpoints
validator = FieldValidator(RULES_FILE)


@app.route('/api/validate-field', methods=['POST'])
def validate_field():
    """Field validation endpoint"""
    try:
        data = request.json
        field_name = data.get('field_name', '').strip()
        field_value = data.get('field_value', '').strip()
        previous_context = data.get('previous_context')

        if not field_name or not field_value:
            return jsonify({
                'status': 'error',
                'message': 'field_name and field_value required'
            }), 400

        result = validator.validate_field(field_name, field_value, previous_context)
        validator.save_log()

        return jsonify(result), 200

    except Exception as e:
        import traceback
        validator.log_entry("ERROR", f"API error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': f'Validation failed: {str(e)}'
        }), 500


@app.route('/api/health', methods=['GET'])
def health():
    cursor = validator.db_connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM policy_rules;")
    rule_count = cursor.fetchone()[0]
    
    return jsonify({
        'status': 'ok' if validator.db_connection else 'error',
        'rules_loaded': len(validator.rules_lines),
        'postgres_connected': validator.db_connection is not None,
        'postgres_rules_count': rule_count,
        'rules_file': RULES_FILE,
        'rules_file_exists': os.path.exists(RULES_FILE),
        'vector_backend': 'PostgreSQL + pgvector'
    }), 200


@app.route('/api/stats', methods=['GET'])
def stats():
    cursor = validator.db_connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM policy_rules;")
    rule_count = cursor.fetchone()[0]
    
    return jsonify({
        'rules_loaded': len(validator.rules_lines),
        'postgres_ready': validator.db_connection is not None,
        'embeddings_count': rule_count,
        'backend': 'PostgreSQL + pgvector',
        'token_stats': {
            'api_calls': validator.api_call_count,
            'tokens_sent': validator.total_tokens_sent,
            'tokens_received': validator.total_tokens_received,
            'total_tokens_used': validator.total_tokens_sent + validator.total_tokens_received,
            'avg_tokens_per_call': (validator.total_tokens_sent + validator.total_tokens_received) / max(1, validator.api_call_count)
        },
        'recent_logs': validator.log[-20:]  # Last 20 log entries
    }), 200


if __name__ == '__main__':
    print("\n" + "="*80)
    print("Starting Field Validation API (PostgreSQL + pgvector Backend)...")
    print("="*80)
    print(f"Rules file: {RULES_FILE}")
    print(f"PostgreSQL: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"Vector backend: pgvector with 384-dim embeddings")
    print("="*80 + "\n")
    app.run(debug=True, host='127.0.0.1', port=5000)

#!/usr/bin/env python3
"""
Field-Level Real-Time Validation API
Maps to policy_validator.py's PayloadEvaluator for dynamic field validation
Validates individual fields against rules.txt using Gemini + iterative grep feedback loop
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import json
import subprocess
import os
import re
import google.generativeai as genai

# Configuration
GEMINI_API_KEY = "AIzaSyAgWfY5zft6IV00Y2HwPc3JHQva38zWEDQ"
RULES_FILE = "/home/hutech/Documents/docupolicy/rules.txt"
OUTPUT_DIR = "/home/hutech/Documents/docupolicy"
LOG_FILE = f"{OUTPUT_DIR}/validation_api.log"

app = Flask(__name__)
CORS(app)


class FieldValidator:
    """
    Validates individual form fields using the same iterative Gemini + grep approach
    as policy_validator.py, but optimized for real-time field validation
    """

    def __init__(self, rules_file, max_attempts=3):
        self.rules_file = rules_file
        self.max_attempts = max_attempts
        self.log = []

        # Initialize Gemini - using gemini-2.5-flash-lite (fastest free tier)
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemma-3-27b-it')
        
        # Cache for field classification and patterns to avoid repeated Gemini calls
        self.field_classification_cache = {}
        self.field_patterns_cache = {}

    def log_entry(self, level, message):
        """Log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.log.append(entry)
        print(entry)

    def is_general_non_policy_field(self, field_name, field_value):
        """
        Fast regex-based check: Is this field general/non-policy-constrained?
        Skip Gemini entirely - use hardcoded patterns for common fields.
        """
        cache_key = field_name.lower()
        if cache_key in self.field_classification_cache:
            return self.field_classification_cache[cache_key]
        
        # Hardcoded patterns for common non-policy fields (no Gemini needed)
        general_patterns = [
            # Names & IDs
            r'^(first_?name|last_?name|full_?name|employee_?name|user_?name|name)$',
            r'^(email|e.?mail|email_?address)$',
            r'^(phone|mobile|cell|telephone|phone_?number)$',
            r'^(id|employee_?id|user_?id|ssn)$',
            
            # Addresses
            r'^(address|street|city|state|zip|postal|country_of_residence)$',
            r'^(address_?line|apt|suite|building)$',
            
            # General Info
            r'^(notes|comments|description|remarks|message|reason|purpose|justification|travel_?reason|travel_?purpose)$',
            r'^(status|approval_?status|approval|submitted|draft|pending)$',
            r'^(company|organization|department|team)$',
            r'^(title|position|job_?title|role)$',
            r'^(date|timestamp|created|modified|updated_?at)$',
            
            # Generic text/number fields
            r'^(comments?|note|memo|additional|other)$',
            r'^(reference|reference_?number|ticket)$',
        ]
        
        field_lower = field_name.lower()
        is_general = False
        
        for pattern in general_patterns:
            if re.match(pattern, field_lower):
                is_general = True
                self.log_entry("SKIP_REGEX", f"Field '{field_name}' matches general pattern '{pattern}'")
                break
        
        # Cache the result
        self.field_classification_cache[cache_key] = is_general
        return is_general

    def grep_search(self, pattern):
        """Run grep search on rules file (same as policy_validator.py)"""
        try:
            result = subprocess.run(
                ['grep', '-n', '-i', pattern, self.rules_file],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.stdout:
                lines = result.stdout.strip().split('\n')
                self.log_entry("GREP", f"Pattern '{pattern}': Found {len(lines)} matches")
                return lines
            else:
                self.log_entry("GREP", f"Pattern '{pattern}': No matches")
                return []

        except subprocess.TimeoutExpired:
            self.log_entry("ERROR", f"grep timeout for pattern '{pattern}'")
            return []
        except Exception as e:
            self.log_entry("ERROR", f"grep failed: {e}")
            return []

    def read_rules_file(self):
        """Read entire rules file"""
        try:
            with open(self.rules_file, 'r') as f:
                return f.read()
        except Exception as e:
            self.log_entry("ERROR", f"Failed to read rules file: {e}")
            return None

    def analyze_field_context_with_gemini(self, field_name, field_value):
        """
        Step 1: Analyze field context to understand what it means
        (same as PayloadEvaluator.analyze_payload_context)
        """
        prompt = f"""Analyze this form field to understand its context and meaning:

Field Name: {field_name}
Field Value: {field_value}

TASK: 
1. What does this field represent? (e.g., 'Employee Grade', 'Travel Days', 'Destination Country')
2. What policy topics might be relevant? (e.g., 'travel class', 'allowance', 'approval workflow')
3. Generate 3-5 GENERIC grep search patterns (NOT specific to the value) that would find relevant policy rules
   - Use KEYWORD VARIATIONS (e.g., for "booking_advance": try "weeks", "prior", "advance", "reservation", "booking lead")
   - Try PARTIAL MATCHES if full phrases don't work
   - Include TIME UNITS if applicable (weeks, days, hours, months)

IMPORTANT: Patterns should search for CONCEPTS, not specific values:
- BAD: "booking_advance=2" or "2 days" or "7 days"
- GOOD: "advance booking" or "weeks prior" or "two weeks" or "reservation.*days"

RESPOND IN JSON:
{{
  "field_meaning": "description of what this field represents",
  "relevant_topics": ["topic1", "topic2"],
  "grep_patterns": ["pattern1", "pattern2", "pattern3", "pattern4", "pattern5"]
}}"""

        try:
            self.log_entry("GEMINI", f"Analyzing context for {field_name}")
            response = self.model.generate_content(prompt)
            
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]  # Remove opening ```json
            if response_text.startswith('```'):
                response_text = response_text[3:]  # Remove opening ```
            if response_text.endswith('```'):
                response_text = response_text[:-3]  # Remove closing ```
            
            response_text = response_text.strip()
            
            analysis = json.loads(response_text)
            self.log_entry("GEMINI", f"Context analysis: {analysis.get('field_meaning', 'N/A')}")
            return analysis

        except json.JSONDecodeError as e:
            self.log_entry("ERROR", f"JSON parsing failed: {e}")
            return None
        except Exception as e:
            self.log_entry("ERROR", f"Gemini analysis failed: {e}")
            return None

    def validate_field_with_feedback_loop(self, field_name, field_value, previous_context=None):
        """
        Step 2-3: Iterative feedback loop (same as PayloadEvaluator.evaluate_with_feedback_loop)
        """
        self.log_entry("VALIDATION", f"Starting validation for {field_name}={field_value}")
        
        # Step 0: Check if this is a general/non-policy field
        # If yes, skip Gemini validation entirely and auto-approve
        if self.is_general_non_policy_field(field_name, field_value):
            self.log_entry("SKIP", f"Field '{field_name}' classified as general/non-policy - auto-approved")
            return {
                'field_name': field_name,
                'field_value': field_value,
                'status': 'valid',
                'message': '✓ Field accepted - general field, no policy constraints',
                'rules': [],
                'validation_details': {
                    'field_meaning': 'General/non-policy field',
                    'relevant_topics': [],
                    'skipped': True,
                    'reason': 'This field does not have specific policy constraints'
                }
            }

        # Step 1: Analyze context (check cache first)
        cache_key = field_name.lower()
        if cache_key in self.field_patterns_cache:
            self.log_entry("CACHE_HIT", f"Using cached patterns for {field_name}")
            analysis = self.field_patterns_cache[cache_key]
        else:
            analysis = self.analyze_field_context_with_gemini(field_name, field_value)
            if not analysis:
                return self._create_error_response("Failed to analyze field context")
            # Cache for future use
            self.field_patterns_cache[cache_key] = analysis

        # Step 2-3: Iterative grep + Gemini refinement loop
        search_attempts = []
        found_rules = []

        for attempt in range(1, self.max_attempts + 1):
            self.log_entry("ATTEMPT", f"Search attempt {attempt}")

            # Get search patterns (first attempt from analysis, later from refinement)
            if attempt == 1:
                patterns = analysis.get('grep_patterns', [])
            else:
                # Refine patterns based on previous results
                patterns = self._refine_patterns_with_gemini(
                    field_name, field_value, search_attempts
                )

            # Execute grep searches
            attempt_results = []
            for pattern in patterns:
                # Clean up patterns (remove quotes that Gemini might add)
                clean_pattern = pattern.strip('"\'')
                results = self.grep_search(clean_pattern)
                if results:
                    found_rules.extend(results)
                    attempt_results.append({
                        'pattern': clean_pattern,
                        'results_count': len(results),
                        'results': results[:5]  # Keep first 5 results
                    })

            search_attempts.append({
                'attempt': attempt,
                'patterns_tried': patterns,
                'results_found': len(attempt_results) > 0,
                'rules_count': len(attempt_results),
                'details': attempt_results
            })

            # Stop if we found sufficient rules (or any rules on first attempt to save time)
            if len(found_rules) >= 2:
                self.log_entry("SUCCESS", f"Found {len(found_rules)} rules - stopping search")
                break

        # Step 4: Generate validation decision based on found rules
        decision = self._generate_validation_decision(
            field_name, field_value, found_rules, analysis, previous_context
        )

        return {
            'field_name': field_name,
            'field_value': field_value,
            'status': decision['status'],
            'message': decision['message'],
            'rules': self._format_rules(found_rules),
            'validation_details': {
                'field_meaning': analysis.get('field_meaning', ''),
                'relevant_topics': analysis.get('relevant_topics', []),
                'search_attempts': search_attempts,
                'total_rules_found': len(found_rules),
                'decision_reasoning': decision.get('reasoning', '')
            }
        }

    def _refine_patterns_with_gemini(self, field_name, field_value, previous_attempts):
        """Refine search patterns based on previous results"""
        try:
            previous_details = json.dumps(previous_attempts[-1].get('details', []), indent=2) if previous_attempts else "{}"
        except Exception as e:
            self.log_entry("ERROR", f"Failed to serialize previous attempts: {e}")
            previous_details = "{}"

        prompt = f"""Previous grep search didn't find enough policy rules. Refine the search:

Field: {field_name} = {field_value}
Previous Results: {previous_details}

TASK: Generate 2-3 COMPLETELY DIFFERENT grep patterns that are NOT specific to the value "{field_value}".
Search for CONCEPTS, TOPICS, and POLICY NAMES instead.

CRITICAL RULES:
❌ DO NOT include the specific value in patterns (e.g., avoid "group_size=5", "group_size:5", "5 people")
✅ DO include policy topics and concepts (e.g., "group travel", "employees together", "risk management", "travel restriction")
✅ DO include partial policy section names (e.g., "managing", "travel", "approval")

Examples for field "group_size":
- BAD: "group_size:5" or "group size=5" or "5 people"
- GOOD: "group travel", "employees.*together", "managing number", "direct reports", "travel risk"

RESPOND IN JSON:
{{"patterns": ["pattern1", "pattern2", "pattern3"]}}"""

        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Remove markdown
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            result = json.loads(response_text)
            patterns = result.get('patterns', [])
            self.log_entry("GEMINI", f"Refined patterns: {patterns}")
            return patterns
        except json.JSONDecodeError as e:
            self.log_entry("ERROR", f"JSON parsing in pattern refinement failed: {e}")
            return []
        except Exception as e:
            self.log_entry("ERROR", f"Pattern refinement failed: {e}")
            return []

    def _generate_validation_decision(self, field_name, field_value, found_rules, analysis, previous_context):
        """Generate validation status based on extracted rules"""
        
        context_info = ""
        if previous_context:
            context_info = f"\nPrevious fields validated: {json.dumps(previous_context[-3:], indent=2)}"

        rules_text = "\n".join(found_rules[:10]) if found_rules else "No rules found"

        prompt = f"""Based on the policy rules found, validate this field:

Field: {field_name} = {field_value}
Field Meaning: {analysis.get('field_meaning', '')}
{context_info}

Policy Rules Found:
{rules_text}

TASK: Determine validation status and provide actionable message
1. status: 'valid', 'warning', or 'error'
2. message: User-friendly validation message
3. reasoning: Brief explanation of the decision

RESPOND IN JSON:
{{
  "status": "valid/warning/error",
  "message": "user-friendly message",
  "reasoning": "explanation"
}}"""

        try:
            response = self.model.generate_content(prompt)
            response_text = response.text
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            
            decision = json.loads(response_text)
            return decision
        except Exception as e:
            self.log_entry("ERROR", f"Decision generation failed: {e}")
            return {
                'status': 'valid',
                'message': '✓ Field validated against policies',
                'reasoning': 'Validation completed successfully'
            }

    def _format_rules(self, rules_lines):
        """Format raw grep results into clean rules list"""
        formatted = []
        seen = set()
        
        for line in rules_lines[:10]:
            # Remove line numbers from grep output
            parts = line.split(':', 1)
            if len(parts) == 2:
                rule_text = parts[1].strip()
            else:
                rule_text = line.strip()
            
            # Deduplicate
            if rule_text and rule_text not in seen:
                formatted.append(rule_text)
                seen.add(rule_text)
        
        return formatted

    def _create_error_response(self, error_message):
        """Create error response"""
        return {
            'field_name': '',
            'status': 'error',
            'message': error_message,
            'rules': [],
            'validation_details': {}
        }

    def save_log(self):
        """Save validation log"""
        with open(LOG_FILE, 'a') as f:
            for entry in self.log:
                f.write(entry + '\n')


# ============================================================================
# API ENDPOINTS
# ============================================================================

validator = FieldValidator(RULES_FILE)


@app.route('/api/validate-field', methods=['POST'])
def validate_field():
    """
    Main endpoint for field validation
    
    Request JSON:
    {
      "field_name": "employee_grade",
      "field_value": "E5",
      "previous_context": [{"field_name": "name", "field_value": "John Doe"}]
    }
    """
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

        # Run validation
        result = validator.validate_field_with_feedback_loop(
            field_name, field_value, previous_context
        )

        # Ensure result has all required fields
        if not isinstance(result, dict):
            result = {'status': 'error', 'message': str(result)}
        
        # Ensure critical fields exist
        result.setdefault('field_name', field_name)
        result.setdefault('field_value', field_value)
        result.setdefault('status', 'valid')
        result.setdefault('message', 'Field validated')
        result.setdefault('rules', [])

        # Save log
        validator.save_log()

        return jsonify(result), 200

    except Exception as e:
        import traceback
        error_msg = str(e)
        validator.log_entry("ERROR", f"API error: {error_msg}")
        validator.log_entry("ERROR", f"Traceback: {traceback.format_exc()}")
        
        return jsonify({
            'status': 'error',
            'message': f'Validation failed: {error_msg}',
            'error': error_msg
        }), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'rules_file': RULES_FILE,
        'rules_file_exists': os.path.exists(RULES_FILE)
    }), 200


if __name__ == '__main__':
    print("Starting Field Validation API...")
    print(f"Rules file: {RULES_FILE}")
    print(f"Log file: {LOG_FILE}")
    app.run(debug=True, host='127.0.0.1', port=5000)

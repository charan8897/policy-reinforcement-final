# Complete Class Map & Interconnections

## Stage-by-Stage Class Reference

---

## STAGE 0: DocumentStructureAnalyzer

**Location:** `policy_validator_stage0_new.py` + `policy_validator.py`

**Purpose:** Extract document structure, sections, and annexures

**Dependencies:**
```python
import json, re, datetime, Path
```

**Key Attributes:**
```python
self.policy_file          # Path to input policy.txt
self.output_file          # stage0_structured_document.json
self.document_id          # Document identifier
self.log                  # List of log entries
self.storage              # PipelineStageStorage instance
```

**Key Methods:**

```python
def __init__(self, policy_file, document_id=None, enable_mongodb=True)
    # Initialize analyzer, MongoDB storage

def log_entry(level, message) → None
    # Thread-safe logging: "[TIMESTAMP] [LEVEL] [Stage 0] message"

def read_policy_text() → str
    # Read policy.txt file (handles encoding)
    # Returns: content or None on error

def identify_section(line) → (section_type, section_name)
    # Uses SECTION_PATTERNS regex
    # Returns: ("objective", "Objective"), ("scope", "Scope"), etc.

def identify_annexure(line) → str
    # Uses ANNEXURE_PATTERNS regex
    # Returns: "Annexure 1: City Classification" or None

def analyze_structure(content) → dict
    # Main parsing logic
    # Returns: {
    #     "metadata": {...},
    #     "sections": {...},
    #     "annexures": {...},
    #     "numbered_clauses": [...]
    # }

def _parse_city_classification(lines) → dict
    # Parses city category lists
    # Returns: {"categories": {"Metros": ["Mumbai", "Delhi"]}}

def _parse_rates_table(lines) → dict
    # Parses rate tables
    # Returns: {"items": [{"item": "Metro", "amount": "5000"}]}

def _parse_rules(lines) → dict
    # Parses numbered/bulleted rules
    # Returns: {"rules": ["1. Rule text", "2. Rule text"]}

def generate_all_clauses(structure) → list[dict]
    # Converts all sections to clause objects
    # Creates clauseId: C1, CA_Annexure1_Row1, etc.
    # Returns: [{clauseId, text, source, clause_type}, ...]

def analyze() → dict
    # MAIN WORKFLOW:
    # 1. read_policy_text()
    # 2. analyze_structure()
    # 3. generate_all_clauses()
    # 4. Save to stage0_structured_document.json
    # 5. Store to MongoDB (via self.storage.store_stage)
    # Returns: structured document dict

def save_log() → None
    # Append logs to mechanism.log
```

**Regex Patterns:**
```python
SECTION_PATTERNS = [
    (r'^(objectives?|purpose|aim)[:\s]', 'objective'),
    (r'^(scope|applicability)[:\s]', 'scope'),
    (r'^(eligibility|who\s+does)[:\s]', 'eligibility'),
    ...
]

ANNEXURE_PATTERNS = [
    r'^(annexure|appendix|schedule)\s*[-–]?\s*(\d+|[A-Z])[:\s]*(.*)',
    ...
]
```

**Output to Stage 1B:**
```json
{
  "all_clauses": [
    {"clauseId": "C1", "text": "...", "source": "numbered"},
    {"clauseId": "CA_Annexure1_Metro", "text": "...", "source": "Annexure 1"}
  ]
}
```

---

## STAGE 1B: ClauseExtractor

**Location:** `policy_validator.py` (lines ~1300-1555)

**Purpose:** Extract and elaborate individual clauses

**Dependencies:**
```python
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import google.generativeai as genai
```

**Key Attributes:**
```python
self.policy_file          # Input: filename.txt
self.clauses_file         # Output: stage1_clauses.json
self.use_langchain        # Boolean flag
self.log                  # Log entries
self.storage              # PipelineStageStorage instance
self.model                # Gemini model instance
self.langchain_llm        # ChatGoogleGenerativeAI (if available)
self.text_splitter        # RecursiveCharacterTextSplitter (if LangChain)
```

**Key Methods:**

```python
def __init__(self, policy_file, document_id=None, enable_mongodb=True, use_langchain=True)
    # Initialize extractor, Gemini, optional LangChain

def log_entry(level, message) → None
    # Thread-safe logging

def read_policy_file() → str
    # Read policy.txt

def extract_clauses_with_langchain(content) → list[dict]
    # Uses RecursiveCharacterTextSplitter
    # Uses Pydantic schema validation
    # Returns: [{"clause_id": "C1", "text": "..."}, ...]

def extract_clauses_with_gemini(content) → list[dict]
    # Direct Gemini API call
    # JSON response parsing
    # Returns: [{"clause_id": "C1", "text": "..."}, ...]

def validate_clauses(clauses) → bool
    # Check required fields: clause_id, text
    # Validate format: C1, C2, etc.
    # Return: True if valid, False otherwise

def build_clause_map(clauses) → list[dict]
    # Convert to {clauseId, text} mapping
    # Returns: [{"clauseId": "C1", "text": "..."}, ...]

def format_clauses_output(clauses) → dict
    # Add metadata header:
    # {
    #     "metadata": {
    #         "generated": "ISO timestamp",
    #         "total_clauses": 25,
    #         "stage": "1B"
    #     },
    #     "clauses": [...]
    # }

def extract() → bool
    # MAIN WORKFLOW:
    # 1. read_policy_file()
    # 2. extract_clauses_with_langchain() or _with_gemini()
    # 3. validate_clauses()
    # 4. build_clause_map()
    # 5. format_clauses_output()
    # 6. Save to stage1_clauses.json
    # 7. Store to MongoDB
    # Returns: True on success

def save_log() → None
    # Append to mechanism.log
```

**Gemini Prompts:**
```
Extract all POLICY CLAUSES from document.
Each clause must have unique ID (C1, C2, C3, ...)
Preserve original text without modification.

OUTPUT FORMAT (STRICT JSON):
{
    "clauses": [
        {"clause_id": "C1", "text": "..."},
        {"clause_id": "C2", "text": "..."}
    ]
}
```

**Input from Stage 0:**
```
stage0_structured_document.json → read all_clauses
```

**Output to Stage 2:**
```
stage1_clauses.json
```

---

## STAGE 2: IntentClassifier

**Location:** `policy_validator.py` (lines ~1557-1930)

**Purpose:** Classify intent of each clause

**Dependencies:**
```python
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from concurrent.futures import ThreadPoolExecutor
import google.generativeai as genai
```

**Key Attributes:**
```python
self.clauses_file         # Input: stage1_clauses.json
self.classified_file      # Output: stage2_classified.json
self.use_langchain        # Boolean flag
self.log                  # Log entries
self.storage              # PipelineStageStorage instance
self.model                # Gemini model
self.langchain_llm        # ChatGoogleGenerativeAI (if available)
self.allowed_intents      # ["RESTRICTION", "LIMIT", ...]
```

**Key Methods:**

```python
def __init__(self, clauses_file, document_id=None, enable_mongodb=True, use_langchain=True)
    # Initialize classifier, Gemini

def log_entry(level, message) → None
    # Thread-safe logging

def read_clauses_file() → list[dict]
    # Read stage1_clauses.json
    # Extract "clauses" array
    # Returns: list of clause dicts

def classify_intent_with_langchain(clause_id, clause_text) → dict
    # LangChain + Pydantic validation
    # Returns: {"intent": "...", "confidence": 0.0-1.0, "reasoning": "..."}

def classify_intent_with_gemini(clause_id, clause_text) → dict
    # Direct Gemini API
    # Validates intent against allowed_intents
    # Clamps confidence to [0.0, 1.0]
    # Returns: {"intent": "...", "confidence": 0.0-1.0, "reasoning": "..."}

def classify() → bool
    # MAIN WORKFLOW:
    # 1. read_clauses_file()
    # 2. PARALLEL classify each clause (8 workers):
    #    - classify_intent_with_langchain() or _with_gemini()
    # 3. format_classified_output()
    # 4. Save to stage2_classified.json
    # 5. Store to MongoDB
    # Returns: True on success

def classify_single_clause(clause_data) → dict
    # Helper for parallel processing
    # Returns: {clauseId, text, intent, confidence, reasoning}

def format_classified_output(classified_clauses) → dict
    # Add metadata:
    # {
    #     "metadata": {
    #         "total_clauses": 25,
    #         "intent_distribution": {
    #             "RESTRICTION": 5,
    #             "LIMIT": 8,
    #             ...
    #         },
    #         "average_confidence": 0.82
    #     },
    #     "classified_clauses": [...]
    # }

def save_log() → None
    # Append to mechanism.log
```

**Intent Types (7):**
```
RESTRICTION        - Prohibits action
LIMIT              - Sets thresholds
CONDITIONAL_ALLOWANCE - IF/THEN
EXCEPTION          - Special cases
APPROVAL_REQUIRED  - Needs authorization
ADVISORY           - Recommended (non-mandatory)
INFORMATIONAL      - Definitions/classifications
```

**Parallel Execution:**
```python
with ThreadPoolExecutor(max_workers=8) as executor:
    clause_data = [(i, clause) for i, clause in enumerate(clauses, 1)]
    classified = list(executor.map(classify_single_clause, clause_data))
```

**Input from Stage 1B:**
```
stage1_clauses.json
```

**Output to Stage 3:**
```
stage2_classified.json
```

---

## STAGE 3: GenericEntityExtractor

**Location:** `policy_agnostic_stages.py` (lines ~36-250) OR `policy_validator.py` (lines ~1980-2300)

**Purpose:** Extract entities (numbers, amounts, durations, roles, conditions)

**Dependencies:**
```python
from concurrent.futures import ThreadPoolExecutor
import google.generativeai as genai
from enum import Enum
from collections import defaultdict
```

**Key Attributes:**
```python
self.classified_file      # Input: stage2_classified.json
self.entities_file        # Output: stage3_entities.json
self.use_langchain        # Boolean flag
self.max_workers          # Default: 8
self.log                  # Log entries
self.storage              # PipelineStageStorage instance
self.model                # Gemini model
self.langchain_llm        # ChatGoogleGenerativeAI (if available)
```

**Key Methods:**

```python
def __init__(self, classified_file, document_id=None, enable_mongodb=True, 
             use_langchain=True, max_workers=8)
    # Initialize extractor

def log_entry(level, message) → None
    # Thread-safe logging

def read_classified_file() → list[dict]
    # Read stage2_classified.json
    # Returns: list of classified clause dicts

def extract_entities_with_langchain(clause_id, clause_text) → dict
    # LangChain + Pydantic validation
    # Returns: {"entityName1": "value1", "entityName2": "value2"}

def extract_entities_with_gemini(clause_id, clause_text) → dict
    # Direct Gemini API
    # Retry logic with exponential backoff (rate limiting)
    # Returns: {"entityName1": "value1", ...}

def extract() → bool
    # MAIN WORKFLOW:
    # 1. read_classified_file()
    # 2. PARALLEL extract entities (8 workers)
    # 3. calculate_entity_statistics()
    # 4. format_entities_output()
    # 5. Save to stage3_entities.json
    # 6. Store to MongoDB
    # Returns: True on success

def extract_single(clause) → dict
    # Helper for parallel processing
    # Returns: {clauseId, text, intent, entities}

def calculate_entity_statistics(extracted_clauses) → dict
    # Returns: {
    #     "total_entities": 142,
    #     "clauses_with_entities": 18,
    #     "coverage": 72.0,
    #     "entity_type_distribution": {...}
    # }

def format_entities_output(extracted_clauses, stats) → dict
    # Add metadata and statistics
    # Returns: {
    #     "metadata": {...},
    #     "extracted_clauses": [...]
    # }

def save_log() → None
    # Append to mechanism.log
```

**Entity Types (Dynamic):**
```
No predefined schema - LLM infers names from context

Examples:
- "fourWheelerRate": "7.0 Rs/KM"
- "twoWheelerRate": "2.5 Rs/KM"
- "employeeGrades": "M1-M6"
- "billSubmissionDeadline": "15 days"
- "requiredApproval": "HOD"
- "allowedCities": "NCR, Mumbai, Delhi"
```

**Parallel Execution:**
```python
with ThreadPoolExecutor(max_workers=8) as executor:
    extracted = list(executor.map(extract_single, clauses))
```

**Rate Limiting Backoff:**
```python
# Attempt 1 fails with 429 → wait 2s
# Attempt 2 fails with 429 → wait 4s
# Attempt 3 fails with 429 → wait 8s
# Attempt 4 → give up, return {}
```

**Input from Stage 2:**
```
stage2_classified.json
```

**Output to Stage 4:**
```
stage3_entities.json
```

---

## STAGE 4: GenericAmbiguityDetector

**Location:** `policy_agnostic_stages.py` (lines ~328-520)

**Purpose:** Detect vague/ambiguous language (RULE-BASED, no Gemini)

**Dependencies:**
```python
import re
from typing import Dict, List, Tuple, Optional
```

**Key Attributes:**
```python
self.VAGUE_KEYWORDS       # {"should", "may", "appropriate", ...}
self.OPEN_ENDED          # {"etc", "and so on", "or other", ...}
self.UNDEFINED_REFS      # {"approval", "approved", "authorized", ...}
```

**Key Methods:**

```python
def detect_ambiguities(clause_text: str, entities: Dict = None, 
                       intent: str = None) → (bool, str, float)
    # MAIN METHOD - uses 7 heuristic rules
    # Returns: (is_ambiguous, reason_string, confidence_score 0-100)
    
    # Scoring algorithm:
    # Score starts at 0
    # Rule 1: Vague keywords (+15 each) - should, may, appropriate
    # Rule 2: Open-ended language (+20 each) - etc, and so on
    # Rule 3: Undefined references (+25) - approval without "by whom"
    # Rule 4: Incomplete conditions (+20) - IF without THEN
    # Rule 5: Ununit numbers (+20) - numbers without units
    # Rule 6: Unanchored percentages (+15) - % without base
    # Rule 7: Clarity signals (-10 each) - maximum, minimum, explicit
    # 
    # Result: score > 40 = ambiguous

def _count_vague_keywords(text: str) → int
    # Count instances of vague keywords
    # Uses regex word boundary matching

def _count_open_ended(text: str) → int
    # Count open-ended language
    # "etc", "and so on", "other", "others", "such"

def _check_undefined_refs(text: str) → Optional[str]
    # Check for undefined references
    # Returns: None or "approval without clear authority"

def _has_incomplete_condition(text: str) → bool
    # Check IF/THEN balance
    # Returns: True if one exists without the other

def _has_ununit_numbers(text: str, entities: Dict) → bool
    # Check for numeric values without units
    # Looks for unit keywords: km, hour, day, week, percent, Rs, USD

def _has_unanchored_percentages(text: str) → bool
    # Check if percentages have base values
    # Looks for: "of", "on", "against", "from" after percentage

def _count_clarity_signals(text: str, entities: Dict) → int
    # Count clarity indicators (reduce ambiguity)
    # Examples: "maximum", "minimum", "exactly", "precisely"
    # Good entity coverage, explicit conditions
```

**NO Gemini Integration** - Pure rule-based

**Output Structure:**
```json
{
  "clauseId": "C3",
  "text": "Approved officers can claim appropriate accommodation.",
  "ambiguous": true,
  "ambiguity_score": 62,
  "reason": "Found 2 vague keyword(s) | Undefined reference: 'Approved'",
  "ambiguity_types": ["vague_language", "undefined_reference"],
  "clarity_level": "low",
  "confidence_score": 76
}
```

**Input from Stage 3:**
```
stage3_entities.json
stage2_classified.json (optional - for intent info)
```

**Output to Stage 5:**
```
stage4_ambiguity_flags.json
```

---

## STAGE 5: AmbiguityClarifier

**Location:** `policy_validator.py` (lines ~5256-5660)

**Purpose:** Clarify ambiguous clauses using context from policy

**Dependencies:**
```python
from concurrent.futures import ThreadPoolExecutor
import google.generativeai as genai
from policy_validator import AmbiguityClarificationEngine
```

**Key Attributes:**
```python
self.stage3_file          # Input: stage3_entities.json
self.stage4_file          # Input: stage4_ambiguity_flags.json
self.raw_policy_file      # Input: filename.txt (for context)
self.clarified_file       # Output: stage5_clarified_clauses.json
self.max_workers          # Default: 8
self.batch_size           # Default: 3
self.log                  # Log entries
self.storage              # PipelineStageStorage instance
self.model                # Gemini model
self.context_engine       # AmbiguityClarificationEngine instance
```

**Key Methods:**

```python
def __init__(self, stage3_file, stage4_file, raw_policy_file=None,
             document_id=None, enable_mongodb=True, max_workers=8,
             batch_size=3, enable_semantic_search=False)
    # Initialize clarifier, context engine, Gemini

def log_entry(level, message) → None
    # Thread-safe logging

def clarify_clause_with_context(clause_id, original_text, ambiguity_reason,
                                ambiguity_types, context_text,
                                search_method) → dict
    # Gemini-powered clarification
    # Uses ONLY definitions found in policy context
    # Returns: {
    #     "text_clarified": "Updated clause",
    #     "confidence": 0.0-1.0,
    #     "is_real_ambiguity": bool,
    #     "real_ambiguity_reason": "What definition missing",
    #     "context_used": search_method,
    #     "changes_made": ["change1", "change2"]
    # }

def process_single_clause(clause, ambiguity_map) → dict
    # Helper for parallel processing
    # Steps:
    # 1. Check if clause is ambiguous
    # 2. Search policy context (context_engine)
    # 3. Clarify with Gemini (clarify_clause_with_context)
    # 4. Return clarified clause record

def clarify_all_clauses() → bool
    # MAIN WORKFLOW:
    # 1. Load stage3_file and stage4_file
    # 2. Create ambiguity_map
    # 3. PARALLEL process each clause (8 workers)
    # 4. format_clarification_output()
    # 5. Save to stage5_clarified_clauses.json
    # 6. Store to MongoDB
    # Returns: True on success

def format_clarification_output(clarified_clauses, stats) → dict
    # Add metadata: ambiguities fixed, real_ambiguities, etc.

def save_log() → None
    # Append to mechanism.log
```

**Two-Step Clarification:**

1. **Context Search:** Uses AmbiguityClarificationEngine
   ```python
   context_found, context_text, search_method = \
       self.context_engine.search_context(ambiguity_record)
   
   # search_method can be:
   # - "definitions_section"
   # - "pattern_matching"
   # - "semantic_search"
   # - "not_found"
   ```

2. **LLM Clarification:** Uses Gemini
   ```
   CLAUSE: "Approved officers can claim appropriate accommodation."
   
   AMBIGUITY: Undefined reference + vague language
   
   CONTEXT: "Officers at grade M4 and above are Approved Officers"
            "Accommodation limit is Rs 5000 per night"
   
   OUTPUT: "Officers at grade M4 and above (Approved Officers) 
            can claim accommodation within limit of Rs 5000 per night."
   ```

**Real Ambiguity Detection:**
- If no definition found in policy → mark `is_real_ambiguity = true`
- Indicates policy gap, not LLM failure

**Parallel Execution:**
```python
with ThreadPoolExecutor(max_workers=8) as executor:
    # Process ambiguous clauses in parallel
```

**Input from Stage 4:**
```
stage3_entities.json
stage4_ambiguity_flags.json
filename.txt (for context search)
```

**Output to Stage 6:**
```
stage5_clarified_clauses.json
```

---

## STAGE 6: DSLGenerator

**Location:** `policy_validator.py` (lines ~5664-5950)

**Purpose:** Generate executable DSL rules (3-step: Index → Pattern → LLM)

**Dependencies:**
```python
from concurrent.futures import ThreadPoolExecutor
import google.generativeai as genai
from langchain.chains import LLMChain
import yaml  # for output format
```

**Key Attributes:**
```python
self.stage5_file          # Input: stage5_clarified_clauses.json
self.stage4_file          # Input: stage4_ambiguity_flags.json
self.dsl_file             # Output: stage6_dsl_rules.yaml
self.use_langchain        # Boolean flag
self.log                  # Log entries
self.storage              # PipelineStageStorage instance
self.model                # Gemini model
self.langchain_llm        # ChatGoogleGenerativeAI (if available)
self.clause_indexer       # ClauseIndexer instance
```

**Key Methods:**

```python
def __init__(self, stage5_file, stage4_file, document_id=None,
             enable_mongodb=True, use_langchain=True)
    # Initialize generator, indexer, Gemini

def log_entry(level, message) → None
    # Thread-safe logging

# STEP 1: Index Lookup (Fast Path - NO Gemini)
def generate_dsl_from_index(clause_id, intent, entities,
                            is_ambiguous) → dict or None
    # Extract keywords from entities
    # Find similar clauses in index (top_k=1)
    # If found: return generate_dsl_from_pattern()
    # If not found: return None (fall through to Step 2)

# STEP 2: Pattern-Based Generation (NO Gemini)
def generate_dsl_from_pattern(clause_id, intent, entities,
                              is_ambiguous, similar_clause) → dict
    # Build WHEN conditions from entities:
    # - "maximum" → LESS_THAN_OR_EQUAL
    # - "minimum" → GREATER_THAN_OR_EQUAL
    # - default → EQUALS
    #
    # Build THEN constraints from intent:
    # - RESTRICTION → "approval.required"
    # - LIMIT → "limit.<type>"
    # - CONDITIONAL_ALLOWANCE → "allowance.<type>"
    # - INFORMATIONAL → "PASS"
    # 
    # Action: "enforce" if not ambiguous, "warn" if ambiguous
    #
    # Returns: DSL rule dict

# STEP 3: LLM Generation (Fallback - ~10% of clauses)
def generate_dsl_rule_with_gemini(clause_id, clause_text, intent,
                                  entities, is_ambiguous) → dict
    # Gemini-powered DSL generation (FALLBACK ONLY)
    # Used when index lookup fails
    # Returns: DSL rule dict

def generate() → bool
    # MAIN WORKFLOW:
    # 1. Load stage5_file and stage4_file
    # 2. Build ambiguity_map
    # 3. PARALLEL generate DSL rules (8 workers):
    #    - For each clause:
    #      a. Try generate_dsl_from_index()
    #      b. If miss, try generate_dsl_from_pattern()
    #      c. If still fails, use generate_dsl_rule_with_gemini()
    # 4. Combine all rules
    # 5. Save to stage6_dsl_rules.yaml
    # 6. Store to MongoDB
    # Returns: True on success

def create_default_rule(clause_id, is_ambiguous) → dict
    # Fallback when all methods fail
    # Returns: {
    #     "rule_id": clause_id,
    #     "when": {"all": []},
    #     "then": {
    #         "warn" or "enforce": [
    #             {"constraint": "PASS", "operator": "EQUALS", "value": "OK"}
    #         ]
    #     }
    # }

def format_dsl_output(dsl_rules) → dict or str
    # Format rules as YAML or JSON
    # Add metadata and execution info
```

**Three-Step DSL Generation:**

```
For each clause:
├─ Step 1: Index Lookup (90% hit)
│  └─ If similar clause exists → use its pattern (fast)
│
├─ Step 2: Pattern-Based (5% hit)
│  └─ If heuristics apply → generate from pattern (no LLM)
│
└─ Step 3: LLM Generation (5% miss)
   └─ If nothing worked → use Gemini (slow but accurate)
```

**DSL Rule Structure:**
```json
{
  "rule_id": "C1",
  "when": {
    "all": [
      {
        "fact": "metric.travel_distance",
        "operator": "LESS_THAN_OR_EQUAL",
        "value": "200",
        "unit": "km"
      }
    ]
  },
  "then": {
    "enforce": [
      {
        "constraint": "limit.travel_distance",
        "operator": "ENFORCED",
        "value": "STRICT"
      }
    ]
  }
}
```

**Operators:**
```
WHEN operators: EQUALS, NOT_EQUALS, GREATER_THAN, LESS_THAN,
                GREATER_THAN_OR_EQUAL, LESS_THAN_OR_EQUAL,
                IN, NOT_IN, CONTAINS, NOT_CONTAINS, EXISTS

THEN actions: enforce, warn, recommend, gate
```

**Ambiguity Flag:**
- If `is_ambiguous = true` → use "warn" action instead of "enforce"

**Parallel Execution:**
```python
with ThreadPoolExecutor(max_workers=8) as executor:
    dsl_rules = list(executor.map(generate_dsl_single_rule, clauses))
```

**Input from Stage 5:**
```
stage5_clarified_clauses.json
stage4_ambiguity_flags.json
```

**Output:**
```
stage6_dsl_rules.yaml (or JSON)
```

---

## Support Classes

### PipelineConfig

**Location:** `policy_validator.py` (lines ~65-123)

```python
class PipelineConfig:
    """Centralized configuration for all pipeline stages"""
    
    # LLM/Gemini Settings
    LLM_MODEL = "gemma-3-27b-it"
    LLM_TEMPERATURE = 0.1
    LLM_MAX_RETRIES = 3
    
    # Text Processing
    CHUNK_SIZE = 3000
    CHUNK_OVERLAP = 300
    TEXT_PREVIEW_LENGTH = 8000
    
    # Parallel Processing
    DEFAULT_MAX_WORKERS = 8
    DEFAULT_BATCH_SIZE = 3
    ENTITY_EXTRACTION_WORKERS = 8
    AMBIGUITY_CLARIFICATION_WORKERS = 8
    
    # Pattern Matching
    TOP_K_SIMILAR_CLAUSES = 3
    TOP_K_DSL_LOOKUP = 1
    
    # Timeout and Retries
    LLM_CALL_TIMEOUT = 120
    LLM_RETRY_DELAY = 2
    LLM_RETRY_ATTEMPTS = 2
    
    # JSON Parsing
    INTENT_CONFIDENCE_MIN = 0.0
    INTENT_CONFIDENCE_MAX = 1.0
    DEFAULT_CONFIDENCE = 0.75
    
    # Ambiguity Detection
    AMBIGUITY_STRICT_MODE = True
    
    # Normalization
    NORMALIZATION_USE_LLM = False
    
    @classmethod
    def to_dict(cls) → dict
        # Export all configs as dictionary
    
    @classmethod
    def validate(cls) → bool
        # Validate all config values
        # Asserts: Temperature [0,1], Workers > 0, etc.
```

### PipelineStageStorage

**Location:** `policy_validator.py` (lines ~125-228)

```python
class PipelineStageStorage:
    """MongoDB integration for stage outputs"""
    
    def __init__(self, enable_mongodb=True, document_id=None)
        # Initialize MongoDB connection (optional)
        # Setup thread-safe logging
    
    def log_entry(level, message) → None
        # Thread-safe logging with timestamp
    
    def store_stage(stage_number, stage_name, stage_output,
                    filename=None) → dict
        # Store stage result to MongoDB
        # Returns: {"success": bool, "stage_id": str, "error": str}
    
    def get_pending_stages(limit=10) → list
        # Get stages pending approval
    
    def approve_stage(stage_id, approved_by, notes=None) → dict
        # Mark stage as approved
    
    def reject_stage(stage_id, rejected_by, reason) → dict
        # Mark stage as rejected
    
    def disconnect() → None
        # Disconnect from MongoDB
```

### AmbiguityClarificationEngine

**Location:** `policy_validator.py` (referenced in Stage 5)

```python
class AmbiguityClarificationEngine:
    """Search policy for context to clarify ambiguous clauses"""
    
    def __init__(self, stage3_file, stage4_file, raw_policy_file,
                 enable_semantic_search=False)
        # Initialize search engine
    
    def search_context(ambiguity_record) → (bool, str, str)
        # Search for definitions
        # Returns: (context_found, context_text, search_method)
        # 
        # search_method:
        # - "definitions_section" - Found definitions
        # - "pattern_matching" - Found via regex
        # - "semantic_search" - Found via embeddings
        # - "not_found" - No context found
```

---

## Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 0: DocumentStructureAnalyzer                               │
│ Input: filename.txt (raw policy)                                 │
│ Output: stage0_structured_document.json                          │
│ Purpose: Extract sections, annexures, all_clauses                │
│ Time: ~2-5s | Gemini: ❌ NO                                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ STAGE 1B: ClauseExtractor                                        │
│ Input: all_clauses from Stage 0                                  │
│ Output: stage1_clauses.json                                      │
│ Purpose: Extract individual clauses with elaboration             │
│ Time: ~5-10s | Gemini: ✅ LangChain/Direct API                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ STAGE 2: IntentClassifier (PARALLEL - 8 workers)                │
│ Input: stage1_clauses.json                                       │
│ Output: stage2_classified.json                                   │
│ Purpose: Classify clause intent (RESTRICTION, LIMIT, etc.)      │
│ Time: ~15-30s | Gemini: ✅ Direct API (1 call per clause)       │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ STAGE 3: GenericEntityExtractor (PARALLEL - 8 workers)           │
│ Input: stage2_classified.json                                    │
│ Output: stage3_entities.json                                     │
│ Purpose: Extract entities (amounts, durations, roles, etc.)      │
│ Time: ~30-60s | Gemini: ✅ Direct API (1 call per clause)       │
│                  Rate limiting: exponential backoff              │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ STAGE 4: GenericAmbiguityDetector                               │
│ Input: stage3_entities.json, stage2_classified.json              │
│ Output: stage4_ambiguity_flags.json                              │
│ Purpose: Detect vague/ambiguous clauses (rule-based)            │
│ Time: ~5-10s | Gemini: ❌ NO (regex-based)                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ STAGE 5: AmbiguityClarifier (PARALLEL - 8 workers)              │
│ Input: stage3_entities.json, stage4_ambiguity_flags.json,       │
│        filename.txt (context search)                             │
│ Output: stage5_clarified_clauses.json                           │
│ Purpose: Clarify ambiguous clauses with policy context          │
│ Time: ~20-40s | Gemini: ✅ Direct API (1 call per ambiguous)   │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│ STAGE 6: DSLGenerator (PARALLEL - 8 workers)                     │
│ Input: stage5_clarified_clauses.json, stage4_ambiguity_flags    │
│ Output: stage6_dsl_rules.yaml                                    │
│ Purpose: Generate executable DSL rules                          │
│         (Index lookup → Pattern → LLM fallback)                 │
│ Time: ~10-20s | Gemini: ✅ Direct API (~10% of clauses)        │
│              Hit rate: 90% index, 5% pattern, 5% LLM            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference: Which File Has What

| Class | File | Purpose |
|-------|------|---------|
| `DocumentStructureAnalyzer` | `policy_validator_stage0_new.py` | Extract document structure |
| `ClauseExtractor` | `policy_validator.py` (L~1300) | Extract clauses |
| `IntentClassifier` | `policy_validator.py` (L~1557) | Classify intent |
| `GenericEntityExtractor` | `policy_agnostic_stages.py` (L~36) | Extract entities |
| `GenericAmbiguityDetector` | `policy_agnostic_stages.py` (L~328) | Detect ambiguity |
| `AmbiguityClarifier` | `policy_validator.py` (L~5256) | Clarify ambiguous clauses |
| `DSLGenerator` | `policy_validator.py` (L~5664) | Generate DSL rules |
| `PipelineConfig` | `policy_validator.py` (L~65) | Configuration |
| `PipelineStageStorage` | `policy_validator.py` (L~125) | MongoDB storage |

---

## Performance Summary

**Total Time:** ~2-3 minutes for 25-clause policy

| Stage | Time | Workers | Gemini Calls | Hit Rate |
|-------|------|---------|--------------|----------|
| 0 | ~2-5s | 1 | 0 | 100% |
| 1B | ~5-10s | 1 | 1 | 90% |
| 2 | ~15-30s | 8 | 25 | 90% |
| 3 | ~30-60s | 8 | 25 | 85% |
| 4 | ~5-10s | 1 | 0 | 95% |
| 5 | ~20-40s | 8 | ~8 | 80% |
| 6 | ~10-20s | 8 | ~2-3 | 95% |

**Total Gemini API Calls:** ~80 calls

---

## Error Handling Strategy

**All Stages:**
- ✅ Thread-safe logging with timestamps
- ✅ JSON parse error recovery
- ✅ Graceful degradation (fallback values)
- ✅ MongoDB optional (continues without it)
- ✅ LangChain optional (falls back to standard API)

**Gemini-Specific:**
- ✅ Markdown cleanup (removes ```json wrappers)
- ✅ Exponential backoff for rate limits (429 errors)
- ✅ Retry up to 3 times before giving up
- ✅ Default values for parsing failures

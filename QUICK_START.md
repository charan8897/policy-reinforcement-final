# Quick Start Guide - Policy Validator Pipeline

## 7-Stage Pipeline at a Glance

```
PDF → [Stage 0] → [Stage 1B] → [Stage 2] → [Stage 3] → [Stage 4] → [Stage 5] → [Stage 6] → DSL Rules
       Extract     Extract     Intent    Extract   Detect       Clarify     Generate
       Structure   Clauses     Type      Entities  Ambiguity    Ambiguity   DSL
       
       No LLM      Gemini      Gemini    Gemini    No LLM       Gemini      Gemini
       ~5s         ~10s        ~30s      ~60s      ~10s         ~40s        ~20s
```

---

## Stage Breakdown

### Stage 0: Document Structure Analysis
**File:** `policy_validator_stage0_new.py`  
**Class:** `DocumentStructureAnalyzer`  
**Input:** `filename.txt` (raw policy)  
**Output:** `stage0_structured_document.json`  

**What it does:**
- Parses document into sections (Objective, Scope, Eligibility, etc.)
- Extracts Annexures (city classifications, rate tables, rules)
- Converts everything to clause objects
- **Critical:** Ensures Annexures with actual rules aren't lost

**Gemini:** ❌ NO - Pure regex-based

**Key Methods:**
- `read_policy_text()` - Read raw file
- `identify_section()` - Detect section headers
- `identify_annexure()` - Detect annexure markers
- `analyze_structure()` - Main parsing
- `_parse_city_classification()` - Extract city lists
- `_parse_rates_table()` - Extract rates/amounts
- `generate_all_clauses()` - Convert to clause objects

---

### Stage 1B: Clause Extraction
**File:** `policy_validator.py`  
**Class:** `ClauseExtractor`  
**Input:** `filename.txt` or `stage0_structured_document.json`  
**Output:** `stage1_clauses.json`  

**What it does:**
- Extracts individual policy clauses
- Elaborates and enriches clause text
- Creates clauseId for each (C1, C2, C3, ...)
- Validates structure

**Gemini:** ✅ YES
- LangChain (Pydantic validation) OR
- Direct API call
- 1 call total for whole policy

**Key Methods:**
- `read_policy_file()` - Read input
- `extract_clauses_with_langchain()` - LangChain approach
- `extract_clauses_with_gemini()` - Direct API approach
- `validate_clauses()` - Check structure
- `build_clause_map()` - Create mapping
- `extract()` - Main workflow

---

### Stage 2: Intent Classification
**File:** `policy_validator.py`  
**Class:** `IntentClassifier`  
**Input:** `stage1_clauses.json`  
**Output:** `stage2_classified.json`  

**What it does:**
- Classifies each clause's intent (7 types)
- Assigns confidence score (0.0-1.0)
- Provides reasoning for classification
- **Parallel:** 8 concurrent workers

**Gemini:** ✅ YES
- 1 call per clause
- 25 clauses = 25 API calls (in parallel)

**Intent Types:**
1. **RESTRICTION** - Prohibits action ("must NOT")
2. **LIMIT** - Sets thresholds ("maximum 5000")
3. **CONDITIONAL_ALLOWANCE** - IF/THEN rules ("if approved, then...")
4. **EXCEPTION** - Special cases ("except", "unless")
5. **APPROVAL_REQUIRED** - Needs authorization
6. **ADVISORY** - Recommended ("should", "may")
7. **INFORMATIONAL** - Definitions ("classified as")

**Key Methods:**
- `read_clauses_file()` - Read input
- `classify_intent_with_gemini()` - Classify single clause
- `classify()` - Main parallel workflow
- `format_classified_output()` - Add metadata

---

### Stage 3: Entity Extraction
**File:** `policy_agnostic_stages.py` or `policy_validator.py`  
**Class:** `GenericEntityExtractor`  
**Input:** `stage2_classified.json`  
**Output:** `stage3_entities.json`  

**What it does:**
- Extracts measurable values from clauses
- Creates meaningful entity names (camelCase)
- No predefined schema - fully dynamic
- **Parallel:** 8 concurrent workers
- **Rate limiting:** Exponential backoff on 429 errors

**Gemini:** ✅ YES
- 1 call per clause
- 25 clauses = 25 API calls (in parallel)
- Retry up to 3 times on rate limit (2s → 4s → 8s)

**Entity Types (Dynamic):**
- Numeric values: `200`, `50`
- Amounts: `Rs 5000`, `$100`
- Durations: `15 days`, `2 weeks`
- Percentages: `25%`
- Roles: `Manager`, `HR Officer`
- Conditions: IF/THEN clauses
- Exclusions: "except", "other than"

**Example Extraction:**
```
Input: "Rs. 7.0 per KM for Four Wheeler or Rs. 2.5 per KM for Two Wheeler"
Output: {
  "fourWheelerRate": "7.0 Rs/KM",
  "twoWheelerRate": "2.5 Rs/KM"
}
```

**Key Methods:**
- `read_classified_file()` - Read input
- `extract_entities_with_gemini()` - Extract from clause
- `extract()` - Main parallel workflow
- `calculate_entity_statistics()` - Stats
- `format_entities_output()` - Add metadata

---

### Stage 4: Ambiguity Detection
**File:** `policy_agnostic_stages.py`  
**Class:** `GenericAmbiguityDetector`  
**Input:** `stage3_entities.json`  
**Output:** `stage4_ambiguity_flags.json`  

**What it does:**
- Detects vague/unclear language (7 rules)
- Scores clauses 0-100 (>40 = ambiguous)
- Flags unclear terms and references
- **NO parallel** - Fast rule-based checks

**Gemini:** ❌ NO - Pure heuristics

**7 Ambiguity Rules:**
1. **Vague keywords** (+15 each): should, may, appropriate, reasonable
2. **Open-ended language** (+20 each): etc, and so on, other
3. **Undefined references** (+25): approval without "by whom"
4. **Incomplete conditions** (+20): IF without THEN
5. **Ununit numbers** (+20): numbers without units
6. **Unanchored percentages** (+15): % without base value
7. **Clarity signals** (-10 each): maximum, minimum (reduce score)

**Scoring Example:**
```
Clause: "Approved officers can claim appropriate accommodation."

Vague keywords: "Approved", "appropriate" → +30
Undefined refs: "Approved" without who approves → +25
Score = 55 → AMBIGUOUS ⚠

Reasons: ["Found 2 vague keywords", "Undefined reference"]
```

**Key Methods:**
- `detect_ambiguities()` - Main detection
- `_count_vague_keywords()` - Rule 1
- `_count_open_ended()` - Rule 2
- `_check_undefined_refs()` - Rule 3
- `_has_incomplete_condition()` - Rule 4
- `_has_ununit_numbers()` - Rule 5
- `_has_unanchored_percentages()` - Rule 6
- `_count_clarity_signals()` - Rule 7

---

### Stage 5: Ambiguity Clarification
**File:** `policy_validator.py`  
**Class:** `AmbiguityClarifier`  
**Input:** `stage3_entities.json`, `stage4_ambiguity_flags.json`, `filename.txt`  
**Output:** `stage5_clarified_clauses.json`  

**What it does:**
- Searches policy for definitions of ambiguous terms
- Inserts real definitions from policy into clauses
- Flags "real ambiguities" (policy gaps) where no definition found
- **Parallel:** 8 concurrent workers

**Gemini:** ✅ YES (only for ambiguous clauses)
- ~8/25 clauses are ambiguous
- 1 call per ambiguous clause
- ~8 API calls total

**Two-Step Process:**

1. **Context Search:** Uses `AmbiguityClarificationEngine`
   - Searches Definitions section
   - Pattern matches in policy
   - Semantic search (optional)
   - Returns: (context_found, context_text, search_method)

2. **LLM Clarification:** Uses Gemini
   - Receives: clause, ambiguities, found context
   - Task: Insert definitions from context ONLY
   - Returns: clarified clause + confidence + real_ambiguity flag

**Example:**
```
Original: "Approved officers can claim appropriate accommodation."
Context Found: "Officers grade M4+ are Approved Officers. Limit: Rs 5000/night"
Clarified: "Officers at grade M4+ (Approved Officers) can claim accommodation up to Rs 5000 per night."
Confidence: 0.89
Real Ambiguity: false
```

**Key Methods:**
- `clarify_clause_with_context()` - Gemini clarification
- `process_single_clause()` - Process one clause
- `clarify_all_clauses()` - Main parallel workflow
- `format_clarification_output()` - Add metadata

---

### Stage 6: DSL Rule Generation
**File:** `policy_validator.py`  
**Class:** `DSLGenerator`  
**Input:** `stage5_clarified_clauses.json`, `stage4_ambiguity_flags.json`  
**Output:** `stage6_dsl_rules.yaml` or `.json`  

**What it does:**
- Converts clarified clauses into executable DSL rules
- 3-step approach: Index → Pattern → LLM
- Marks ambiguous rules with "warn" instead of "enforce"
- **Parallel:** 8 concurrent workers

**Gemini:** ✅ YES (only ~10% of clauses)
- 90% hit rate on Index lookup (fast)
- 5% hit rate on Pattern matching (no LLM)
- 5% fallback to LLM (~2-3 API calls)

**3-Step Generation:**

1. **Index Lookup** (90% hit - NO Gemini)
   - Check if similar clause exists in index
   - If yes: reuse pattern
   - If no: fall through to Step 2

2. **Pattern-Based** (5% hit - NO Gemini)
   - Apply heuristics:
     - "maximum" entity → LESS_THAN_OR_EQUAL
     - "minimum" entity → GREATER_THAN_OR_EQUAL
     - RESTRICTION intent → "approval.required"
     - LIMIT intent → "limit.<type>"
   - If successful: return rule
   - If fail: fall through to Step 3

3. **LLM Generation** (5% fallback - Uses Gemini)
   - Send clause + intent + entities to Gemini
   - Gemini generates complete DSL rule
   - Used only when heuristics fail

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
    "enforce": [  // "warn" if ambiguous
      {
        "constraint": "limit.travel_distance",
        "operator": "ENFORCED",
        "value": "STRICT"
      }
    ]
  }
}
```

**Key Methods:**
- `generate_dsl_from_index()` - Step 1 (fast lookup)
- `generate_dsl_from_pattern()` - Step 2 (heuristics)
- `generate_dsl_rule_with_gemini()` - Step 3 (LLM fallback)
- `generate()` - Main parallel workflow
- `create_default_rule()` - Fallback for failures
- `format_dsl_output()` - Output as YAML/JSON

---

## Configuration Classes

### PipelineConfig
- **Location:** `policy_validator.py` (L65-123)
- **Purpose:** Centralized configuration
- **Key Settings:**
  - `LLM_MODEL = "gemma-3-27b-it"`
  - `LLM_TEMPERATURE = 0.1` (deterministic)
  - `DEFAULT_MAX_WORKERS = 8`
  - `CHUNK_SIZE = 3000`
  - `LLM_RETRY_ATTEMPTS = 2`

### PipelineStageStorage
- **Location:** `policy_validator.py` (L125-228)
- **Purpose:** MongoDB integration
- **Methods:**
  - `store_stage()` - Save stage output
  - `approve_stage()` - Mark as approved
  - `reject_stage()` - Mark as rejected

---

## Running the Pipeline

### All Stages:
```bash
python policy_validator.py all <policy.pdf>
```

### Individual Stages:
```bash
# Stage 0
python policy_validator_stage0_new.py filename.txt

# Stage 1B
python policy_validator.py extract-clauses filename.txt

# Stage 2
python policy_validator.py classify-intents stage1_clauses.json

# Stage 3
python policy_validator.py extract-entities stage2_classified.json

# Stage 4
python policy_validator.py detect-ambiguities stage3_entities.json

# Stage 5
python policy_validator.py clarify-ambiguities stage3_entities.json

# Stage 6
python policy_validator.py generate-dsl stage5_clarified_clauses.json
```

---

## Output Files

| Stage | Output File | Size | Content |
|-------|-------------|------|---------|
| 0 | `stage0_structured_document.json` | ~500KB | Structured sections + annexures + all clauses |
| 1B | `stage1_clauses.json` | ~50KB | 25 clauses with elaboration |
| 2 | `stage2_classified.json` | ~60KB | Clauses + intents + confidence |
| 3 | `stage3_entities.json` | ~80KB | Clauses + extracted entities |
| 4 | `stage4_ambiguity_flags.json` | ~40KB | Ambiguity scores + reasons |
| 5 | `stage5_clarified_clauses.json` | ~100KB | Original + clarified text + confidence |
| 6 | `stage6_dsl_rules.yaml` or `.json` | ~60KB | 25 executable DSL rules |

---

## Performance Summary

**Total Time:** ~2-3 minutes (25-clause policy)

| Stage | Time | Workers | Gemini | Calls |
|-------|------|---------|--------|-------|
| 0 | 5s | 1 | ❌ NO | 0 |
| 1B | 10s | 1 | ✅ YES | 1 |
| 2 | 30s | 8 | ✅ YES | 25 |
| 3 | 60s | 8 | ✅ YES | 25 |
| 4 | 10s | 1 | ❌ NO | 0 |
| 5 | 40s | 8 | ✅ YES | ~8 |
| 6 | 20s | 8 | ✅ YES | ~2 |

**Total:** ~175s / ~80 Gemini API calls

---

## Error Handling

**All stages have:**
- ✅ Thread-safe logging with timestamps
- ✅ JSON parse error recovery (returns empty/default)
- ✅ Markdown cleanup for Gemini responses
- ✅ Exponential backoff for rate limits
- ✅ Retry up to 3 times before giving up
- ✅ MongoDB optional (continues without it)
- ✅ LangChain optional (falls back to standard API)

---

## Key Concepts

### Parallel Processing
- Stages 2, 3, 5, 6 use `ThreadPoolExecutor(max_workers=8)`
- Each clause processed independently
- ~8x faster than sequential

### Rate Limiting
- 429 errors trigger exponential backoff
- Wait: 2s → 4s → 8s → give up
- Returns empty/default value on final failure

### Dynamic Entities
- No predefined schema in Stage 3
- LLM infers meaningful names from context
- Examples: `fourWheelerRate`, `lodgingAmount`, `travelDuration`

### Real Ambiguities
- Stage 5 distinguishes:
  - Clarifiable ambiguities (definition found) → clarified
  - Real ambiguities (no definition in policy) → flagged as policy gap

### Three-Step DSL Generation
1. **Index lookup** (90% - fast) - NO LLM
2. **Pattern heuristics** (5% - faster) - NO LLM
3. **LLM generation** (5% - slower) - Uses Gemini

---

## Document Structure

```
policy/
├── filename.txt                          # Raw policy input
├── stage0_structured_document.json       # Sections + annexures
├── stage1_clauses.json                   # Extracted clauses
├── stage2_classified.json                # Intents classified
├── stage3_entities.json                  # Entities extracted
├── stage4_ambiguity_flags.json           # Ambiguities detected
├── stage5_clarified_clauses.json         # Clarified versions
├── stage6_dsl_rules.yaml                 # Final DSL rules
└── mechanism.log                         # Complete execution log
```

---

## Quick Debugging

**Check Stage Output:**
```bash
# Pretty-print JSON
python -m json.tool stage2_classified.json | head -50

# Count clauses by intent
python -c "import json; d=json.load(open('stage2_classified.json')); \
  from collections import Counter; \
  c=Counter(x['intent'] for x in d['classified_clauses']); \
  print(dict(c))"

# Check for ambiguities
python -c "import json; d=json.load(open('stage4_ambiguity_flags.json')); \
  amb=[x for x in d if x['ambiguous']]; \
  print(f'Ambiguous: {len(amb)}/{len(d)}')"
```

**Check Logs:**
```bash
tail -100 mechanism.log
grep "ERROR" mechanism.log
grep "WARNING" mechanism.log
```

---

## Files to Read

1. **Understanding Stages:** `STAGES_BREAKDOWN.md`
2. **Understanding Gemini:** `GEMINI_INTERACTIONS.md`
3. **Understanding Classes:** `COMPLETE_CLASS_MAP.md`
4. **This Guide:** `QUICK_START.md`

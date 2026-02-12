# Rego Field Mapper Module

AI-powered field mapper for converting payload fields to OPA Rego `input.xxx` conditions in policy enforcement systems.

**Part of: docupolicy - Policy Reinforcement System**

## 📁 Module Contents

```
rego_field_mapper_module/
├── find_rego_fields.py              # Core engine (RegoFieldMatcher class)
├── rego_field_mapper.py             # Easy-to-use wrapper (recommended)
├── find_rego_fields.sh              # Bash CLI alternative
├── REGO_FIELD_MAPPER_GUIDE.md       # Detailed API documentation
└── README.md                        # This file
```

## 🎯 Overview

Maps semantic payload fields to actual Rego condition fields:

```
"authorizing_entity"           → input.validationauthority
"reimbursement_ceiling"        → input.lodgingallowance
"distance_threshold"           → input.deputationdurationthreshold
"private_lodging_stipend_ratio" → input.gradem1lodgingallowance
```

## 🚀 Quick Start

### Python CLI

```bash
cd /path/to/rego_field_mapper_module

# Basic mapping
python3 find_rego_fields.py "authorizing_entity"

# With Gemini AI
python3 find_rego_fields.py "reimbursement_ceiling"

# Force heuristic mode
python3 find_rego_fields.py "distance_threshold" --no-gemini

# Get top 5 matches
python3 find_rego_fields.py "disbursement_basis" --top-k 5
```

### Bash CLI

```bash
# Heuristic mode
./find_rego_fields.sh "authorizing_entity" false

# Try Gemini first
./find_rego_fields.sh "reimbursement_ceiling" true
```

### Python Integration

```python
import sys
sys.path.insert(0, '/path/to/rego_field_mapper_module')

from rego_field_mapper import (
    map_payload_to_rego_field,
    get_best_match,
    map_payload_batch
)

# Single field mapping
results = map_payload_to_rego_field("authorizing_entity", top_k=3)
for field in results:
    print(f"input.{field.field_name} (Score: {field.score})")

# Best match only
best = get_best_match("reimbursement_ceiling")
print(f"Best: input.{best.field_name}")

# Batch processing
batch = map_payload_batch([
    "authorizing_entity",
    "distance_threshold",
    "private_lodging_stipend_ratio"
])
```

## 📚 API Reference

### Core Class: RegoFieldMatcher

```python
from find_rego_fields import RegoFieldMatcher

matcher = RegoFieldMatcher(
    rego_dir="opa_bundles",  # Path to rego files
    use_gemini=True           # Use Gemini if available
)

# Find matches
results = matcher.match_fields("authorizing_entity", top_k=3)

# Get field context
context = matcher.get_field_context("validationauthority")

# Score a field
score = matcher.score_field("validationauthority", "authorizing_entity")
```

### Wrapper Functions: rego_field_mapper.py

**Recommended for integration with stage11_enforcement_api.py**

```python
from rego_field_mapper import (
    map_payload_to_rego_field,      # Single field → List[RegoField]
    map_payload_batch,               # Multiple fields → dict
    get_best_match,                  # Single field → RegoField
    get_field_info,                  # Get field context
    print_mapping_report,            # Formatted output
    PayloadRegoMapper                # Context manager
)

# Simple usage
results = map_payload_to_rego_field("authorizing_entity")

# Best match
best = get_best_match("authorizing_entity")
if best:
    print(f"input.{best.field_name}")

# Batch
batch = map_payload_batch(["field1", "field2"])
for payload, matches in batch.items():
    print(f"{payload}: {[m.field_name for m in matches]}")

# Context manager
with PayloadRegoMapper() as mapper:
    results = mapper.map("authorizing_entity", top_k=3)
```

## 🔧 Integration with stage11_enforcement_api.py

Add to your enforcement API:

```python
# At top of file
from rego_field_mapper_module.rego_field_mapper import (
    map_payload_to_rego_field,
    PayloadRegoMapper
)

# In your enforcement class
class PolicyEnforcer:
    def __init__(self):
        self.rego_mapper = PayloadRegoMapper()
    
    def validate_payload_to_rego(self, payload_dict):
        """Convert payload fields to rego conditions"""
        rego_mapping = self.rego_mapper.map_dict(payload_dict, top_k=3)
        
        rego_conditions = {}
        for payload_field, rego_matches in rego_mapping.items():
            if rego_matches:
                best = rego_matches[0]
                rego_conditions[payload_field] = {
                    "rego_field": f"input.{best.field_name}",
                    "score": best.score,
                    "context": best.context
                }
        
        return rego_conditions

# Usage
enforcer = PolicyEnforcer()
opa_input = enforcer.validate_payload_to_rego({
    "authorizing_entity": "Senior Manager",
    "reimbursement_ceiling": 5000,
    "distance_threshold": 200
})
```

## 🎓 How It Works

### 1. Pattern Generation
- **Gemini Mode**: Uses LLM to understand semantics and generate regex patterns
- **Heuristic Mode**: Uses keyword extraction + predefined semantic families

### 2. Field Extraction
- Scans all `*.rego` files in opa_bundles/
- Extracts all `input.xxx` field names
- Caches for performance

### 3. Pattern Matching
- Applies generated patterns to extracted fields
- Matches using case-insensitive regex

### 4. Scoring & Ranking
- Exact substring match: +100 points
- Word component match: +25 points each
- Semantic family match: +40 points
- Returns top K by score

## 📊 Output Format

### Python Object (RegoField)

```python
@dataclass
class RegoField:
    field_name: str      # "validationauthority"
    score: int           # 40-100
    context: str         # "input.validationauthority == 'HR & Accounts'"
```

### CLI Output

```
╔════════════════════════════════════════════════╗
║ AI-Powered Rego Field Mapper for Policy Rules  ║
╚════════════════════════════════════════════════╝

Payload Field: authorizing_entity

[Mode: Heuristic]

═══════════════════════════════════════════════
TOP 3 MATCHING REGO FIELDS
═══════════════════════════════════════════════

[MATCH #1] Score: 40
  Field:   input.validationauthority
  Context: input.validationauthority == "HR & Accounts"

[MATCH #2] Score: 40
  Field:   input.approvalauthority
  Context: input.approvalauthority == "Reporting Manager"

[MATCH #3] Score: 40
  Field:   input.eligibledesignations
  Context: input.eligibledesignations == "AGM, Sr. Manager..."
```

## 🎯 Supported Payload Field Families

### Authority/Role Family
- `authorizing_entity`
- `approval_authority`
- `validation_authority`
- `designated_role`

**Maps to:** `input.approvalauthority`, `input.validationauthority`, `input.eligibledesignations`, `input.employeegrade`

### Amount/Limit Family
- `reimbursement_ceiling`
- `daily_limit`
- `maximum_allowance`
- `private_lodging_stipend_ratio`

**Maps to:** `input.lodgingallowance`, `input.*rate`, `input.*allowance`, `input.*limit`

### Duration/Distance Family
- `distance_threshold`
- `travel_duration`
- `maximum_travel_distance`

**Maps to:** `input.deputationdurationthreshold`, `input.maximumdailydistance`, `input.*duration`

### Claim/Disbursement Family
- `disbursement_basis`
- `claim_basis`

**Maps to:** `input.claimbasis`, `input.eligibilitybasis`

## ⚙️ Configuration

### Environment Variables

```bash
# For Gemini AI support
export GEMINI_API_KEY="your-api-key"
# OR
export GOOGLE_API_KEY="your-api-key"
```

### CLI Options

```bash
python3 find_rego_fields.py [payload_field] [OPTIONS]

Options:
  --no-gemini          Disable Gemini, use heuristics only
  --rego-dir PATH      Custom path to opa_bundles (default: opa_bundles)
  --top-k N            Number of matches to return (default: 3)
  -h, --help           Show help message
```

## 📈 Performance

- **First run**: ~50ms (rego field extraction + caching)
- **Subsequent lookups**: <5ms per field
- **Gemini API calls**: ~1-2 seconds (optional)
- **Heuristic mode**: <100ms per field

## 🐛 Troubleshooting

### No matches found
```python
# Check if field name is specific enough
results = map_payload_to_rego_field("field_name", top_k=5)
# Try increasing top_k to see all candidates
```

### Gemini API errors
```bash
# Verify API key
echo $GEMINI_API_KEY

# Force heuristic mode
python3 find_rego_fields.py "field_name" --no-gemini
```

### Wrong matches
```python
# Review the scoring
from find_rego_fields import RegoFieldMatcher
matcher = RegoFieldMatcher()
score = matcher.score_field("matched_field", "your_payload_field")
# Lower scores may need adjustment
```

## 📝 Examples

### Example 1: Simple Mapping

```python
from rego_field_mapper import get_best_match

best = get_best_match("authorizing_entity")
print(f"Best match: input.{best.field_name} (score: {best.score})")
```

### Example 2: Batch Processing

```python
from rego_field_mapper import map_payload_batch

payload_fields = ["authorizing_entity", "reimbursement_ceiling", "distance_threshold"]
mappings = map_payload_batch(payload_fields, top_k=3)

for payload, matches in mappings.items():
    print(f"\n{payload}:")
    for i, match in enumerate(matches, 1):
        print(f"  [{i}] input.{match.field_name} (score: {match.score})")
```

### Example 3: Enforcement API Integration

```python
from rego_field_mapper import PayloadRegoMapper

class PolicyValidator:
    def __init__(self):
        self.mapper = PayloadRegoMapper()
    
    def convert_to_opa_input(self, payload):
        """Convert payload to OPA input conditions"""
        mappings = self.mapper.map_dict(payload, top_k=1)
        
        opa_input = {}
        for payload_field, matches in mappings.items():
            if matches:
                best = matches[0]
                opa_input[f"input.{best.field_name}"] = payload[payload_field]
        
        return opa_input

# Usage
validator = PolicyValidator()
opa_conditions = validator.convert_to_opa_input({
    "authorizing_entity": "Senior Manager",
    "reimbursement_ceiling": 5000,
    "distance_threshold": 200
})
print(opa_conditions)
```

## 📚 Additional Documentation

See **REGO_FIELD_MAPPER_GUIDE.md** for:
- Detailed API reference
- Advanced configuration
- Custom semantic families
- Development guide

## 🔗 Related Files

- `stage11_enforcement_api.py` - Enforcement system that uses this mapper
- `policy_validator.py` - Main policy validation pipeline
- `opa_bundles/` - Rego policy bundles

## 📄 License

Part of docupolicy - Policy Reinforcement System

## ✅ Testing

Test the module:

```bash
cd /path/to/rego_field_mapper_module

# Python tests
python3 find_rego_fields.py "authorizing_entity" --no-gemini
python3 rego_field_mapper.py

# Bash tests (if bash script is used)
./find_rego_fields.sh "distance_threshold" false
```

## 📞 Support

For issues or questions, refer to:
1. REGO_FIELD_MAPPER_GUIDE.md (detailed docs)
2. Code comments in find_rego_fields.py
3. CLI help: `python3 find_rego_fields.py -h`

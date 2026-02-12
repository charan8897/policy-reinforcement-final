# Rego Field Mapper - Integration Guide

Convert payload fields to OPA Rego `input.xxx` conditions using AI-powered field matching.

## Files Created

1. **find_rego_fields.py** - Core engine with RegoFieldMatcher class
2. **rego_field_mapper.py** - Easy-to-use wrapper for integration
3. **find_rego_fields.sh** - Bash CLI version (alternative)

## Quick Start

### CLI Usage (Python)

```bash
# Basic mapping with heuristics
python3 find_rego_fields.py "authorizing_entity"

# Use Gemini AI if available
python3 find_rego_fields.py "reimbursement_ceiling"

# Force heuristic mode
python3 find_rego_fields.py "distance_threshold" --no-gemini

# Get top 5 matches
python3 find_rego_fields.py "disbursement_basis" --top-k 5
```

### Python Integration (Recommended for stage11_enforcement_api.py)

```python
from rego_field_mapper import map_payload_to_rego_field, get_best_match

# Map a single field - get top 3 matches
results = map_payload_to_rego_field("authorizing_entity")
for field in results:
    print(f"input.{field.field_name} (Score: {field.score})")

# Get best match
best = get_best_match("authorizing_entity")
if best:
    print(f"Best match: input.{best.field_name}")

# Map multiple fields
from rego_field_mapper import map_payload_batch
batch_results = map_payload_batch([
    "authorizing_entity",
    "reimbursement_ceiling",
    "distance_threshold"
])

for payload, matches in batch_results.items():
    print(f"{payload}: {[m.field_name for m in matches]}")
```

## Integration with stage11_enforcement_api.py

Add to your enforcement API:

```python
from rego_field_mapper import PayloadRegoMapper

class PolicyEnforcer:
    def __init__(self):
        self.rego_mapper = PayloadRegoMapper()
    
    def validate_payload_to_rego(self, payload_dict):
        """Map payload fields to rego conditions"""
        rego_mapping = self.rego_mapper.map_dict(payload_dict, top_k=3)
        
        # Build rego conditions from mapping
        rego_conditions = {}
        for payload_field, rego_matches in rego_mapping.items():
            best_match = rego_matches[0] if rego_matches else None
            if best_match:
                rego_conditions[payload_field] = {
                    "rego_field": f"input.{best_match.field_name}",
                    "score": best_match.score,
                    "context": best_match.context
                }
        
        return rego_conditions
```

## API Reference

### RegoFieldMatcher (Core Class)

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

### RegoFieldMapper (Wrapper Functions)

```python
from rego_field_mapper import (
    map_payload_to_rego_field,      # Single field mapping
    map_payload_batch,               # Multiple fields
    get_best_match,                  # Single best match
    get_field_info,                  # Field information
    print_mapping_report,            # Formatted report
    PayloadRegoMapper                # Context manager
)
```

## How It Works

### 1. Pattern Generation
- **Gemini Mode**: Uses LLM to generate semantic regex patterns
- **Heuristic Mode**: Uses keyword extraction + semantic families

### 2. Field Matching
- Extracts all `input.xxx` fields from rego files
- Matches against generated regex patterns
- Scores each match based on relevance

### 3. Scoring
- Exact substring match: +100
- Word component match: +25 each
- Semantic family match: +40
- Returns top K ranked by score

## Supported Payload Field Families

### Authority/Role Family
- `authorizing_entity`
- `approval_authority`
- `validation_authority`
- `designated_role`

Maps to: `input.approvalauthority`, `input.validationauthority`, `input.eligibledesignations`

### Amount/Limit Family
- `reimbursement_ceiling`
- `daily_limit`
- `maximum_allowance`
- `stipend_ratio`

Maps to: `input.personalincidentalallowancelimit`, `input.lodgingallowance`, `input.*rate`

### Duration/Distance Family
- `distance_threshold`
- `travel_duration`
- `maximum_travel_distance`

Maps to: `input.deputationdurationthreshold`, `input.maximumdailydistance`

## Configuration

### Environment Variables

```bash
# Use Gemini API
export GEMINI_API_KEY="your-api-key"
export GOOGLE_API_KEY="your-api-key"  # Alternative
```

### CLI Options

```bash
python3 find_rego_fields.py [payload_field] [OPTIONS]

Options:
  --no-gemini          Disable Gemini, use heuristics
  --rego-dir PATH      Custom rego directory (default: opa_bundles)
  --top-k N            Number of matches (default: 3)
```

## Output Format

### Python Objects

```python
RegoField(
    field_name: str,     # "validationauthority"
    score: int,          # 40-100
    context: str         # "input.validationauthority == 'HR & Accounts'"
)
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

## Examples

### Example 1: Simple Mapping

```python
from rego_field_mapper import get_best_match

result = get_best_match("authorizing_entity")
print(f"Match: input.{result.field_name} (score: {result.score})")
# Output: Match: input.validationauthority (score: 40)
```

### Example 2: Batch Processing

```python
from rego_field_mapper import map_payload_batch

payload_fields = {
    "authorizing_entity": "Senior Manager",
    "reimbursement_ceiling": 5000,
    "distance_threshold": 200
}

mappings = map_payload_batch(list(payload_fields.keys()))

for payload, rego_fields in mappings.items():
    if rego_fields:
        best = rego_fields[0]
        print(f"{payload} → input.{best.field_name}")
```

### Example 3: Enforcement API Integration

```python
from rego_field_mapper import PayloadRegoMapper

class PolicyValidator:
    def __init__(self):
        self.mapper = PayloadRegoMapper()
    
    def validate_request(self, payload):
        """Convert payload to OPA input conditions"""
        mappings = self.mapper.map_dict(payload)
        
        opa_input = {}
        for field_name, matches in mappings.items():
            if matches:
                best_match = matches[0]
                opa_input[f"input.{best_match.field_name}"] = payload[field_name]
        
        return opa_input

# Usage
validator = PolicyValidator()
opa_conditions = validator.validate_request({
    "authorizing_entity": "Senior Manager",
    "reimbursement_ceiling": 5000
})
```

## Performance Notes

- First run caches all rego fields (~50ms)
- Subsequent lookups: <5ms per field
- Gemini API calls: ~1-2 seconds (optional)
- Heuristic mode: <100ms per field

## Troubleshooting

### No matches found
- Check payload field spelling
- Try `--no-gemini` flag to see heuristic results
- Verify rego files exist in `opa_bundles/`

### Gemini API errors
- Verify API key is set: `echo $GEMINI_API_KEY`
- Check internet connectivity
- Falls back to heuristic mode automatically

### Wrong matches
- Multiple patterns available, try different top-k values
- Review semantic field families above
- Consider using specific field names instead of generic ones

## Development

To extend with custom field families:

```python
# In find_rego_fields.py, RegoFieldMatcher.generate_patterns_heuristic()
elif any(word in payload_lower for word in ['your_keyword']):
    patterns.append("regex_pattern_1|regex_pattern_2")
```

## License

Part of docupolicy project - Policy Reinforcement System

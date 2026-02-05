"""
Integration Code: Add this to policy_validator.py to use the output formatter

Location: At the end of main() function in policy_validator.py (around line 7390)
"""

# ============================================================================
# ADD THIS IMPORT AT THE TOP OF policy_validator.py
# ============================================================================

"""
from output_formatter import OutputFormatter
"""

# ============================================================================
# ADD THIS TO THE END OF main() FUNCTION
# ============================================================================

"""
def main():
    # ... existing pipeline code ...
    
    # After all stages complete, format outputs
    print("\n" + "="*70)
    print("FORMATTING OUTPUTS")
    print("="*70)
    
    formatter = OutputFormatter()
    formatter.format_all()
    
    print("\n" + "="*70)
    print("PIPELINE COMPLETE")
    print("="*70)
    print(f"✓ Intermediate files: {formatter.TODO_OPTIMIZATION_DIR}")
    print(f"✓ Final outputs: {formatter.FINAL_DIR}")
"""

# ============================================================================
# OR RUN STANDALONE
# ============================================================================

"""
python output_formatter.py
"""

# ============================================================================
# VERIFY OUTPUT STRUCTURE
# ============================================================================

"""
After running formatter:

✓ todo-optimization/
  ├── stage1_clauses.json
  ├── stage2_classified.json
  ├── stage3_entities.json
  ├── stage4_ambiguity_flags.json
  ├── stage5_clarified_clauses.json
  └── stage6_dsl_rules.yaml

✓ final/
  ├── stage1Clause.json         [{"clauseId": "C1", "text": "..."}]
  ├── stage2Classified.json     [{"clauseId": "C1", "intent": "...", "confidence": 0.0}]
  ├── stage3Entities.json       [{"clauseId": "C1", "entities": {...}}]
  ├── stage4Ambiguity.json      [{"clauseId": "C1", "ambiguous": false, "reason": "..."}]
  ├── stage5DslRules.yaml       (as-is copy)
  └── stage6Confidence.json     [{"clauseId": "C1", "rationale": "...", "confidence": 0.0}]
"""

#!/usr/bin/env python3
"""
Output Formatter: Transform stage outputs to optimized format

Creates directory structure:
├── todo-optimization/          (intermediate outputs, original format)
│   ├── stage1_clauses.json
│   ├── stage2_classified.json
│   ├── stage3_entities.json
│   ├── stage4_ambiguity_flags.json
│   ├── stage5_clarified_clauses.json
│   └── stage6_dsl_rules.yaml
│
└── final/                       (cleaned/optimized outputs, camelCase)
    ├── stage1Clause.json       (simplified: clauseId, text)
    ├── stage2Classified.json   (simplified: clauseId, intent, confidence)
    ├── stage3Entities.json     (simplified: clauseId, entities)
    ├── stage4Ambiguity.json    (simplified: clauseId, ambiguous, reason)
    ├── stage5DslRules.yaml     (as-is copy with camelCase name)
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any
import shutil
import re
from datetime import datetime

# Configuration
BASE_DIR = "/home/hutech/Documents/docupolicy"
TODO_OPTIMIZATION_DIR = os.path.join(BASE_DIR, "todo-optimization")
FINAL_DIR = os.path.join(BASE_DIR, "final")

# Stage files (original names in todo-optimization)
STAGE_FILES = {
    1: "stage1_clauses.json",
    2: "stage2_classified.json",
    3: "stage3_entities.json",
    4: "stage4_ambiguity_flags.json",
    5: "stage5_clarified_clauses.json",
    6: "stage6_dsl_rules.yaml",
    7: "stage7_confidence_rationale.json",  # For stage 6 output
}

# Output files (camelCase names in final)
OUTPUT_FILES = {
    1: "stage1Clause.json",
    2: "stage2Classified.json",
    3: "stage3Entities.json",
    4: "stage4Ambiguity.json",
    5: "stage5DslRules.yaml",
    # 6: "stage6Confidence.json",
    8: "stage8_normalized_policies.json",  # Normalized policies (Stage 8)
}

# Intent to Enforcement Mapping
INTENT_TO_ENFORCEMENT = {
    "RESTRICTION": "BLOCK",
    "LIMIT": "WARN",
    "MANDATORY": "REQUIRE",
    "ADVISORY": "SUGGEST",
    "CONDITIONAL_ALLOWANCE": "ALLOW_IF",
    "CONDITIONAL": "ALLOW_IF",
    "EXCEPTION": "ALLOW_IF",
    "APPROVAL_REQUIRED": "REQUIRE_APPROVAL",
    "PERMISSIVE": "ALLOW",
    "INFORMATIONAL": "INFO",
}

# Intent to Constraint Operator Mapping
INTENT_TO_OPERATOR = {
    "RESTRICTION": "MUST_NOT",
    "LIMIT": "MUST_NOT_EXCEED",
    "MANDATORY": "MUST",
    "ADVISORY": "SHOULD",
    "CONDITIONAL_ALLOWANCE": "EQUALS",
    "CONDITIONAL": "EQUALS",
    "EXCEPTION": "EQUALS",
    "APPROVAL_REQUIRED": "NEEDS_AUTHORIZATION",
    "PERMISSIVE": "MAY",
    "INFORMATIONAL": "IS",
}


class OutputFormatter:
    """Transform pipeline outputs to optimized format"""
    
    def __init__(self):
        self.ensure_directories()
    
    def ensure_directories(self):
        """Create todo-optimization and final directories"""
        for dir_path in [TODO_OPTIMIZATION_DIR, FINAL_DIR]:
            os.makedirs(dir_path, exist_ok=True)
            print(f"✓ Directory ready: {dir_path}")
    
    def copy_to_todo_optimization(self):
        """Copy original stage files to todo-optimization directory"""
        print("\n=== Copying to todo-optimization ===")

        for stage, filename in STAGE_FILES.items():
            src = os.path.join(BASE_DIR, filename)
            dst = os.path.join(TODO_OPTIMIZATION_DIR, filename)

            if os.path.exists(src):
                shutil.copy2(src, dst)
                print(f"✓ Stage {stage}: {filename} → todo-optimization/")
            else:
                print(f"⚠ Stage {stage}: {filename} not found (skipping)")

    # =========================================================================
    # STAGE 0: Document Structure Analysis (Policy-Agnostic)
    # =========================================================================

    def analyze_structure(self):
        """
        Run Stage 0: Document Structure Analysis to extract ALL sections including Annexures.

        This is policy-agnostic and uses flexible patterns to identify:
        - Document sections (Objective, Scope, Eligibility, etc.)
        - Annexures/Appendices with tabular data
        - Numbered clauses and rules

        Input: filename.txt (raw policy document)
        Output: stage0_structured_document.json (all sections tagged and extracted)
        """
        print("\n=== Stage 0: Document Structure Analysis ===")

        # Generic section headers (policy-agnostic patterns)
        SECTION_PATTERNS = [
            (r'^(objectives?|purpose|aim)[:\s]', 'objective'),
            (r'^(scope|applicability|coverage)[:\s]', 'scope'),
            (r'^(eligibility|who\s+does\s+this\s+apply)[:\s]', 'eligibility'),
            (r'^(general\s*rules?|norms?|terms?\s*and\s*conditions?)[:\s]', 'general_rules'),
        ]

        ANNEXURE_PATTERNS = [
            r'^(annexure|appendix|schedule|exhibit|attachment)\s*[-–]?\s*(\d+|[A-Z])[:\s]*(.*)',
        ]

        policy_file = os.path.join(BASE_DIR, "filename.txt")
        src_file = os.path.join(BASE_DIR, "stage0_structured_document.json")
        dst_file = os.path.join(FINAL_DIR, "stage0StructuredDocument.json")

        if not os.path.exists(policy_file):
            print(f"⚠ {policy_file} not found")
            return False

        try:
            # Read policy text
            with open(policy_file, 'r', encoding='utf-8') as f:
                content = f.read()

            lines = content.split('\n')

            document_info = {
                "title": "",
                "document_id": "",
                "effective_date": ""
            }

            sections = {}
            annexures = {}
            numbered_clauses = []

            # Extract document header
            for i, line in enumerate(lines[:15]):
                line = line.strip()
                if not line:
                    continue
                if i == 0:
                    document_info["title"] = line
                doc_id_match = re.search(r'(HR|Pol|Policy|Ref)[/\-]?\s*\d+', line, re.IGNORECASE)
                if doc_id_match:
                    document_info["document_id"] = doc_id_match.group(0)

            date_match = re.search(
                r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
                content, re.IGNORECASE
            )
            if date_match:
                document_info["effective_date"] = date_match.group(1)

            current_section = "unclassified"
            section_buffer = []

            in_annexure = False
            annexure_name = None
            annexure_buffer = []

            for line in lines:
                line_stripped = line.strip()

                if '\x0c' in line_stripped or not line_stripped:
                    continue

                # Check for annexure headers
                annexure_match = None
                for pattern in ANNEXURE_PATTERNS:
                    match = re.match(pattern, line_stripped, re.IGNORECASE)
                    if match:
                        annexure_match = match
                        break

                if annexure_match:
                    if in_annexure and annexure_name and annexure_buffer:
                        annexures[annexure_name] = {"content": '\n'.join(annexure_buffer), "type": "reference"}

                    annexure_name = f"{annexure_match.group(1)} {annexure_match.group(2)}".strip()
                    in_annexure = True
                    annexure_buffer = []
                    current_section = None
                    continue

                if in_annexure:
                    annexure_buffer.append(line_stripped)
                    continue

                # Check for section headers
                section_type = None
                for pattern, stype in SECTION_PATTERNS:
                    if re.match(pattern, line_stripped.lower()):
                        section_type = stype
                        break

                if section_type:
                    if section_buffer:
                        sections[current_section] = '\n'.join(section_buffer)
                    current_section = section_type
                    section_buffer = []
                    continue

                # Check for numbered clauses
                clause_match = re.match(r'^(\d+|[a-z])\s*[.)]\s+(.+)', line_stripped)
                if clause_match:
                    clause_num = clause_match.group(1)
                    clause_text = clause_match.group(2)
                    numbered_clauses.append({
                        "clauseId": f"C{clause_num}" if clause_num.isdigit() else f"C{clause_num}",
                        "text": clause_text,
                        "section": current_section
                    })
                    continue

                section_buffer.append(line_stripped)

            # Save final annexure
            if in_annexure and annexure_name and annexure_buffer:
                annexures[annexure_name] = {"content": '\n'.join(annexure_buffer), "type": "reference"}

            if section_buffer:
                sections[current_section] = '\n'.join(section_buffer)

            structure = {
                "metadata": document_info,
                "sections": sections,
                "annexures": annexures,
                "numbered_clauses": numbered_clauses
            }

            # Generate all_clauses
            all_clauses = []
            for clause in numbered_clauses:
                all_clauses.append({
                    "clauseId": clause["clauseId"],
                    "text": clause["text"],
                    "source": clause.get("section", "general"),
                    "clause_type": "numbered"
                })

            for annexure_name, annexure_data in annexures.items():
                content = annexure_data.get("content", "")
                all_clauses.append({
                    "clauseId": f"CA_{annexure_name.replace(' ', '')}_1",
                    "text": content[:500],
                    "source": annexure_name,
                    "clause_type": "annexure"
                })

            structure["all_clauses"] = all_clauses
            structure["metadata"]["total_clauses"] = len(all_clauses)
            structure["metadata"]["total_annexures"] = len(annexures)

            # Save to stage0 file and copy to final
            with open(src_file, 'w', encoding='utf-8') as f:
                json.dump(structure, f, indent=2, ensure_ascii=False)

            shutil.copy2(src_file, dst_file)

            print(f"✓ Analyzed document structure")
            print(f"✓ Total clauses: {len(all_clauses)}")
            print(f"✓ Annexures found: {len(annexures)}")
            print(f"✓ Saved to: stage0StructuredDocument.json")
            return True

        except Exception as e:
            print(f"✗ Error in Stage 0: {e}")
            return False

    # =========================================================================
    # STAGE 1: Transform to [{"clauseId": "C1", "text": "..."}]
    # =========================================================================
    
    def format_stage1(self):
        """
        Extract clauseId and elaborated_text from stage1_clauses.json
        
        Input: {
            "clauses": [
                {
                    "clause_id": "C6_1",
                    "original_text": "...",
                    "elaborated_text": "...",
                    ...
                }
            ]
        }
        
        Output: [
            {
                "clauseId": "C6_1",
                "text": "..."  (from elaborated_text)
            }
        ]
        """
        print("\n=== Processing Stage 1 ===")
        
        src_file = os.path.join(TODO_OPTIMIZATION_DIR, STAGE_FILES[1])
        dst_file = os.path.join(FINAL_DIR, OUTPUT_FILES[1])
        
        if not os.path.exists(src_file):
            print(f"⚠ {src_file} not found")
            return False
        
        try:
            with open(src_file, 'r') as f:
                data = json.load(f)
            
            clauses = data.get('clauses', [])
            
            # Transform to simplified format
            simplified = []
            for clause in clauses:
                simplified.append({
                    "clauseId": clause.get('clauseId', ''),
                    "text": clause.get('text', '')
                })
            
            # Save to final
            with open(dst_file, 'w') as f:
                json.dump(simplified, f, indent=2)
            
            print(f"✓ Formatted {len(simplified)} clauses")
            print(f"✓ Saved to: {OUTPUT_FILES[1]}")
            return True
        
        except Exception as e:
            print(f"✗ Error processing Stage 1: {e}")
            return False
    
    # =========================================================================
    # STAGE 2: Transform to [{"clauseId": "C1", "intent": "...", "confidence": 0.0}]
    # =========================================================================
    
    def format_stage2(self):
        """
        Extract clauseId, intent, confidence from stage2_classified.json
        
        Input: {
            "classified_clauses": [
                {
                    "clause_id": "C6_1",
                    "original_text": "...",
                    "elaborated_text": "...",
                    "intent": "RESTRICTION",
                    "confidence": 0.95,
                    ...
                }
            ]
        }
        
        Output: [
            {
                "clauseId": "C6_1",
                "intent": "RESTRICTION",
                "confidence": 0.95
            }
        ]
        """
        print("\n=== Processing Stage 2 ===")
        
        src_file = os.path.join(TODO_OPTIMIZATION_DIR, STAGE_FILES[2])
        dst_file = os.path.join(FINAL_DIR, OUTPUT_FILES[2])
        
        if not os.path.exists(src_file):
            print(f"⚠ {src_file} not found")
            return False
        
        try:
            with open(src_file, 'r') as f:
                data = json.load(f)
            
            clauses = data.get('classified_clauses', [])
            
            # Transform to simplified format
            simplified = []
            for clause in clauses:
                simplified.append({
                    "clauseId": clause.get('clauseId', ''),
                    "intent": clause.get('intent', 'UNKNOWN'),
                    "confidence": float(clause.get('confidence', 0.0))
                })
            
            # Save to final
            with open(dst_file, 'w') as f:
                json.dump(simplified, f, indent=2)
            
            print(f"✓ Formatted {len(simplified)} classified clauses")
            print(f"✓ Saved to: {OUTPUT_FILES[2]}")
            return True
        
        except Exception as e:
            print(f"✗ Error processing Stage 2: {e}")
            return False
    
    # =========================================================================
    # STAGE 3: Transform to [{"clauseId": "C1", "entities": {...}}]
    # =========================================================================
    
    def format_stage3(self):
        """
        Extract clauseId and entities from stage3_entities.json
        
        Input: {
            "extracted_entities": [
                {
                    "clause_id": "C6_1",
                    "entities": {
                        "distanceThreshold": "200 kms",
                        "travelMode": "Personal Car",
                        ...
                    },
                    ...
                }
            ]
        }
        
        Output: [
            {
                "clauseId": "C6_1",
                "entities": {
                    "distanceThreshold": "200 kms",
                    "travelMode": "Personal Car"
                }
            }
        ]
        """
        print("\n=== Processing Stage 3 ===")
        
        src_file = os.path.join(TODO_OPTIMIZATION_DIR, STAGE_FILES[3])
        dst_file = os.path.join(FINAL_DIR, OUTPUT_FILES[3])
        
        if not os.path.exists(src_file):
            print(f"⚠ {src_file} not found")
            return False
        
        try:
            with open(src_file, 'r') as f:
                data = json.load(f)
            
            # Handle both possible structures
            # Stage 3 output has 'extracted_clauses' not 'extracted_entities'
            entities_list = data.get('extracted_clauses') or data.get('extracted_entities') or data.get('entities') or []
            
            # Transform to simplified format
            simplified = []
            for entity_clause in entities_list:
                simplified.append({
                    "clauseId": entity_clause.get('clauseId', ''),
                    "entities": entity_clause.get('entities', {})
                })
            
            # Save to final
            with open(dst_file, 'w') as f:
               json.dump(simplified, f, indent=2)
            
            print(f"✓ Formatted {len(simplified)} entity extractions")
            print(f"✓ Saved to: {OUTPUT_FILES[3]}")
            return True
        
        except Exception as e:
            print(f"✗ Error processing Stage 3: {e}")
            return False
    
    # =========================================================================
    # STAGE 4: Transform to [{"clauseId": "C1", "ambiguous": bool, "reason": "..."}]
    # =========================================================================
    
    def format_stage4(self):
        """
        Extract clauseId, ambiguous, reason from stage4_ambiguity_flags.json
        
        Input: {
            "ambiguity_flags": [
                {
                    "clause_id": "C6_1",
                    "ambiguous": true,
                    "reason": "...",
                    "ambiguity_types": [...],
                    ...
                }
            ]
        }
        
        Output: [
            {
                "clauseId": "C6_1",
                "ambiguous": true,
                "reason": "..."
            }
        ]
        """
        print("\n=== Processing Stage 4 ===")
        
        src_file = os.path.join(TODO_OPTIMIZATION_DIR, STAGE_FILES[4])
        dst_file = os.path.join(FINAL_DIR, OUTPUT_FILES[4])
        
        if not os.path.exists(src_file):
            print(f"⚠ {src_file} not found")
            return False
        
        try:
            with open(src_file, 'r') as f:
                data = json.load(f)
            
            # Handle both list and dict formats
            if isinstance(data, list):
                flags = data
            else:
                flags = data.get('ambiguity_flags', [])
            
            # Transform to simplified format
            simplified = []
            for flag in flags:
                simplified.append({
                    "clauseId": flag.get('clauseId', ''),
                    "ambiguous": flag.get('ambiguous', False),
                    "reason": flag.get('reason', '')
                })
            
            # Save to final
            with open(dst_file, 'w') as f:
                json.dump(simplified, f, indent=2)
            
            print(f"✓ Formatted {len(simplified)} ambiguity flags")
            print(f"✓ Saved to: {OUTPUT_FILES[4]}")
            return True
        
        except Exception as e:
            print(f"✗ Error processing Stage 4: {e}")
            return False
    
    # =========================================================================
    # STAGE 5: Copy DSL rules as-is (just change filename to camelCase)
    # =========================================================================
    
    def format_stage5(self):
        """
        Copy stage5_clarified_clauses or stage6_dsl_rules.yaml to final as-is
        with camelCase filename
        """
        print("\n=== Processing Stage 5 ===")
        
        # Try both possible source files
        src_file1 = os.path.join(TODO_OPTIMIZATION_DIR, "stage5_clarified_clauses.json")
        src_file2 = os.path.join(TODO_OPTIMIZATION_DIR, "stage5_dsl_rules.yaml")
        src_file3 = os.path.join(TODO_OPTIMIZATION_DIR, "stage6_dsl_rules.yaml")
        
        src_file = None
        for candidate in [src_file2, src_file3, src_file1]:
            if os.path.exists(candidate):
                src_file = candidate
                break
        
        if not src_file:
            print(f"⚠ No stage 5 DSL file found")
            return False
        
        try:
            dst_file = os.path.join(FINAL_DIR, OUTPUT_FILES[5])
            shutil.copy2(src_file, dst_file)
            print(f"✓ Copied DSL rules (as-is)")
            print(f"✓ Saved to: {OUTPUT_FILES[5]}")
            return True
        
        except Exception as e:
            print(f"✗ Error processing Stage 5: {e}")
            return False
    
    # =========================================================================
    # STAGE 6: Transform to [{"clauseId": "C1", "rationale": "...", "confidence": 0.0}]
    # =========================================================================
    
    # def format_stage6(self):
    #     """
    #     Extract clauseId, rationale, confidence from confidence/stage6 file
        
    #     Input: {
    #         "confidence_scores": [
    #             {
    #                 "clause_id": "C6_1",
    #                 "rationale": "...",
    #                 "confidence": 0.95,
    #                 ...
    #             }
    #         ]
    #     }
        
    #     Output: [
    #         {
    #             "clauseId": "C6_1",
    #             "rationale": "...",
    #             "confidence": 0.95
    #         }
    #     ]
    #     """
    #     print("\n=== Processing Stage 6 ===")
        
    #     # Try multiple possible source file names
    #     possible_sources = [
    #         os.path.join(TODO_OPTIMIZATION_DIR, STAGE_FILES[7]),  # stage7_confidence_rationale.json
    #         os.path.join(TODO_OPTIMIZATION_DIR, "stage6_confidence.json"),
    #         os.path.join(TODO_OPTIMIZATION_DIR, "stage6_rationale.json"),
    #     ]
        
    #     src_file = None
    #     for candidate in possible_sources:
    #         if os.path.exists(candidate):
    #             src_file = candidate
    #             break
        
    #     if not src_file:
    #         print(f"⚠ No stage 6/7 confidence file found")
    #         return False
        
    #     try:
    #         with open(src_file, 'r') as f:
    #             data = json.load(f)
            
    #         # Handle different possible structures
    #         scores = data.get('confidence_scores') or data.get('rationales') or data
    #         if not isinstance(scores, list):
    #             scores = [scores]
            
    #         # Transform to simplified format
    #         simplified = []
    #         for score in scores:
    #             if isinstance(score, dict):
    #                 simplified.append({
    #                     "clauseId": score.get('clause_id', '') or score.get('clauseId', ''),
    #                     "rationale": score.get('rationale', score.get('reasoning', '')),
    #                     "confidence": float(score.get('confidence', 0.0))
    #                 })
            
    #         # Save to final
    #         dst_file = os.path.join(FINAL_DIR, OUTPUT_FILES[6])
    #         with open(dst_file, 'w') as f:
    #             json.dump(simplified, f, indent=2)
            
    #         print(f"✓ Formatted {len(simplified)} confidence scores")
    #         print(f"✓ Saved to: {OUTPUT_FILES[6]}")
    #         return True
        
    #     except Exception as e:
    #         print(f"✗ Error processing Stage 6: {e}")
    #         return False
    
    # =========================================================================
    # STAGE 8: Normalize to canonical policy format
    # =========================================================================
    
    def _entity_to_fact(self, entity_key: str) -> str:
        """
        Convert entity key to fact notation.
        
        Examples:
            travelMode → travel.mode
            distanceThreshold → travel.distance
            accommodationType → accommodation.type
            employeeLevel → employee.level
        """
        # Handle common entity prefixes
        prefix_mappings = {
            'travel': 'travel',
            'accommodation': 'accommodation',
            'employee': 'employee',
            'claim': 'claim',
            'bill': 'bill',
            'settlement': 'settlement',
            'reimbursement': 'reimbursement',
            'distance': 'travel.distance',
            'percentage': 'value.percentage',
            'duration': 'time.duration',
            'deadline': 'time.deadline',
            'group': 'group.size',
            'enforcement': 'policy.enforcement',
        }
        
        for prefix, fact in prefix_mappings.items():
            if entity_key.lower().startswith(prefix):
                # Extract the rest of the key
                rest = entity_key[len(prefix):]
                # Convert camelCase to lowercase with underscores
                rest = ''.join(['_' + c.lower() if c.isupper() else c for c in rest]).strip('_')
                if rest:
                    return f"{fact}.{rest}"
                return fact
        
        # Default: convert camelCase to dot notation
        return ''.join(['.' + c.lower() if c.isupper() else c for c in entity_key]).strip('.')
    
    def _get_threshold_entity(self, entities: dict) -> tuple:
        """
        Extract threshold-related entity for the 'what' constraint.
        
        Returns: (fact, value)
        """
        threshold_entities = [
            'distanceThreshold', 'maxDuration', 'minWorkDuration',
            'maxClaimPercentage', 'percentageClaim', 'submissionDeadline',
            'effectiveDate', 'minGroupSize', 'monetaryAmount'
        ]
        
        for key in threshold_entities:
            if key in entities:
                fact = self._entity_to_fact(key)
                return fact, entities[key]
        
        # Default: use first entity value
        if entities:
            first_key = list(entities.keys())[0]
            return self._entity_to_fact(first_key), entities[first_key]
        
        return "policy.condition", "unknown"
    
    def normalize_policies(self):
        """
        Transform extracted clauses to normalized canonical policy format.
        
        Input: Combined data from stage2 (intent) and stage3 (entities)
        Output: stage8_normalized_policies.json in canonical form
        
        Canonical Format:
        {
            "policyId": "POL-C82_1",
            "name": "LIMIT Policy",
            "scope": {
                "tenantId": "DEFAULT",
                "appliesTo": {"roles": ["EMPLOYEE"], "locations": []}
            },
            "when": [{"fact": "travel.mode", "operator": "EQUALS", "value": "Personal Car"}],
            "what": {"constraint": {"fact": "travel.distance", "operator": "MUST_NOT_EXCEED", "value": "200 KMS"}},
            "outcome": {"enforcement": "WARN", "message": "LIMIT - No official Travel..."},
            "metadata": {"source": "AI_ASSISTED", "version": 1}
        }
        """
        print("\n=== Processing Stage 8: Normalizing Policies ===")
        
        # Read stage 2 for intent classification
        stage2_file = os.path.join(TODO_OPTIMIZATION_DIR, STAGE_FILES[2])
        # Read stage 3 for entities
        stage3_file = os.path.join(TODO_OPTIMIZATION_DIR, STAGE_FILES[3])
        
        if not os.path.exists(stage2_file):
            print(f"⚠ {stage2_file} not found")
            return False
        
        if not os.path.exists(stage3_file):
            print(f"⚠ {stage3_file} not found")
            return False
        
        try:
            # Load stage 2 data
            with open(stage2_file, 'r') as f:
                stage2_data = json.load(f)
            clauses = stage2_data.get('classified_clauses', [])
            
            # Load stage 3 data
            with open(stage3_file, 'r') as f:
                stage3_data = json.load(f)
            entities_list = stage3_data.get('extracted_clauses', [])
            
            # Create entities lookup
            entities_lookup = {}
            for item in entities_list:
                clause_id = item.get('clauseId', '')
                entities_lookup[clause_id] = item.get('entities', {})
            
            # Normalize each clause
            normalized_policies = []
            
            for clause in clauses:
                clause_id = clause.get('clauseId', '')
                intent = clause.get('intent', 'INFORMATIONAL')
                text = clause.get('text', '')
                entities = entities_lookup.get(clause_id, {})
                
                # Get enforcement and operator from intent
                enforcement = INTENT_TO_ENFORCEMENT.get(intent, 'INFO')
                constraint_operator = INTENT_TO_OPERATOR.get(intent, 'IS')
                
                # Build 'when' conditions from entities
                when_conditions = []
                for entity_key, entity_value in entities.items():
                    # Skip threshold entities (they go in 'what')
                    if entity_key in ['distanceThreshold', 'maxDuration', 'minWorkDuration',
                                     'maxClaimPercentage', 'percentageClaim', 'submissionDeadline',
                                     'effectiveDate', 'minGroupSize', 'monetaryAmount']:
                        continue
                    
                    fact = self._entity_to_fact(entity_key)
                    when_conditions.append({
                        "fact": fact,
                        "operator": "EQUALS",
                        "value": entity_value
                    })
                
                # Build 'what' constraint from threshold entities
                threshold_fact, threshold_value = self._get_threshold_entity(entities)
                
                what_constraint = {
                    "constraint": {
                        "fact": threshold_fact,
                        "operator": constraint_operator,
                        "value": threshold_value
                    }
                }
                
                # Build scope from employee-related entities
                employee_level = entities.get('employeeLevel', '')
                roles = ["EMPLOYEE"]
                if employee_level:
                    roles.append(employee_level)
                
                # Build appliesTo dict (only include locations if not empty)
                applies_to = {"roles": roles}
                
                # Create normalized policy
                policy = {
                    "policyId": f"POL-{clause_id}",
                    "name": f"{intent} Policy",
                    "scope": {
                        "tenantId": "DEFAULT",
                        "appliesTo": applies_to
                    },
                    "when": when_conditions,
                    "what": what_constraint,
                    "outcome": {
                        "enforcement": enforcement,
                        "message": f"{intent} - {text[:100]}{'...' if len(text) > 100 else ''}"
                    },
                    "metadata": {
                        "source": "AI_ASSISTED",
                        "version": 1
                    }
                }
                
                normalized_policies.append(policy)
            
            # Save to final
            dst_file = os.path.join(FINAL_DIR, OUTPUT_FILES[8])
            with open(dst_file, 'w') as f:
                json.dump(normalized_policies, f, indent=2)
            
            print(f"✓ Normalized {len(normalized_policies)} policies")
            print(f"✓ Saved to: {OUTPUT_FILES[8]}")
            return True
        
        except Exception as e:
            print(f"✗ Error processing Stage 8: {e}")
            return False
    
    # =========================================================================
    # MAIN EXECUTION
    # =========================================================================
    
    def format_all(self):
        """Process all stages"""
        print("\n" + "="*70)
        print("OUTPUT FORMATTER: Transforming Pipeline Outputs")
        print("="*70)

        self.ensure_directories()

        # Stage 0: Document Structure Analysis (first)
        results = {
            'stage0': self.analyze_structure(),
        }

        self.copy_to_todo_optimization()

        results.update({
            'stage1': self.format_stage1(),
            'stage2': self.format_stage2(),
            'stage3': self.format_stage3(),
            'stage4': self.format_stage4(),
            'stage5': self.format_stage5(),
            # 'stage6': self.format_stage6(),
            'stage8': self.normalize_policies(),
        })

        self.print_summary(results)
        return results
    
    def print_summary(self, results):
        """Print summary of formatting results"""
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        
        print(f"\nDirectory Structure Created:")
        print(f"  todo-optimization/  (intermediate files, original format)")
        print(f"  final/              (cleaned files, optimized format)")
        
        print(f"\nStage Processing Results:")
        for stage, success in results.items():
            status = "✓ SUCCESS" if success else "⚠ SKIPPED"
            print(f"  {stage}: {status}")
        
        print(f"\nOutput Files (in final/ directory):")
        for stage, filename in OUTPUT_FILES.items():
            filepath = os.path.join(FINAL_DIR, filename)
            exists = "✓" if os.path.exists(filepath) else "✗"
            print(f"  {exists} {filename}")
        
        print(f"\nNext Steps:")
        print(f"  1. Review files in: {FINAL_DIR}")
        print(f"  2. Original intermediate files: {TODO_OPTIMIZATION_DIR}")
        print(f"  3. Use final/ files for downstream processing")
        print("\n" + "="*70 + "\n")


def main():
    """Main entry point"""
    formatter = OutputFormatter()
    formatter.format_all()


if __name__ == "__main__":
    main()

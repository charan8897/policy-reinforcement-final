#!/usr/bin/env python3
"""
Semantic Condition Matcher - JSON Output Only
No console output - direct JSON response for all payload fields
"""

import json
import sys
import re
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    USE_EMBEDDINGS = True
except ImportError:
    USE_EMBEDDINGS = False

REGO_DIR = "/home/hutech/Documents/docupolicy/opa_bundles"

def extract_value_type(value_str):
    """Determine if a value is numeric, string, boolean, etc."""
    if value_str is None:
        return 'unknown'
    
    value_str = str(value_str).strip()
    
    try:
        float(value_str)
        return 'numeric'
    except ValueError:
        pass
    
    if value_str.lower() in ['true', 'false']:
        return 'boolean'
    
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        return 'string'
    
    return 'string'

def infer_field_value_types(field, conditions):
    """Infer the expected value type(s) for a rego field"""
    value_types = set()
    
    for cond in conditions:
        if cond['field'] == field:
            pattern = rf'input\.{field}\s*==\s*(["\']?)([^,\s]+)\1'
            matches = re.findall(pattern, cond['context'])
            
            for quote, value in matches:
                vtype = extract_value_type(value)
                value_types.add(vtype)
    
    return value_types if value_types else {'unknown'}

def extract_rego_fields():
    """Extract all unique input.xxx field names"""
    rego_fields = set()
    
    for rego_file in Path(REGO_DIR).rglob("*.rego"):
        with open(rego_file, 'r', errors='ignore') as f:
            content = f.read()
            matches = re.findall(r'input\.([a-zA-Z_][a-zA-Z0-9_]*)', content)
            rego_fields.update(matches)
    
    return sorted(list(rego_fields))

def extract_rego_conditions():
    """Extract all input.xxx fields with their conditions"""
    conditions = []
    
    for rego_file in Path(REGO_DIR).rglob("*.rego"):
        with open(rego_file, 'r', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                input_matches = re.findall(r'input\.([a-zA-Z_][a-zA-Z0-9_]*)', line)
                
                for field in input_matches:
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context = '\n'.join(lines[start:end])
                    
                    conditions.append({
                        'file': str(rego_file),
                        'field': field,
                        'context': context.strip(),
                        'line_number': i + 1
                    })
    
    return conditions

def compute_similarity(query, candidates):
    """Compute cosine similarity between query and candidates"""
    if not USE_EMBEDDINGS:
        return None
    
    model = SentenceTransformer("all-MiniLM-L6-v2")
    all_texts = [query] + candidates
    embeddings = model.encode(all_texts, convert_to_numpy=True, show_progress_bar=False)
    similarities = cosine_similarity([embeddings[0]], embeddings[1:])[0]
    
    return similarities.tolist()

def find_matching_conditions_for_field(payload_field, payload_value, payload_value_type, rego_fields, conditions):
    """Find matching conditions for a single payload field"""
    
    # Prepare search query
    if payload_value is not None and isinstance(payload_value, str) and len(str(payload_value)) > 10:
        search_query = f"{payload_field} {payload_value}"
    else:
        search_query = payload_field
    
    # Score fields
    if USE_EMBEDDINGS:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        similarities = compute_similarity(search_query, rego_fields)
        
        scored = []
        for i, rego_field in enumerate(rego_fields):
            similarity = similarities[i] if similarities else 0
            
            # Apply type filtering
            type_match = True
            if payload_value_type and payload_value_type != 'unknown':
                field_types = infer_field_value_types(rego_field, conditions)
                if 'unknown' not in field_types:
                    if payload_value_type in field_types:
                        similarity *= 1.2
                    else:
                        similarity *= 0.5
                        type_match = False
            
            if type_match or payload_value_type == 'unknown':
                scored.append((rego_field, similarity))
        
        scored.sort(key=lambda x: -x[1])
    else:
        scored = []
    
    # Get top 3 matches with detailed conditions
    results = []
    for rego_field, score in scored[:3]:
        field_conditions = [c for c in conditions if c['field'] == rego_field]
        
        for cond in field_conditions[:2]:
            context = cond['context']
            pattern = rf'input\.{rego_field}\s*==\s*(["\']?)([^,\n' + '}' + r']+)\1'
            value_match = re.search(pattern, context)
            extracted_value = value_match.group(2) if value_match else "unknown"
            
            results.append({
                "rego_field": rego_field,
                "payload_field": payload_field,
                "payload_value": payload_value,
                "rego_value": extracted_value.strip().strip('"\''),
                "condition": f"input.{rego_field} == {extracted_value}",
                "similarity": round(float(score), 4),
                "status": "matched",
                "file": Path(cond['file']).name,
                "line": cond['line_number']
            })
    
    return results

def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    
    input_arg = sys.argv[1]
    payload_fields = {}
    
    # Parse JSON input
    if input_arg.startswith('{'):
        try:
            payload_fields = json.loads(input_arg)
        except json.JSONDecodeError:
            sys.exit(1)
    else:
        payload_fields = {input_arg: None}
    
    # Extract rego data once
    rego_fields = extract_rego_fields()
    all_conditions = extract_rego_conditions()
    
    # Collect all results
    all_results = []
    
    for payload_field, payload_value in payload_fields.items():
        payload_value_type = extract_value_type(payload_value) if payload_value is not None else 'unknown'
        
        matches = find_matching_conditions_for_field(
            payload_field, 
            payload_value, 
            payload_value_type,
            rego_fields,
            all_conditions
        )
        
        all_results.extend(matches)
    
    # Output only JSON
    if all_results:
        print(json.dumps(all_results, indent=2))
    else:
        print(json.dumps([]))

if __name__ == "__main__":
    main()

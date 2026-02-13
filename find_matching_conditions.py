#!/usr/bin/env python3
"""
Dynamic Condition Matcher with Cosine Similarity - Direct Rego Search
No hardcoded mappings - uses sentence-transformers for semantic similarity

Usage: 
    python find_matching_conditions.py "qualification_standard"
    python find_matching_conditions.py "assigned_validator"
    python find_matching_conditions.py "authorizing_entity"

This script directly analyzes rego files to find matching conditions.
"""

import json
import sys
import os
import re
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    USE_EMBEDDINGS = True
except ImportError:
    USE_EMBEDDINGS = False
    print("Warning: sentence-transformers not installed. Using fallback string matching.")

# Configuration
REGO_DIR = "/home/hutech/Documents/docupolicy/opa_bundles"

def extract_value_type(value_str):
    """Determine if a value is numeric, string, boolean, etc."""
    if value_str is None:
        return 'unknown'
    
    value_str = str(value_str).strip()
    
    # Check if numeric
    try:
        float(value_str)
        return 'numeric'
    except ValueError:
        pass
    
    # Check if boolean
    if value_str.lower() in ['true', 'false']:
        return 'boolean'
    
    # Check if quoted string
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        return 'string'
    
    # Default to string
    return 'string'

def infer_field_value_types(field, conditions):
    """Infer the expected value type(s) for a rego field by examining its conditions"""
    value_types = set()
    
    for cond in conditions:
        if cond['field'] == field:
            # Look for patterns like: input.field == value
            pattern = rf'input\.{field}\s*==\s*(["\']?)([^,\s]+)\1'
            matches = re.findall(pattern, cond['context'])
            
            for quote, value in matches:
                vtype = extract_value_type(value)
                value_types.add(vtype)
    
    return value_types if value_types else {'unknown'}

def extract_rego_conditions():
    """Extract all input.xxx fields with their conditions from rego files"""
    conditions = []
    
    for rego_file in Path(REGO_DIR).rglob("*.rego"):
        with open(rego_file, 'r') as f:
            content = f.read()
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                # Find lines with input.xxx patterns
                input_matches = re.findall(r'input\.([a-zA-Z_][a-zA-Z0-9_]*)', line)
                
                for field in input_matches:
                    # Get context (surrounding lines for better understanding)
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

def extract_rego_fields():
    """Extract all unique input.xxx field names from rego files"""
    rego_fields = set()
    
    for rego_file in Path(REGO_DIR).rglob("*.rego"):
        with open(rego_file, 'r') as f:
            content = f.read()
            # Find all input.xxx patterns
            matches = re.findall(r'input\.([a-zA-Z_][a-zA-Z0-9_]*)', content)
            rego_fields.update(matches)
    
    return sorted(rego_fields)

def get_embedding(texts, model=None):
    """Generate embeddings using sentence-transformers"""
    if model is None:
        if USE_EMBEDDINGS:
            model = SentenceTransformer("all-MiniLM-L6-v2")
        else:
            return None
    
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings

def compute_similarity(query, candidates, model=None):
    """Compute cosine similarity between query and candidates"""
    if not USE_EMBEDDINGS:
        return None
    
    # Generate embeddings
    all_texts = [query] + candidates
    embeddings = get_embedding(all_texts, model)
    
    # Compute cosine similarity
    similarities = cosine_similarity([embeddings[0]], embeddings[1:])[0]
    
    return similarities.tolist()

def fuzzy_match_score(payload_field, rego_field):
    """Fallback string matching when embeddings unavailable"""
    p = payload_field.lower().replace('_', '')
    r = rego_field.lower().replace('_', '')
    
    score = 0
    
    # Exact substring match
    if p in r or r in p:
        score += 100
    
    # Word overlap
    p_words = set(payload_field.lower().split('_'))
    r_words = set(rego_field.lower().split('_'))
    common_words = p_words & r_words
    score += len(common_words) * 40
    
    # Partial word match
    for pw in p_words:
        if len(pw) > 2:
            for rw in r_words:
                if len(rw) > 2 and (pw[:3] == rw[:3] or pw in rw):
                    score += 20
    
    return score

def find_matching_conditions(payload_field, payload_value=None, payload_value_type=None):
    """Main function to find matching conditions directly from rego files
    
    Args:
        payload_field: Field name to search for
        payload_value: Optional value to infer type from
        payload_value_type: Explicit value type ('numeric', 'string', 'boolean')
    """
    print(f"\n{'='*70}")
    print(f"🔍 Searching for: {payload_field}")
    if payload_value is not None:
        print(f"   Value: {payload_value} (type: {payload_value_type})")
    print(f"{'='*70}\n")
    
    # Extract rego fields and conditions
    print("Step 1: Extracting rego fields and conditions...")
    rego_fields = extract_rego_fields()
    conditions = extract_rego_conditions()
    print(f"Found {len(rego_fields)} unique fields and {len(conditions)} total occurrences\n")
    
    # Compute similarity scores
    print("Step 2: Computing semantic similarity scores...")
    
    if USE_EMBEDDINGS:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        similarities = compute_similarity(payload_field, rego_fields, model)
        
        # Create scored list with type filtering
        scored = []
        for i, rego_field in enumerate(rego_fields):
            similarity = similarities[i] if similarities else 0
            
            # Apply type filtering if payload value type is known
            type_match = True
            if payload_value_type and payload_value_type != 'unknown':
                field_types = infer_field_value_types(rego_field, conditions)
                # Boost score if types match, reduce if they don't
                if 'unknown' not in field_types:
                    if payload_value_type in field_types:
                        similarity *= 1.2  # 20% boost for type match
                    else:
                        similarity *= 0.5  # 50% penalty for type mismatch
                        type_match = False
            
            if type_match or payload_value_type == 'unknown':
                scored.append((rego_field, similarity))
        
        # Sort by score
        scored.sort(key=lambda x: -x[1])
    else:
        # Fallback to string matching
        scored = []
        for rego_field in rego_fields:
            score = fuzzy_match_score(payload_field, rego_field)
            scored.append((rego_field, score))
        scored.sort(key=lambda x: -x[1])
    
    # Show top matches
    print(f"\n📊 Top 10 semantically similar rego fields:\n")
    for i, (field, score) in enumerate(scored[:10], 1):
        if USE_EMBEDDINGS:
            print(f"  {i:2}. {field:50} (similarity: {score:.4f})")
        else:
            print(f"  {i:2}. {field:50} (score: {score})")
    
    # Find conditions for top matching fields
    print(f"\n📝 Matching Conditions Found:\n")
    
    threshold = 0.3 if USE_EMBEDDINGS else 50
    top_fields = [s[0] for s in scored if s[1] > threshold][:10]
    
    if not top_fields:
        top_fields = [s[0] for s in scored[:3]]
    
    total_conditions = 0
    
    for field in top_fields:
        # Find all conditions for this field
        field_conditions = [c for c in conditions if c['field'] == field]
        
        if field_conditions:
            print(f"  ── Field: {field} ──")
            
            for cond in field_conditions[:5]:  # Show up to 5 occurrences
                print(f"      File: {Path(cond['file']).name}")
                print(f"      Line: {cond['line_number']}")
                print(f"      Context: {cond['context'][:100]}...")
                print()
                total_conditions += 1
    
    return {
        'payload_field': payload_field,
        'scored_fields': scored[:10],
        'total_conditions': total_conditions
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python find_matching_conditions.py <payload_field>")
        print("       python find_matching_conditions.py '{\"payload_field\": \"description\"}'")
        print()
        print("Examples:")
        print("  python find_matching_conditions.py qualification_standard")
        print("  python find_matching_conditions.py '{\"qualification_standard\": \"Job band and grade\"}'")
        print("  python find_matching_conditions.py '{\"assigned_validator\": \"Person who validates the request\"}'")
        sys.exit(1)
    
    # Parse input - could be string or JSON
    input_arg = sys.argv[1]
    payload_fields = {}
    
    # Try to parse as JSON
    if input_arg.startswith('{'):
        try:
            input_json = json.loads(input_arg)
            if isinstance(input_json, dict) and len(input_json) > 0:
                # Check if it's a single field or multiple fields
                if len(input_json) == 1 and not any(isinstance(v, dict) for v in input_json.values()):
                    # Single field format: {"field_name": value}
                    payload_fields = input_json
                else:
                    # Could be full payload with multiple fields
                    payload_fields = input_json
                
                print(f"[*] Parsed JSON input with {len(payload_fields)} field(s):\n")
                for field, value in payload_fields.items():
                    vtype = extract_value_type(value)
                    print(f"    - {field}: {value} (type: {vtype})")
                print()
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON format")
            sys.exit(1)
    else:
        # Plain string argument
        payload_fields = {input_arg: None}
    
    # Process each field
    all_results = []
    
    for payload_field, payload_value in payload_fields.items():
        field_description = None
        payload_value_type = 'unknown'
        
        if payload_value is not None:
            # Determine value type
            payload_value_type = extract_value_type(payload_value)
            
            # For string descriptions, use as field_description
            if isinstance(payload_value, str) and len(str(payload_value)) > 10:
                field_description = payload_value
        
        # Use both field name and description for better matching
        if field_description:
            search_query = f"{payload_field} {field_description}"
        else:
            search_query = payload_field
        
        result = find_matching_conditions(search_query, payload_value, payload_value_type)
        result['original_field'] = payload_field
        result['original_value'] = payload_value
        result['original_value_type'] = payload_value_type
        all_results.append(result)
    
    # Print summary for all fields
    print(f"\n{'='*70}")
    print("📋 SUMMARY - ALL PAYLOAD FIELDS")
    print(f"{'='*70}\n")
    print(f"Total fields processed: {len(all_results)}\n")
    
    for idx, result in enumerate(all_results, 1):
        print(f"{idx}. Payload Field: {result['original_field']}")
        if result['original_value'] is not None:
            print(f"   Value: {result['original_value']} (type: {result['original_value_type']})")
        print(f"   Top Match: {result['scored_fields'][0][0]} (similarity: {result['scored_fields'][0][1]:.4f})")
        print(f"   Total Conditions Found: {result['total_conditions']}")
        print()
    
    # Optional: Show detailed matching for each field
    print(f"\n{'='*70}")
    print("📝 DETAILED MATCHING")
    print(f"{'='*70}")
    
    # Extract conditions once for reuse
    all_conditions = extract_rego_conditions()
    
    for result in all_results:
        print(f"\n🔍 {result['original_field']}:")
        print(f"   Top 3 Matching Rego Fields:")
        
        detailed_matches = []
        
        for i, (field, score) in enumerate(result['scored_fields'][:3], 1):
            if USE_EMBEDDINGS:
                print(f"   {i}. {field} (similarity: {score:.4f})")
            else:
                print(f"   {i}. {field} (score: {score})")
            
            # Find actual conditions for this field
            field_conditions = [c for c in all_conditions if c['field'] == field]
            
            if field_conditions:
                for cond in field_conditions[:2]:  # Show up to 2 conditions per field
                    # Extract value from context
                    context = cond['context']
                    
                    # Try to extract value from condition
                    pattern = rf'input\.{field}\s*==\s*(["\']?)([^,\n' + '}' + r']+)\1'
                    value_match = re.search(pattern, context)
                    extracted_value = value_match.group(2) if value_match else "unknown"
                    
                    # Determine if it matches the payload value type
                    status = "matched"
                    if result['original_value'] is not None:
                        # Simple check: if types don't align, mark as different
                        if result['original_value_type'] == 'numeric' and extracted_value == 'unknown':
                            status = "type_mismatch"
                        elif result['original_value_type'] == 'string' and extracted_value == 'unknown':
                            status = "type_mismatch"
                    
                    detailed_matches.append({
                        "rego_field": field,
                        "payload_field": result['original_field'],
                        "payload_value": result['original_value'],
                        "rego_value": extracted_value.strip().strip('"\''),
                        "condition": f"input.{field} == {extracted_value}",
                        "status": status,
                        "similarity": f"{score:.4f}",
                        "line_number": cond['line_number'],
                        "file": Path(cond['file']).name
                    })
        
        # Print JSON format below the field matches
        if detailed_matches:
            print(f"\n   Matching Conditions (JSON):")
            print(f"   ```json")
            for match in detailed_matches:
                print(f"   {{")
                print(f"       \"rego_field\": \"{match['rego_field']}\",")
                print(f"       \"payload_field\": \"{match['payload_field']}\",")
                print(f"       \"payload_value\": {json.dumps(match['payload_value'])},")
                print(f"       \"rego_value\": \"{match['rego_value']}\",")
                print(f"       \"condition\": \"{match['condition']}\",")
                print(f"       \"similarity\": {match['similarity']},")
                print(f"       \"status\": \"{match['status']}\",")
                print(f"       \"file\": \"{match['file']}\",")
                print(f"       \"line\": {match['line_number']}")
                print(f"   }},")
            print(f"   ```")

if __name__ == "__main__":
    main()

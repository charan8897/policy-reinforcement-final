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

def find_matching_conditions(payload_field):
    """Main function to find matching conditions directly from rego files"""
    print(f"\n{'='*70}")
    print(f"🔍 Searching for: {payload_field}")
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
        
        # Create scored list
        scored = []
        for i, rego_field in enumerate(rego_fields):
            score = similarities[i] if similarities else 0
            scored.append((rego_field, score))
        
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
        print()
        print("Examples:")
        print("  python find_matching_conditions.py qualification_standard")
        print("  python find_matching_conditions.py assigned_validator")
        print("  python find_matching_conditions.py authorizing_entity")
        print("  python find_matching_conditions.py distance_threshold")
        sys.exit(1)
    
    payload_field = sys.argv[1]
    result = find_matching_conditions(payload_field)
    
    print(f"\n{'='*70}")
    print("📋 SUMMARY")
    print(f"{'='*70}")
    print(f"  Payload Field:    {result['payload_field']}")
    print(f"  Total Conditions: {result['total_conditions']}")
    print()
    print("  Top Matching Fields:")
    for i, (field, score) in enumerate(result['scored_fields'][:5], 1):
        if USE_EMBEDDINGS:
            print(f"    {i}. {field} (similarity: {score:.4f})")
        else:
            print(f"    {i}. {field} (score: {score})")
    print()

if __name__ == "__main__":
    main()

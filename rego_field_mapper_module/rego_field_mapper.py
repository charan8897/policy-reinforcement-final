#!/usr/bin/env python3

"""
Rego Field Mapper Integration Module
Easy-to-use wrapper for finding matching rego fields for payload fields
Designed to integrate with stage11_enforcement_api.py and similar enforcement systems

Usage in your code:
    from rego_field_mapper import map_payload_to_rego_field, map_json_payload
    
    # Single field
    result = map_payload_to_rego_field("authorizing_entity", top_k=3)
    for field in result:
        print(f"input.{field.field_name} (score: {field.score})")
    
    # JSON payload
    import json
    payload_json = '{"authorizing_entity": "Senior Manager", "distance_threshold": 200}'
    mapped = map_json_payload(payload_json)
"""

import os
import sys
import json
from typing import List, Optional, Dict, Any, Union
from dataclasses import asdict
from find_rego_fields import RegoFieldMatcher, RegoField


# Singleton instance
_matcher_instance: Optional[RegoFieldMatcher] = None


def initialize_matcher(rego_dir: str = "opa_bundles", use_gemini: bool = True) -> RegoFieldMatcher:
    """Initialize the matcher (call once at startup)"""
    global _matcher_instance
    _matcher_instance = RegoFieldMatcher(rego_dir=rego_dir, use_gemini=use_gemini)
    return _matcher_instance


def get_matcher() -> RegoFieldMatcher:
    """Get or create the matcher singleton"""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = RegoFieldMatcher()
    return _matcher_instance


def map_payload_to_rego_field(
    payload_field: str,
    top_k: int = 3,
    use_gemini: Optional[bool] = None
) -> List[RegoField]:
    """
    Map a payload field to matching rego input.xxx fields
    
    Args:
        payload_field: The payload field name to map (e.g., "authorizing_entity")
        top_k: Number of top matches to return (default: 3)
        use_gemini: Override gemini setting (None = use default)
    
    Returns:
        List of RegoField objects with matched fields and scores
    
    Example:
        results = map_payload_to_rego_field("authorizing_entity")
        for field in results:
            print(f"input.{field.field_name}")
    """
    matcher = get_matcher()
    return matcher.match_fields(payload_field, top_k=top_k)


def map_payload_batch(
    payload_fields: List[str],
    top_k: int = 3
) -> dict:
    """
    Map multiple payload fields at once
    
    Args:
        payload_fields: List of payload field names
        top_k: Number of top matches per field
    
    Returns:
        Dictionary mapping payload_field -> List[RegoField]
    
    Example:
        results = map_payload_batch(["authorizing_entity", "reimbursement_ceiling"])
        for payload, fields in results.items():
            print(f"{payload}: {[f.field_name for f in fields]}")
    """
    matcher = get_matcher()
    return {
        field: matcher.match_fields(field, top_k=top_k)
        for field in payload_fields
    }


def get_best_match(payload_field: str) -> Optional[RegoField]:
    """
    Get the single best matching rego field
    
    Args:
        payload_field: The payload field to map
    
    Returns:
        The best RegoField match, or None if no match found
    
    Example:
        best = get_best_match("authorizing_entity")
        if best:
            print(f"Best match: input.{best.field_name}")
    """
    results = map_payload_to_rego_field(payload_field, top_k=1)
    return results[0] if results else None


def get_field_info(field_name: str) -> dict:
    """
    Get information about a specific rego field
    
    Args:
        field_name: The rego field name (without input. prefix)
    
    Returns:
        Dictionary with field info
    
    Example:
        info = get_field_info("validationauthority")
        print(info['context'])
    """
    matcher = get_matcher()
    context = matcher.get_field_context(field_name)
    return {
        'field_name': field_name,
        'full_name': f"input.{field_name}",
        'context': context
    }


def print_mapping_report(payload_fields: List[str], top_k: int = 3):
    """
    Print a formatted mapping report for multiple payload fields
    
    Args:
        payload_fields: List of payload fields to map
        top_k: Number of top matches per field
    """
    results = map_payload_batch(payload_fields, top_k=top_k)
    
    print("\n" + "="*60)
    print("PAYLOAD FIELD TO REGO FIELD MAPPING REPORT")
    print("="*60 + "\n")
    
    for payload_field, matches in results.items():
        print(f"{payload_field}:")
        if not matches:
            print("  ✗ No matches found")
        else:
            for i, match in enumerate(matches, 1):
                print(f"  [{i}] input.{match.field_name} (score: {match.score})")
                if match.context:
                    print(f"      Context: {match.context[:70]}...")
        print()


def map_json_payload(
    payload_json: Union[str, Dict],
    top_k: int = 3,
    include_values: bool = True
) -> Dict[str, Any]:
    """
    Map a complete JSON payload to rego fields with values
    
    Args:
        payload_json: JSON string or dictionary with payload fields and values
        top_k: Number of top matches per field (default: 3)
        include_values: Include original values in output (default: True)
    
    Returns:
        Dictionary with mapping results including values and matched fields
    
    Example:
        payload = {
            "authorizing_entity": "Senior Manager",
            "reimbursement_ceiling": 125,
            "distance_threshold": 200
        }
        result = map_json_payload(payload)
        for field_name, mapping in result.items():
            print(f"{field_name}: {mapping['value']} → input.{mapping['rego_field']}")
    """
    # Parse JSON if string
    if isinstance(payload_json, str):
        try:
            payload_dict = json.loads(payload_json)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {str(e)}"}
    else:
        payload_dict = payload_json
    
    matcher = get_matcher()
    results = {}
    
    for payload_field, value in payload_dict.items():
        # Find matches
        matches = matcher.match_fields(payload_field, top_k=top_k)
        
        # Get best match
        best_match = matches[0] if matches else None
        
        # Build result
        field_result = {
            "original_payload_field": payload_field,
            "payload_value": value,
            "matches": []
        }
        
        if best_match:
            field_result["best_match"] = {
                "rego_field": f"input.{best_match.field_name}",
                "field_name": best_match.field_name,
                "score": best_match.score,
                "context": best_match.context
            }
        
        # Add all matches
        for match in matches:
            field_result["matches"].append({
                "rego_field": f"input.{match.field_name}",
                "field_name": match.field_name,
                "score": match.score,
                "context": match.context
            })
        
        results[payload_field] = field_result
    
    return results


def map_json_payload_to_opa_input(
    payload_json: Union[str, Dict],
    top_k: int = 1
) -> Dict[str, Any]:
    """
    Convert a JSON payload directly to OPA input conditions
    
    Uses best match for each payload field and maps values to rego field names
    
    Args:
        payload_json: JSON payload with fields and values
        top_k: Number of matches to consider (default: 1 for best match only)
    
    Returns:
        Dictionary ready for OPA evaluation with input.xxx keys
    
    Example:
        payload = {
            "authorizing_entity": "Senior Manager",
            "distance_threshold": 200
        }
        opa_input = map_json_payload_to_opa_input(payload)
        # Returns: {"input.validationauthority": "Senior Manager", "input.deputationdurationthreshold": 200}
    """
    # Parse JSON if string
    if isinstance(payload_json, str):
        try:
            payload_dict = json.loads(payload_json)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {str(e)}"}
    else:
        payload_dict = payload_json
    
    matcher = get_matcher()
    opa_input = {}
    
    for payload_field, value in payload_dict.items():
        matches = matcher.match_fields(payload_field, top_k=top_k)
        
        if matches:
            best_match = matches[0]
            rego_field_key = f"input.{best_match.field_name}"
            opa_input[rego_field_key] = value
    
    return opa_input


def print_json_mapping_report(
    payload_json: Union[str, Dict],
    top_k: int = 3,
    show_all_matches: bool = False
):
    """
    Print a formatted report for JSON payload mapping
    
    Args:
        payload_json: JSON payload to map
        top_k: Number of top matches per field
        show_all_matches: Show all matches or just best match
    """
    results = map_json_payload(payload_json, top_k=top_k)
    
    if "error" in results:
        print(f"\n❌ Error: {results['error']}\n")
        return
    
    print("\n" + "="*80)
    print("JSON PAYLOAD TO REGO FIELD MAPPING REPORT")
    print("="*80 + "\n")
    
    for payload_field, mapping in results.items():
        print(f"📌 Payload Field: {payload_field}")
        print(f"   Value: {mapping['payload_value']}")
        
        if "best_match" in mapping:
            best = mapping['best_match']
            print(f"\n   ✓ Best Match: {best['rego_field']}")
            print(f"     Score: {best['score']}")
            if best['context']:
                print(f"     Context: {best['context'][:60]}...")
        else:
            print(f"\n   ✗ No matches found")
        
        if show_all_matches and mapping['matches']:
            print(f"\n   All Matches ({len(mapping['matches'])}):")
            for i, match in enumerate(mapping['matches'], 1):
                print(f"     [{i}] {match['rego_field']} (score: {match['score']})")
        
        print()


def payload_to_opa_conditions(payload_json: Union[str, Dict]) -> Dict[str, Any]:
    """
    Alias for map_json_payload_to_opa_input for convenience
    
    Args:
        payload_json: JSON payload
    
    Returns:
        OPA input conditions dictionary
    """
    return map_json_payload_to_opa_input(payload_json)


# For integration with enforcement systems
class PayloadRegoMapper:
    """Context manager for rego field mapping"""
    
    def __init__(self, rego_dir: str = "opa_bundles", use_gemini: bool = True):
        self.matcher = RegoFieldMatcher(rego_dir=rego_dir, use_gemini=use_gemini)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def map(self, payload_field: str, top_k: int = 3) -> List[RegoField]:
        """Map a payload field to rego fields"""
        return self.matcher.match_fields(payload_field, top_k=top_k)
    
    def map_dict(self, payload_dict: dict, top_k: int = 3) -> dict:
        """Map all fields in a payload dictionary (keys only)"""
        return {
            field: self.matcher.match_fields(field, top_k=top_k)
            for field in payload_dict.keys()
        }
    
    def map_json(self, payload_json: Union[str, Dict], top_k: int = 3) -> Dict[str, Any]:
        """Map a JSON payload with field names and values"""
        # Parse JSON if string
        if isinstance(payload_json, str):
            try:
                payload_dict = json.loads(payload_json)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON: {str(e)}"}
        else:
            payload_dict = payload_json
        
        results = {}
        
        for payload_field, value in payload_dict.items():
            matches = self.matcher.match_fields(payload_field, top_k=top_k)
            best_match = matches[0] if matches else None
            
            field_result = {
                "payload_field": payload_field,
                "payload_value": value,
                "matches": []
            }
            
            if best_match:
                field_result["best_match"] = {
                    "rego_field": f"input.{best_match.field_name}",
                    "field_name": best_match.field_name,
                    "score": best_match.score,
                    "context": best_match.context
                }
            
            for match in matches:
                field_result["matches"].append({
                    "rego_field": f"input.{match.field_name}",
                    "field_name": match.field_name,
                    "score": match.score,
                    "context": match.context
                })
            
            results[payload_field] = field_result
        
        return results
    
    def to_opa_input(self, payload_json: Union[str, Dict]) -> Dict[str, Any]:
        """Convert JSON payload to OPA input conditions"""
        # Parse JSON if string
        if isinstance(payload_json, str):
            try:
                payload_dict = json.loads(payload_json)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON: {str(e)}"}
        else:
            payload_dict = payload_json
        
        opa_input = {}
        
        for payload_field, value in payload_dict.items():
            matches = self.matcher.match_fields(payload_field, top_k=1)
            
            if matches:
                best_match = matches[0]
                rego_field_key = f"input.{best_match.field_name}"
                opa_input[rego_field_key] = value
        
        return opa_input
    
    def print_json_report(self, payload_json: Union[str, Dict], show_all: bool = False):
        """Print formatted JSON mapping report"""
        results = self.map_json(payload_json)
        
        if "error" in results:
            print(f"\n❌ Error: {results['error']}\n")
            return
        
        print("\n" + "="*80)
        print("JSON PAYLOAD TO REGO FIELD MAPPING")
        print("="*80 + "\n")
        
        for payload_field, mapping in results.items():
            print(f"📌 {payload_field}")
            print(f"   Value: {mapping['payload_value']}")
            
            if "best_match" in mapping:
                best = mapping['best_match']
                print(f"   → {best['rego_field']} (score: {best['score']})")
            else:
                print(f"   → No match found")
            
            if show_all and mapping['matches']:
                print(f"   Other matches: {len(mapping['matches']) - 1}")
            print()


if __name__ == '__main__':
    # Example 1: Map individual fields
    print("\n" + "="*80)
    print("EXAMPLE 1: Individual Field Mapping")
    print("="*80)
    
    test_fields = [
        "authorizing_entity",
        "reimbursement_ceiling",
        "distance_threshold",
    ]
    
    print_mapping_report(test_fields, top_k=3)
    
    # Example 2: Map JSON payload
    print("\n" + "="*80)
    print("EXAMPLE 2: JSON Payload Mapping")
    print("="*80)
    
    payload = {
        "authorizing_entity": "Senior Manager",
        "min_service_period": 6,
        "distance_threshold": 200,
        "commute_mode": "Air (Economy Class)",
        "coverage_breadth": "on_regular_rolls",
        "private_lodging_stipend_ratio": 25,
        "reimbursement_ceiling": 125,
        "disbursement_basis": "eligible amount of the Senior level employee",
        "qualification_standard": "Job band and grade",
        "daily_mileage_boundary": 200,
        "assigned_validator": "Reporting Manager"
    }
    
    print_json_mapping_report(payload, top_k=3)
    
    # Example 3: Convert to OPA input
    print("\n" + "="*80)
    print("EXAMPLE 3: Convert to OPA Input Conditions")
    print("="*80)
    
    opa_conditions = map_json_payload_to_opa_input(payload)
    print("\nOPA Input Conditions:")
    print(json.dumps(opa_conditions, indent=2))
    
    # Example 4: Using context manager
    print("\n" + "="*80)
    print("EXAMPLE 4: Using Context Manager")
    print("="*80)
    
    with PayloadRegoMapper() as mapper:
        results = mapper.map_json(payload, top_k=3)
        mapper.print_json_report(payload)

#!/usr/bin/env python3

"""
Rego Field Mapper Integration Module
Easy-to-use wrapper for finding matching rego fields for payload fields
Designed to integrate with stage11_enforcement_api.py and similar enforcement systems

Usage in your code:
    from rego_field_mapper import map_payload_to_rego_field
    
    result = map_payload_to_rego_field("authorizing_entity", top_k=3)
    for field in result:
        print(f"input.{field.field_name} (score: {field.score})")
"""

import os
import sys
from typing import List, Optional
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
        """Map all fields in a payload dictionary"""
        return {
            field: self.matcher.match_fields(field, top_k=top_k)
            for field in payload_dict.keys()
        }


if __name__ == '__main__':
    # Example usage
    test_fields = [
        "authorizing_entity",
        "reimbursement_ceiling",
        "distance_threshold",
        "private_lodging_stipend_ratio",
        "disbursement_basis"
    ]
    
    print_mapping_report(test_fields, top_k=3)

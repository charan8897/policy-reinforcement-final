"""
Rego Field Mapper Module
AI-powered field mapper for converting payload fields to OPA Rego input.xxx conditions

Version: 1.0.0
Part of: docupolicy - Policy Reinforcement System
"""

__version__ = "1.1.0"
__author__ = "docupolicy"
__all__ = [
    'RegoFieldMatcher',
    'RegoField',
    'map_payload_to_rego_field',
    'map_payload_batch',
    'get_best_match',
    'get_field_info',
    'print_mapping_report',
    'map_json_payload',
    'map_json_payload_to_opa_input',
    'print_json_mapping_report',
    'payload_to_opa_conditions',
    'PayloadRegoMapper',
    'initialize_matcher',
    'get_matcher',
]

# Import main classes and functions
from .find_rego_fields import RegoFieldMatcher, RegoField
from .rego_field_mapper import (
    map_payload_to_rego_field,
    map_payload_batch,
    get_best_match,
    get_field_info,
    print_mapping_report,
    map_json_payload,
    map_json_payload_to_opa_input,
    print_json_mapping_report,
    payload_to_opa_conditions,
    PayloadRegoMapper,
    initialize_matcher,
    get_matcher,
)

# Version info
def get_version():
    """Get module version"""
    return __version__

"""
Stage 11: Enforcement API - FastAPI application for policy enforcement
Integrates with OPA Runtime running in Docker on localhost:8181
Enhanced with DETAILED violation reporting
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import asyncio
import logging
import re
from datetime import datetime
from opa_runtime_client import OPARuntimeClient, create_opa_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Rego Policy Analyzer - Parse conditions from Rego files
# ============================================================================

def parse_rego_rules(rego_file_path: str) -> Dict[str, List[str]]:
    """
    Parse Rego file and extract all rules with their conditions
    
    Args:
        rego_file_path: Path to .rego policy file
        
    Returns:
        Dict mapping rule IDs (C1, C2, etc.) to their conditions
    """
    try:
        with open(rego_file_path, 'r') as f:
            content = f.read()
        
        rules = {}
        
        # Extract rule blocks with conditions
        rule_blocks = re.findall(
            r'# Rule: (C\d+).*?if \{(.*?)\}',
            content,
            re.DOTALL
        )
        
        for rule_id, conditions_block in rule_blocks:
            # Parse conditions
            conditions = [
                line.strip() 
                for line in conditions_block.split('\n') 
                if line.strip() and not line.strip().startswith('#')
            ]
            rules[rule_id] = conditions
        
        return rules
    except Exception as e:
        logger.error(f"Failed to parse Rego file: {e}")
        return {}


def analyze_rule_failures(
    failed_rules: List[str],
    payload: Dict[str, Any],
    rego_rules: Dict[str, List[str]]
) -> Dict[str, Dict[str, Any]]:
    """
    Analyze why each rule failed and provide detailed reasons
    
    Args:
        failed_rules: List of rule IDs that failed (e.g., ['C2', 'C3', ...])
        payload: The input payload that was tested
        rego_rules: Dict of parsed Rego rules from rego file
        
    Returns:
        Dict with detailed failure analysis for each rule
    """
    failure_analysis = {}
    
    for rule_id in failed_rules:
        if rule_id not in rego_rules:
            continue
        
        conditions = rego_rules[rule_id]
        rule_failures = []
        
        for condition in conditions:
            # Check if condition involves input fields
            if "input." in condition:
                # Extract field name from condition
                field_matches = re.findall(r'input\.(\w+)', condition)
                
                for field_name in field_matches:
                    if field_name not in payload:
                        rule_failures.append({
                            'type': 'missing_field',
                            'field': field_name,
                            'condition': condition
                        })
                    else:
                        # Field exists but condition might not be satisfied
                        rule_failures.append({
                            'type': 'field_exists',
                            'field': field_name,
                            'value': payload[field_name],
                            'condition': condition
                        })
            else:
                # Condition doesn't reference input
                rule_failures.append({
                    'type': 'constant',
                    'condition': condition
                })
        
        failure_analysis[rule_id] = rule_failures
    
    return failure_analysis


def format_detailed_failure_report(
    failure_analysis: Dict[str, Dict[str, Any]]
) -> str:
    """
    Format failure analysis into human-readable report
    
    Args:
        failure_analysis: Dict from analyze_rule_failures()
        
    Returns:
        Formatted string report
    """
    report_lines = []
    
    for rule_id in sorted(failure_analysis.keys()):
        report_lines.append(f"{rule_id}:")
        failures = failure_analysis[rule_id]
        
        for failure in failures:
            if failure['type'] == 'missing_field':
                report_lines.append(f"  ✗ Missing field: {failure['field']}")
                report_lines.append(f"    Condition requires: {failure['condition']}")
            
            elif failure['type'] == 'field_exists':
                report_lines.append(f"  ✓ Field exists: {failure['field']} = {failure['value']}")
                report_lines.append(f"    But condition '{failure['condition']}' not satisfied")
        
        report_lines.append("")
    
    return "\n".join(report_lines)


# Initialize FastAPI app
app = FastAPI(
    title="Policy Enforcement API",
    description="Stage 11: Real-time policy enforcement via OPA with detailed violation reporting",
    version="1.0.0"
)

# Add CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for testing
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# ============================================================================
# Pydantic Models
# ============================================================================

class PolicyRequest(BaseModel):
    """
    Generic policy enforcement request - accepts any JSON payload
    Policy-agnostic: works with any policy type (travel, expense, hiring, etc.)
    """
    request_id: Optional[str] = None
    policy_type: Optional[str] = None
    submitted_date: Optional[str] = None
    
    # Allow any additional fields
    class Config:
        extra = "allow"


class Violation(BaseModel):
    """Detailed violation information"""
    clause_id: str
    denied: bool
    reason: str
    details: List[str] = []
    policy: Optional[str] = None


class ComplianceSummary(BaseModel):
    """Compliance status for a single policy"""
    clause_id: str
    status: str  # PASS, FAIL, ERROR
    message: Optional[str] = None
    reason: Optional[str] = None
    details: List[str] = []


class EnforcementResult(BaseModel):
    """Policy enforcement result with detailed violations"""
    request_id: str
    status: str
    compliant: bool
    total_policies_checked: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: str = "0%"
    violations: List[Violation] = []
    compliance_summary: List[ComplianceSummary] = []
    timestamp: str


# ============================================================================
# Dependency Injection
# ============================================================================

async def get_opa_client() -> OPARuntimeClient:
    """Get OPA Runtime Client instance"""
    return create_opa_client(opa_host="0.0.0.0", opa_port=8181)


def _normalize_field_name(field_name: str) -> str:
    """
    Normalize field name to lowercase with no special chars
    Converts: driverChargesApplicability -> driverchargesapplicability
              driver_charges_applicability -> driverchargesapplicability
              Driver Charges -> drivercharges
    """
    # Convert camelCase to lowercase
    name = re.sub(r'([a-z])([A-Z])', r'\1\2', field_name)
    # Remove spaces, underscores, hyphens
    name = re.sub(r'[\s_-]+', '', name)
    # Convert to lowercase
    return name.lower()


def _extract_ngrams(text: str, n: int = 3) -> set:
    """
    Extract n-grams (character substrings) from text
    This is completely dynamic and works for any field name
    
    Example: "drivercharges" -> {"dri", "riv", "ive", "ver", "erc", "rch", "cha", "har", "arg", "rge", "ges", ...}
    This captures phonetic/semantic similarity even for synonymous terms
    """
    text = text.lower()
    ngrams = set()
    for i in range(len(text) - n + 1):
        ngrams.add(text[i:i+n])
    return ngrams


def _extract_keywords(field_name: str) -> set:
    """
    Extract semantic keywords from field name dynamically
    No hardcoded lists - uses character n-gram analysis
    
    Examples:
        driverchargesapplicability -> ngrams + word segments
        chauffeurfees -> ngrams + word segments  
        operatorcosts -> ngrams + word segments
        pilotage -> ngrams + word segments
    
    Works for ANY field name regardless of domain
    """
    normalized = _normalize_field_name(field_name)
    
    # Use n-grams for character-level similarity
    # 3-grams work well for capturing phonetic/spelling similarity
    ngrams = _extract_ngrams(normalized, n=3)
    
    # Also try to extract words by assuming capital letters or common patterns
    # This helps with camelCase: driverCharges -> driver, charges
    # And compound words: drivercharges could be driver+charges
    words = set()
    
    # Simple heuristic: look for transitions where pattern might indicate word boundary
    current_word = ""
    for char in normalized:
        if char.isalpha():
            current_word += char
        else:
            if len(current_word) >= 2:
                words.add(current_word)
            current_word = ""
    
    if len(current_word) >= 2:
        words.add(current_word)
    
    # Return combination of n-grams (for similarity) and words (for semantic matching)
    return ngrams | words


def _calculate_keyword_similarity(expected_keywords: set, payload_keywords: set) -> float:
    """
    Calculate semantic similarity between field names using multiple strategies
    
    Combines:
    1. N-gram overlap (character patterns)
    2. Length similarity (fields of similar length are more likely to map)
    3. Jaccard similarity on extracted words
    
    Returns:
        float: Similarity score between 0 and 1
    """
    if not expected_keywords or not payload_keywords:
        return 0.0
    
    # Strategy 1: Jaccard similarity on n-grams
    intersection = len(expected_keywords & payload_keywords)
    union = len(expected_keywords | payload_keywords)
    
    if union == 0:
        return 0.0
    
    ngram_similarity = intersection / union
    
    # Strategy 2: Prefer fields of similar length (heuristic: mapped fields usually have similar length)
    # This helps avoid matching very different field names
    expected_str = ''.join(sorted(expected_keywords))
    payload_str = ''.join(sorted(payload_keywords))
    
    len_similarity = 1.0 - (abs(len(expected_str) - len(payload_str)) / max(len(expected_str), len(payload_str)))
    
    # Weighted combination: n-gram similarity is primary, length is secondary filter
    # This ensures we match fields with actual character overlap AND reasonable length
    combined_similarity = (ngram_similarity * 0.7) + (len_similarity * 0.3)
    
    return combined_similarity


def _find_field_in_payload(field_name: str, payload: Dict[str, Any]) -> Any:
    """
    Find field value in payload with flexible matching
    
    Tries:
    1. Exact match
    2. Case-insensitive match
    3. Normalized match (remove special chars, camelCase handling)
    """
    # Try exact match first
    if field_name in payload:
        return payload[field_name]
    
    # Try case-insensitive match
    field_lower = field_name.lower()
    for key, value in payload.items():
        if key.lower() == field_lower:
            logger.debug(f"Field matched (case-insensitive): '{field_name}' -> '{key}'")
            return value
    
    # Try normalized match (camelCase, snake_case, spaces all treated same)
    normalized_target = _normalize_field_name(field_name)
    for key, value in payload.items():
        normalized_key = _normalize_field_name(key)
        if normalized_key == normalized_target:
            logger.debug(f"Field matched (normalized): '{field_name}' -> '{key}'")
            return value
    
    # Try semantic/keyword-based match for synonymous fields
    # This handles cases where backends use different names but similar semantics
    # e.g., driverchargesapplicability vs operatorcosts (both about transportation costs)
    expected_keywords = _extract_keywords(field_name)
    
    if expected_keywords:
        best_match = None
        best_score = 0.0
        best_match_key = None
        
        for key, value in payload.items():
            payload_keywords = _extract_keywords(key)
            similarity_score = _calculate_keyword_similarity(expected_keywords, payload_keywords)
            
            # Lower threshold to catch semantic matches even with completely different names
            # The 3-gram analysis catches character pattern similarity
            if similarity_score > best_score:
                best_score = similarity_score
                best_match = value
                best_match_key = key
        
        # Only use semantic match if score is meaningful (>25% similarity)
        # Higher threshold reduces false matches while still catching synonyms
        if best_match is not None and best_score > 0.25:
            logger.info(
                f"Field semantic match (similarity: {best_score:.2f}): "
                f"expected '{field_name}' -> found '{best_match_key}'"
            )
            return best_match
    
    # Not found
    logger.debug(f"Field '{field_name}' not found in payload. Payload keys: {list(payload.keys())}")
    return None


def _evaluate_condition(condition: str, payload: Dict[str, Any], field_name: str) -> str:
    """
    Evaluate if a condition is satisfied for the given field value
    
    Args:
        condition: Rego condition string (e.g., "input.maximumdailydistance <= 50")
        payload: Request payload dict
        field_name: Field name to check
        
    Returns:
        "passed" if condition is satisfied, "violated" if not
    """
    # Use flexible field matching to find field in payload
    field_value = _find_field_in_payload(field_name, payload)
    
    try:
        # Extract operator and expected value from condition
        # Examples: "input.field <= 50", "input.field == 'value'", "input.field >= 200"
        
        if " <= " in condition:
            parts = condition.split(" <= ")
            expected = parts[1].strip()
            # Remove quotes if present
            expected = expected.strip("'\"")
            try:
                expected_num = float(expected)
                return "passed" if float(field_value) <= expected_num else "violated"
            except:
                return "violated"
        
        elif " >= " in condition:
            parts = condition.split(" >= ")
            expected = parts[1].strip()
            expected = expected.strip("'\"")
            try:
                expected_num = float(expected)
                return "passed" if float(field_value) >= expected_num else "violated"
            except:
                return "violated"
        
        elif " < " in condition:
            parts = condition.split(" < ")
            expected = parts[1].strip()
            expected = expected.strip("'\"")
            try:
                expected_num = float(expected)
                return "passed" if float(field_value) < expected_num else "violated"
            except:
                return "violated"
        
        elif " > " in condition:
            parts = condition.split(" > ")
            expected = parts[1].strip()
            expected = expected.strip("'\"")
            try:
                expected_num = float(expected)
                return "passed" if float(field_value) > expected_num else "violated"
            except:
                return "violated"
        
        elif " == " in condition:
            parts = condition.split(" == ")
            expected = parts[1].strip()
            expected = expected.strip("'\"")
            return "passed" if str(field_value) == expected else "violated"
        
        else:
            return "violated"
    
    except Exception as e:
        logger.debug(f"Error evaluating condition '{condition}': {e}")
        return "violated"


def _build_simple_failure_report(
    failed_rules_list: List[str],
    payload: Dict[str, Any],
    rego_rules: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Build detailed failure report for failed rules
    
    Shows rules where fields exist in payload with condition status (passed/violated).
    Omits rules with only missing fields since those don't need analysis.
    
    Returns structured dict with condition evaluation results.
    """
    violations = {}
    
    for rule_id in sorted(failed_rules_list):
        if rule_id not in rego_rules:
            continue
        
        conditions = rego_rules[rule_id]
        rule_violations = []
        
        for condition in conditions:
            if "input." in condition:
                # Extract all field names from this condition
                field_matches = re.findall(r'input\.(\w+)', condition)
                
                for field_name in set(field_matches):
                    # Use flexible matching to find field
                    payload_value = _find_field_in_payload(field_name, payload)
                    if payload_value is not None:
                        status = _evaluate_condition(condition, payload, field_name)
                        
                        rule_violations.append({
                            "field": field_name,
                            "value": payload_value,
                            "condition": condition,
                            "status": status
                        })
        
        # Only add this rule if it has at least one field that exists
        if rule_violations:
            violations[rule_id] = rule_violations
    
    return violations


def _build_failure_report(
    compliance_summary_data: List[Dict[str, Any]],
    payload: Dict[str, Any],
    rego_rules: Dict[str, List[str]]
) -> str:
    """
    Build detailed failure report from compliance summary
    
    Shows for each failed rule:
    - Missing fields (✗)
    - Fields that exist but don't satisfy conditions (✓ but...)
    - The actual conditions from the Rego file
    """
    report_lines = []
    
    if not isinstance(compliance_summary_data, list):
        logger.warning(f"compliance_summary_data is not a list: {type(compliance_summary_data)}")
        return ""
    
    for item in compliance_summary_data:
        if not isinstance(item, dict):
            logger.warning(f"Item in compliance_summary_data is not a dict: {type(item)}")
            continue
        
        if item.get('status') == 'FAIL':
            clause_id = item.get('clause_id')
            details = item.get('details', {})
            
            # details might be a list or dict depending on source
            if isinstance(details, list):
                logger.warning(f"details is a list for {clause_id}, converting...")
                expected_fields = []
                provided_fields = []
            else:
                expected_fields = details.get('expected_fields', []) if isinstance(details, dict) else []
                provided_fields = details.get('provided_fields', []) if isinstance(details, dict) else []
            
            # Get conditions from parsed Rego rules
            conditions = rego_rules.get(clause_id, [])
            
            report_lines.append(f"{clause_id}:")
            
            # Check each expected field
            for field in expected_fields:
                if field not in provided_fields:
                    report_lines.append(f"  ✗ Missing field: {field}")
                    # Find the condition that uses this field
                    for condition in conditions:
                        if f"input.{field}" in condition:
                            report_lines.append(f"    Condition requires: {condition}")
                            break
                else:
                    # Field exists but might not satisfy condition
                    payload_value = payload.get(field, "N/A")
                    report_lines.append(f"  ✓ Field exists: {field} = {payload_value}")
                    # Find the condition that uses this field
                    for condition in conditions:
                        if f"input.{field}" in condition:
                            report_lines.append(f"    But condition '{condition}' not satisfied")
                            break
            
            report_lines.append("")
    
    return "\n".join(report_lines)


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health")
async def health_check(opa_client: OPARuntimeClient = Depends(get_opa_client)):
    """
    Health check endpoint
    
    Returns:
        dict: Health status of API and OPA server
    """
    try:
        opa_health = await opa_client.health_check()
        
        return {
            "status": "healthy",
            "api": "online",
            "opa_runtime": opa_health.get('status'),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/api/bundle-info")
async def get_bundle_info(opa_client: OPARuntimeClient = Depends(get_opa_client)):
    """Get bundle information from OPA"""
    try:
        bundle_info = await opa_client.get_bundle_info()
        return bundle_info
    except Exception as e:
        logger.error(f"Failed to get bundle info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve bundle info")


# ============================================================================
# Policy Enforcement Endpoints
# ============================================================================

@app.post("/api/enforce")
async def enforce_policy(
    request: PolicyRequest,
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Enforce ANY policy against a request with DETAILED violation reporting
    
    Policy-agnostic: works with travel, expense, hiring, or any custom policy type.
    
    Accepts:
    - Flat JSON: {field1: value1, field2: value2, ...}
    - Nested JSON: {employee: {...}, travel: {...}, ...}
    - Any custom structure matching your policy
    
    Returns detailed reasons WHY policies failed:
    - Which policies passed/failed
    - Exact conditions that weren't met
    - What was expected vs. what was provided
    - DETAILED rule-by-rule failure analysis
    """
    try:
        request_id = request.request_id or f"REQ_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        policy_type = request.policy_type or "policy"
        
        logger.info(f"Processing {policy_type} enforcement request: {request_id}")
        
        # Convert request to dict (PolicyRequest allows extra fields)
        request_data = request.model_dump()
        
        # Remove metadata fields before sending to OPA
        request_data.pop('request_id', None)
        request_data.pop('policy_type', None)
        request_data.pop('submitted_date', None)
        
        logger.info(f"Request fields: {list(request_data.keys())}")
        
        # Enforce policy via OPA - returns detailed violations
        # For now using travel_policy enforcement; make policy-agnostic in future
        result = await opa_client.enforce_travel_policy(request_data)
        
        if result.get('status') == 'error':
            raise HTTPException(status_code=500, detail=result.get('error'))
        
        # Extract OPA results
        compliance = result.get('compliance', {})
        violations_data = compliance.get('violations', []) if isinstance(compliance, dict) else []
        compliance_summary_data = compliance.get('compliance_summary', []) if isinstance(compliance, dict) else []
        summary = compliance.get('summary', {}) if isinstance(compliance, dict) else {}
        opa_result = result.get('opa_result', {})
        
        # Extract passed and failed rules from compliance summary
        passed_rules = [item['clause_id'] for item in compliance_summary_data if isinstance(item, dict) and item.get('status') == 'PASS']
        failed_rules = [item['clause_id'] for item in compliance_summary_data if isinstance(item, dict) and item.get('status') == 'FAIL']
        
        # Parse Rego rules and analyze failures
        try:
            rego_file_path = '/home/hutech/Documents/docupolicy/opa_bundles/v1.0.0/.policy/travel_policy.rego'
            rego_rules = parse_rego_rules(rego_file_path)
            
            # Build detailed failure report from passed/failed rules
            detailed_failure_report = _build_simple_failure_report(failed_rules, request_data, rego_rules)
        except Exception as e:
            logger.error(f"Error in Rego analysis: {e}", exc_info=True)
            detailed_failure_report = f"Error generating detailed report: {str(e)}"
        
        # Convert to Pydantic models
        violations = []
        try:
            violations = [Violation(**v) for v in violations_data]
        except:
            pass
        
        compliance_summary = []
        for item in compliance_summary_data:
            try:
                if isinstance(item, dict):
                    comp = ComplianceSummary(**item)
                    compliance_summary.append(comp)
            except:
                pass
        
        # Return response with detailed failure analysis
        return {
            "request_id": request_id,
            "status": result.get('status'),
            "detailed_failure_analysis": detailed_failure_report,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enforcement failed for request: {e}")
        raise HTTPException(status_code=500, detail=f"Enforcement failed: {str(e)}")


@app.post("/api/evaluate-policy")
async def evaluate_single_policy(
    policy_path: str,
    input_data: Dict[str, Any],
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """Evaluate a single policy"""
    try:
        logger.info(f"Evaluating policy: {policy_path}")
        
        result = await opa_client.evaluate_policy(policy_path, input_data)
        return result
    
    except Exception as e:
        logger.error(f"Policy evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Policy evaluation failed: {str(e)}")


# ============================================================================
# Detailed Compliance Check
# ============================================================================

@app.post("/api/compliance-detailed")
async def compliance_check_detailed(
    request: PolicyRequest,
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Comprehensive compliance check with EXTREMELY detailed violation information
    
    Shows:
    - Which policies passed/failed
    - Exact reasons why they failed
    - What conditions weren't met
    """
    try:
        request_id = request.request_id or f"CHK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        request_data = request.model_dump()
        
        result = await opa_client.enforce_travel_policy(request_data)
        
        if result.get('status') == 'error':
            raise HTTPException(status_code=500, detail=result.get('error'))
        
        compliance = result.get('compliance', {})
        
        return {
            "request_id": request_id,
            "employee_id": request.employee.employee_id,
            "overall_compliant": result.get('compliant'),
            "compliance_summary": compliance.get('compliance_summary', []),
            "violations_detail": compliance.get('violations', []),
            "statistics": compliance.get('summary', {}),
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Detailed compliance check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {str(e)}")


# ============================================================================
# Root Endpoint
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with API documentation link"""
    return {
        "service": "Policy Enforcement API",
        "version": "1.0.0",
        "stage": "Stage 11 - Enforcement",
        "key_feature": "DETAILED violation reporting - explains WHY policies fail",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "endpoints": {
            "health": "GET /health",
            "enforce_detailed": "POST /api/enforce (DETAILED violations)",
            "compliance_detailed": "POST /api/compliance-detailed (VERY DETAILED)",
            "evaluate": "POST /api/evaluate-policy",
            "bundle_info": "GET /api/bundle-info"
        }
    }


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "detail": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Stage 11 Enforcement API...")
    logger.info("OPA Runtime expected at: http://localhost:8181")
    logger.info("Key feature: DETAILED violation reporting")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

"""
Stage 11: Enforcement API - FastAPI application for policy enforcement
Integrates with OPA Runtime running in Docker on localhost:8181
Supports any JSON input format (flat, nested, array, etc.)
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
import asyncio
import logging
from datetime import datetime
from opa_runtime_client import OPARuntimeClient, create_oparuntime_client
import json
import base64
import re
from collections.abc import Mapping

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Add file handler for enforcement logs
file_handler = logging.FileHandler('logs/enforcement_api.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
logger.addHandler(file_handler)

# Initialize FastAPI app
app = FastAPI(
    title="Policy Enforcement API",
    description="Stage 11: Real-time policy enforcement via OPA - Supports any JSON format",
    version="1.0.0"
)


# ============================================================================
# JSON Normalizer - Handles any JSON structure
# ============================================================================

class JSONNormalizer:
    """
    Normalizes any JSON structure to a flat dictionary for policy evaluation.
    
    Supports:
    - Flat JSON: {"key": "value"}
    - Nested JSON: {"employee": {"name": "John", "details": {"age": 30}}}
    - Array-Based JSON: [{"id": 1}, {"id": 2}]
    - Array of Objects: {"users": [{"name": "John"}, {"name": "Jane"}]}
    - Key/Value Map: {"attributes": {"grade": "E9", "designation": "Director"}}
    - EAV Style: {"data": [{"entity": "employee", "attribute": "grade", "value": "E9"}]}
    - Newline Delimited JSON (ndJSON): Multiple JSON objects separated by newlines
    - Base64 Encoded: {"data": "<base64 encoded json>"}
    """
    
    @staticmethod
    def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
        """Flatten nested dictionary"""
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(JSONNormalizer.flatten_dict(v, new_key, sep))
            elif isinstance(v, list):
                # Handle lists
                if all(isinstance(item, (dict, str, int, float, bool)) for item in v):
                    items[new_key] = v
                else:
                    items[new_key] = json.dumps(v)
            else:
                items[new_key] = v
        return items
    
    @staticmethod
    def normalize(input_data: Union[Dict, List, str]) -> Dict[str, Any]:
        """
        Normalize any JSON input to a flat dictionary for policy evaluation.
        
        Args:
            input_data: Any JSON structure (dict, list, or string)
        
        Returns:
            Flat dictionary with all fields accessible for policy rules
        """
        result = {}
        
        # Handle string input
        if isinstance(input_data, str):
            # Try to decode base64
            try:
                decoded = base64.b64decode(input_data).decode('utf-8')
                input_data = json.loads(decoded)
                logger.info("Decoded base64 JSON input")
            except Exception:
                # Try to parse as JSON string
                try:
                    input_data = json.loads(input_data)
                    logger.info("Parsed JSON string input")
                except Exception:
                    # Treat as plain string value
                    return {"value": input_data}
        
        # Handle ndJSON (newline delimited)
        if isinstance(input_data, str) and '\n' in input_data:
            lines = [line.strip() for line in input_data.split('\n') if line.strip()]
            if all(line.startswith('{') and line.endswith('}') for line in lines):
                input_data = [json.loads(line) for line in lines]
                logger.info(f"Parsed ndJSON with {len(input_data)} objects")
        
        # Handle list input (array-based JSON)
        if isinstance(input_data, list):
            # If list of objects, merge them
            for idx, item in enumerate(input_data):
                if isinstance(item, dict):
                    flattened = JSONNormalizer.flatten_dict(item, f"item_{idx}")
                    result.update(flattened)
            return result
        
        # Handle EAV (Entity-Attribute-Value) style
        if isinstance(input_data, dict):
            # Check for EAV pattern
            if 'entity' in input_data and 'attribute' in input_data and 'value' in input_data:
                result[input_data['attribute']] = input_data['value']
                return result
            
            # Check if it's a list of EAV rows
            if 'data' in input_data and isinstance(input_data['data'], list):
                if all(isinstance(row, dict) and 'attribute' in row for row in input_data['data']):
                    for row in input_data['data']:
                        result[row.get('attribute', f"attr_{list(row.keys()).index('attribute')}")] = row.get('value')
                    return result
            
            # Handle nested/flat JSON - flatten it
            result = JSONNormalizer.flatten_dict(input_data)
            return result
        
        return input_data if isinstance(input_data, dict) else {"value": input_data}
    
    @staticmethod
    def extract_policy_fields(normalized: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract fields commonly used in policies from normalized dict.
        
        Creates a standardized input structure for OPA policies.
        """
        # Try to extract employee fields
        employee = {}
        allowance = {}
        travel = {}
        hosting = {}
        approval = {}
        insurance = {}
        
        # Employee fields
        for key, value in normalized.items():
            key_lower = key.lower()
            if 'employee' in key_lower or 'emp' in key_lower:
                if 'id' in key_lower:
                    employee['employee_id'] = value
                elif 'designation' in key_lower or 'title' in key_lower:
                    employee['designation'] = value
                elif 'grade' in key_lower:
                    employee['grade'] = value
                elif 'type' in key_lower:
                    employee['employee_type'] = value
                elif 'email' in key_lower:
                    employee['email'] = value
        
        # Allowance fields
        for key, value in normalized.items():
            key_lower = key.lower()
            if 'allowance' in key_lower or 'daily' in key_lower or 'amount' in key_lower:
                if 'daily' in key_lower:
                    allowance['daily_allowance_requested'] = float(value) if isinstance(value, (int, float)) else value
                elif 'max' in key_lower and ('day' in key_lower or 'allowance' in key_lower):
                    allowance['maximum_allowed_days'] = int(value) if isinstance(value, (int, float)) else value
                elif 'total' in key_lower:
                    allowance['total_allowance_requested'] = float(value) if isinstance(value, (int, float)) else value
        
        # Travel fields
        for key, value in normalized.items():
            key_lower = key.lower()
            if 'travel' in key_lower or 'tour' in key_lower or 'trip' in key_lower:
                if 'mode' in key_lower:
                    travel['travel_mode'] = value
                elif 'duration' in key_lower or 'day' in key_lower:
                    travel['tour_duration_days'] = int(value) if isinstance(value, (int, float)) else value
                elif 'destination' in key_lower or 'city' in key_lower:
                    travel['destination'] = value
                elif 'departure' in key_lower:
                    travel['departure_date'] = value
                elif 'return' in key_lower:
                    travel['return_date'] = value
                elif 'purpose' in key_lower:
                    travel['purpose'] = value
        
        # Build the standard structure
        policy_input = {}
        
        if employee:
            policy_input['employee'] = employee
        if allowance:
            policy_input['allowance'] = allowance
        if travel:
            policy_input['travel'] = travel
        if hosting:
            policy_input['hosting'] = hosting
        if approval:
            policy_input['approval'] = approval
        if insurance:
            policy_input['insurance'] = insurance
        
        # If no structured fields found, return normalized dict as-is
        if not policy_input:
            return normalized
        
        return policy_input


# ============================================================================
# Pydantic Models
# ============================================================================

class EnforcementResult(BaseModel):
    """Policy enforcement result"""
    request_id: str
    status: str
    compliant: bool
    violations: List[Dict[str, Any]] = []
    evaluation_details: Dict[str, Any] = {}
    timestamp: str


# ============================================================================
# Dependency Injection
# ============================================================================

def get_opa_client() -> OPARuntimeClient:
    """Get OPA Runtime Client instance"""
    return create_oparuntime_client(opa_host="localhost", opa_port=8181)


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
            "json_support": "any JSON format",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/api/bundle-info")
async def get_bundle_info(opa_client: OPARuntimeClient = Depends(get_opa_client)):
    """
    Get bundle information from OPA
    
    Returns:
        dict: Bundle metadata and version info
    """
    try:
        bundle_info = await opa_client.get_bundle_info()
        return bundle_info
    except Exception as e:
        logger.error(f"Failed to get bundle info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve bundle info")


# ============================================================================
# Policy Enforcement Endpoints
# ============================================================================

@app.post("/api/enforce", response_model=EnforcementResult)
async def enforce_travel_policy(
    request: Dict[str, Any],
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Enforce policies against ANY JSON input structure.
    
    Supports:
    - Flat JSON: {"employee_id": "EMP001", "grade": "E9"}
    - Nested JSON: {"employee": {"id": "EMP001", "details": {"grade": "E9"}}}
    - Array of Objects: {"employees": [{"id": "EMP001"}, {"id": "EMP002"}]}
    - EAV Style: {"data": [{"attribute": "grade", "value": "E9"}]}
    - Base64 Encoded: {"data": "<base64 string>"}
    - Newline Delimited: "{\"id\": \"EMP001\"}\n{\"id\": \"EMP002\"}"
    
    Args:
        request: Any JSON payload
        opa_client: OPA Runtime Client
    
    Returns:
        EnforcementResult: Policy compliance status and violations
    """
    try:
        request_id = f"REQ_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"Processing enforcement request: {request_id}")
        logger.info(f"Raw input type: {type(request).__name__}")
        
        # Normalize any JSON input to flat dictionary
        normalized = JSONNormalizer.normalize(request)
        logger.info(f"Normalized keys: {list(normalized.keys())}")
        
        # Extract policy fields from normalized data
        policy_input = JSONNormalizer.extract_policy_fields(normalized)
        logger.info(f"Policy input structure: {list(policy_input.keys())}")
        
        # Enforce policy via OPA
        result = await opa_client.enforce_policies(policy_input)
        
        # Extract violations
        violations = result.get('evaluation_result', {}).get('violations', [])
        
        # Log the enforcement response
        enforcement_response = {
            "request_id": request_id,
            "status": result.get('status'),
            "compliant": result.get('compliant', False),
            "violations": violations,
            "evaluation_details": result.get('evaluation_result', {}),
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"ENFORCEMENT_RESPONSE: {enforcement_response}")
        
        return EnforcementResult(
            request_id=request_id,
            status=result.get('status'),
            compliant=result.get('compliant', False),
            violations=violations,
            evaluation_details=result.get('evaluation_result', {}),
            timestamp=datetime.now().isoformat()
        )
    
    except Exception as e:
        logger.error(f"Enforcement failed for request: {e}")
        raise HTTPException(status_code=500, detail=f"Enforcement failed: {str(e)}")


@app.post("/api/normalize-json")
async def normalize_json(request: Dict[str, Any]):
    """
    Normalize any JSON structure to a flat dictionary.
    
    Useful for testing JSON normalization.
    
    Args:
        request: Any JSON payload
    
    Returns:
        dict: Normalized and extracted policy fields
    """
    try:
        normalized = JSONNormalizer.normalize(request)
        policy_fields = JSONNormalizer.extract_policy_fields(normalized)
        
        return {
            "status": "success",
            "original_type": type(request).__name__,
            "normalized": normalized,
            "policy_input": policy_fields,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"JSON normalization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Normalization failed: {str(e)}")


@app.post("/api/evaluate-policy")
async def evaluate_single_policy(
    policy_path: str,
    input_data: Dict[str, Any],
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Evaluate a single policy
    
    Args:
        policy_path: OPA policy path
        input_data: Input payload (any JSON structure)
    
    Returns:
        dict: Policy evaluation result
    """
    try:
        # Normalize input
        normalized = JSONNormalizer.normalize(input_data)
        policy_input = JSONNormalizer.extract_policy_fields(normalized)
        
        logger.info(f"Evaluating policy: {policy_path}")
        
        result = await opa_client.evaluate_policy(policy_path, policy_input)
        return result
    
    except Exception as e:
        logger.error(f"Policy evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Policy evaluation failed: {str(e)}")


@app.post("/api/batch-evaluate")
async def batch_evaluate_policies(
    policies: List[Dict[str, str]],
    input_data: Dict[str, Any],
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Evaluate multiple policies in parallel
    
    Args:
        policies: List of {path, name} objects
        input_data: Common input data for all policies (any JSON structure)
    
    Returns:
        dict: Batch evaluation results
    """
    try:
        # Normalize input
        normalized = JSONNormalizer.normalize(input_data)
        policy_input = JSONNormalizer.extract_policy_fields(normalized)
        
        logger.info(f"Batch evaluating {len(policies)} policies")
        
        result = await opa_client.batch_evaluate(policies, policy_input)
        return result
    
    except Exception as e:
        logger.error(f"Batch evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch evaluation failed: {str(e)}")


@app.post("/api/enforce-any")
async def enforce_any_json(
    request: Dict[str, Any],
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Enforce policies against completely unstructured JSON.
    
    This endpoint accepts any JSON and attempts to extract policy-relevant fields.
    
    Args:
        request: Any JSON payload
    
    Returns:
        dict: Enforcement result with metadata
    """
    try:
        request_id = f"REQ_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"Processing ANY JSON request: {request_id}")
        
        # Normalize
        normalized = JSONNormalizer.normalize(request)
        policy_input = JSONNormalizer.extract_policy_fields(normalized)
        
        # Enforce
        result = await opa_client.enforce_policies(policy_input)
        
        # Build response with normalization details
        response = {
            "request_id": request_id,
            "original_structure": type(request).__name__,
            "normalized_keys": len(normalized),
            "policy_fields_extracted": list(policy_input.keys()),
            "status": result.get('status'),
            "compliant": result.get('compliant', False),
            "violations": result.get('evaluation_result', {}).get('violations', []),
            "evaluation_details": result.get('evaluation_result', {}),
            "timestamp": datetime.now().isoformat()
        }
        
        return response
    
    except Exception as e:
        logger.error(f"Enforcement failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enforcement failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

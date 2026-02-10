"""
Stage 11: Enforcement API - FastAPI application for policy enforcement
Integrates with OPA Runtime running in Docker on localhost:8181
Enhanced with DETAILED violation reporting
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import asyncio
import logging
from datetime import datetime
from opa_runtime_client import OPARuntimeClient, create_opa_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Policy Enforcement API",
    description="Stage 11: Real-time policy enforcement via OPA with detailed violation reporting",
    version="1.0.0"
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

@app.post("/api/enforce", response_model=EnforcementResult)
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
        
        # Extract detailed violations with reasons
        compliance = result.get('compliance', {})
        violations_data = compliance.get('violations', [])
        compliance_summary_data = compliance.get('compliance_summary', [])
        summary = compliance.get('summary', {})
        
        # Convert to Pydantic models
        violations = [Violation(**v) for v in violations_data]
        
        compliance_summary = []
        for item in compliance_summary_data:
            try:
                comp = ComplianceSummary(**item)
                compliance_summary.append(comp)
            except:
                # Fallback if model doesn't match exactly
                pass
        
        return EnforcementResult(
            request_id=request_id,
            status=result.get('status'),
            compliant=result.get('compliant', False),
            total_policies_checked=summary.get('total', 0),
            passed=summary.get('passed', 0),
            failed=summary.get('failed', 0),
            pass_rate=summary.get('pass_rate', '0%'),
            violations=violations,
            compliance_summary=compliance_summary,
            timestamp=datetime.now().isoformat()
        )
    
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

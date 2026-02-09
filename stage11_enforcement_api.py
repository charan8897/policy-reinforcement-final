"""
Stage 11: Enforcement API - FastAPI application for policy enforcement
Integrates with OPA Runtime running in Docker on localhost:8181
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
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
    description="Stage 11: Real-time policy enforcement via OPA",
    version="1.0.0"
)

# ============================================================================
# Pydantic Models
# ============================================================================

class EmployeeInfo(BaseModel):
    employee_id: str
    designation: str
    grade: str
    employee_type: str = "on_regular_rolls"
    email: Optional[str] = None


class TravelInfo(BaseModel):
    travel_mode: str
    tour_duration_days: int
    destination: str
    departure_date: str
    return_date: str
    purpose: Optional[str] = None


class AllowanceInfo(BaseModel):
    daily_allowance_requested: float
    maximum_allowed_days: int
    total_allowance_requested: float


class HostingInfo(BaseModel):
    hosting_type: str = "none"
    lodging_provided: bool = False
    meals_provided: bool = False
    partial_allowance_pct: float = 50.0


class ApprovalInfo(BaseModel):
    approver_designation: str
    visa_required: bool = False
    visa_fee_estimated: float = 0.0
    reimbursement_method: str = "company_pays"


class InsuranceInfo(BaseModel):
    insurance_type: str = "overseas_travel"
    coverage_amount: float = 50000.0


class TravelRequest(BaseModel):
    """Complete travel request payload"""
    employee: EmployeeInfo
    travel: TravelInfo
    allowance: AllowanceInfo
    hosting: HostingInfo
    approval: ApprovalInfo
    insurance: InsuranceInfo
    request_id: Optional[str] = None
    submitted_date: Optional[str] = None


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

async def get_opa_client() -> OPARuntimeClient:
    """Get OPA Runtime Client instance"""
    return create_opa_client(opa_host="localhost", opa_port=8181)


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
    request: TravelRequest,
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Enforce travel policy against employee request
    
    Args:
        request: TravelRequest payload
        opa_client: OPA Runtime Client
    
    Returns:
        EnforcementResult: Policy compliance status and violations
    """
    try:
        request_id = request.request_id or f"REQ_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"Processing enforcement request: {request_id}")
        
        # Convert request to dict for OPA
        request_data = request.model_dump()
        
        # Enforce policy via OPA
        result = await opa_client.enforce_travel_policy(request_data)
        
        # Extract violations
        violations = result.get('evaluation_result', {}).get('violations', [])
        
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


@app.post("/api/evaluate-policy")
async def evaluate_single_policy(
    policy_path: str,
    input_data: Dict[str, Any],
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Evaluate a single policy
    
    Args:
        policy_path: OPA policy path (e.g., "data.travel_policy.allow_c13_limit")
        input_data: Input payload for policy evaluation
    
    Returns:
        dict: Policy evaluation result
    """
    try:
        logger.info(f"Evaluating policy: {policy_path}")
        
        result = await opa_client.evaluate_policy(policy_path, input_data)
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
        input_data: Common input data for all policies
    
    Returns:
        dict: Batch evaluation results
    """
    try:
        logger.info(f"Batch evaluating {len(policies)} policies")
        
        result = await opa_client.batch_evaluate(policies, input_data)
        return result
    
    except Exception as e:
        logger.error(f"Batch evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch evaluation failed: {str(e)}")


# ============================================================================
# Advanced Endpoints
# ============================================================================

@app.post("/api/compliance-check")
async def compliance_check(
    request: TravelRequest,
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Comprehensive compliance check with detailed violations
    
    Args:
        request: TravelRequest payload
    
    Returns:
        dict: Compliance status with detailed breakdown
    """
    try:
        request_id = request.request_id or f"CHK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        request_data = request.model_dump()
        
        # Check key compliance areas
        compliance_areas = {
            "travel_mode": {
                "policy": "data.travel_policy.allow_c2_limit",
                "description": "Travel Mode Entitlement"
            },
            "allowance_limit": {
                "policy": "data.travel_policy.allow_c13_limit",
                "description": "Daily Allowance Limit"
            },
            "approval_required": {
                "policy": "data.travel_policy.allow_c29_approval",
                "description": "Travel Approval"
            },
            "insurance": {
                "policy": "data.travel_policy.allow_c7_restriction",
                "description": "Insurance Coverage"
            }
        }
        
        # Evaluate each area
        compliance_results = {}
        overall_compliant = True
        
        for area_key, area_config in compliance_areas.items():
            try:
                result = await opa_client.evaluate_policy(
                    area_config["policy"],
                    request_data
                )
                
                is_compliant = result.get('result', {}).get('allow', False)
                compliance_results[area_key] = {
                    "policy": area_config["policy"],
                    "description": area_config["description"],
                    "compliant": is_compliant,
                    "result": result
                }
                
                if not is_compliant:
                    overall_compliant = False
            
            except Exception as e:
                compliance_results[area_key] = {
                    "error": str(e)
                }
                overall_compliant = False
        
        return {
            "request_id": request_id,
            "overall_compliant": overall_compliant,
            "compliance_areas": compliance_results,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Compliance check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {str(e)}")


@app.post("/api/reload-bundle")
async def reload_bundle(
    version: str,
    opa_client: OPARuntimeClient = Depends(get_opa_client)
):
    """
    Reload a specific bundle version
    
    Args:
        version: Bundle version (e.g., "v1.0.4")
    
    Returns:
        dict: Reload status
    """
    try:
        logger.info(f"Reloading bundle version: {version}")
        result = await opa_client.reload_bundle(version)
        return result
    except Exception as e:
        logger.error(f"Bundle reload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bundle reload failed: {str(e)}")


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
        "docs": "/docs",
        "openapi": "/openapi.json",
        "endpoints": {
            "health": "/health",
            "enforce": "/api/enforce (POST)",
            "evaluate": "/api/evaluate-policy (POST)",
            "batch": "/api/batch-evaluate (POST)",
            "compliance": "/api/compliance-check (POST)",
            "bundle_info": "/api/bundle-info (GET)",
            "reload": "/api/reload-bundle (POST)"
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
            "timestamp": datetime.now().isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Stage 11 Enforcement API...")
    logger.info("OPA Runtime expected at: http://localhost:8181")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

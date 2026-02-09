"""
Stage 11: Enforcement Server Integration
Real-time policy enforcement via OPA + FastAPI

Features:
- Accept booking requests against travel policy
- Evaluate via OPA runtime
- Return decisions with violations, remediation, audit logs
- Track enforcement decisions with stage metadata
"""

import json
import requests
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== DATA MODELS ====================

class EmployeeInfo(BaseModel):
    """Employee attributes from stage3_entities"""
    employee_id: str = Field(..., description="Unique employee identifier")
    designation: str = Field(..., description="MD&CEO, Director, E8-E10, E7-Below, etc.")
    grade: str = Field(..., description="E7, E8, E9, E10, etc.")
    employee_type: str = Field(..., description="on_regular_rolls, on_deputation, director, md_ceo")

class TravelDetails(BaseModel):
    """Travel specifics from policy"""
    travel_mode: str = Field(..., description="Air (First Class), Air (Business Class), Air (Economy Class)")
    tour_duration_days: int = Field(..., ge=1, le=365, description="Days for tour")
    destination: str = Field(..., description="Country/city of travel")
    departure_date: str = Field(..., description="ISO format YYYY-MM-DD")
    return_date: str = Field(..., description="ISO format YYYY-MM-DD")

class AllowanceDetails(BaseModel):
    """Allowance request details"""
    daily_allowance_requested: float = Field(..., ge=0, description="Daily allowance in USD")
    maximum_allowed_days: int = Field(45, description="Max days policy allows")
    total_allowance_requested: float = Field(..., ge=0, description="Total = daily * days")

class HostingDetails(BaseModel):
    """Hosting type affects allowance"""
    hosting_type: str = Field("none", description="none, partial, full")
    lodging_provided: bool = False
    meals_provided: bool = False
    partial_allowance_pct: float = Field(50.0, ge=0, le=100, description="Percentage if partial")

class ApprovalDetails(BaseModel):
    """Approval chain"""
    approver_designation: str = Field(..., description="Who approved")
    visa_required: bool = False
    visa_fee_estimated: float = Field(0.0, ge=0, description="Visa cost")
    reimbursement_method: str = Field("company_pays", description="company_pays, employee_reimburses")

class InsuranceDetails(BaseModel):
    """Travel insurance coverage"""
    insurance_type: str = Field("overseas_travel", description="Type of insurance")
    coverage_amount: float = Field(..., ge=0, description="Coverage amount in USD")

class BookingRequest(BaseModel):
    """Complete booking request matching policy entities"""
    employee: EmployeeInfo
    travel: TravelDetails
    allowance: AllowanceDetails
    hosting: HostingDetails
    approval: ApprovalDetails
    insurance: InsuranceDetails

# ==================== RESPONSE MODELS ====================

class Violation(BaseModel):
    """Single policy violation"""
    rule_id: str = Field(..., description="Clause ID (C1-C30)")
    clause_id: str = Field(..., description="Same as rule_id")
    intent: str = Field(..., description="LIMIT, RESTRICTION, ADVISORY, etc.")
    severity: str = Field(..., description="ERROR, WARNING, INFO")
    message: str = Field(..., description="Human-readable violation message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Specific details")
    confidence: float = Field(1.0, ge=0, le=1, description="Confidence from Stage 5/7")
    source_stage: List[str] = Field(default_factory=list, description="Stages that generated rule")
    ambiguity_flag: bool = Field(False, description="Real ambiguity from Stage 5")

class PassedRule(BaseModel):
    """Rule that passed"""
    rule_id: str
    clause_id: str
    intent: str
    severity: str
    message: str
    confidence: float

class Remediation(BaseModel):
    """Remediation suggestion"""
    violation_rule: str = Field(..., description="Rule ID with violation")
    suggestion: str = Field(..., description="Primary fix suggestion")
    alternative_options: List[str] = Field(default_factory=list, description="Other options")

class AuditLog(BaseModel):
    """Audit trail for enforcement decision"""
    request_id: str
    employee_id: str
    enforcement_timestamp: str
    opa_response_time_ms: float
    rules_evaluated: int
    violations_found: int
    decision_outcome: str  # APPROVED, DENIED, CONDITIONAL
    stage_metadata: Dict[str, Any]

class EnforcementDecision(BaseModel):
    """Complete enforcement decision response"""
    request_id: str
    timestamp: str
    decision: Dict[str, Any]
    violations: List[Violation]
    passed_rules: List[PassedRule]
    remediation: List[Remediation]
    audit_log: AuditLog

# ==================== OPA ENFORCER ====================

class OPAEnforcer:
    """Interface to OPA for policy enforcement"""
    
    def __init__(self, opa_url: str = "http://localhost:8181"):
        self.opa_url = opa_url
        self.logger = logging.getLogger(__name__)
    
    def check_health(self) -> bool:
        """Check OPA server health"""
        try:
            response = requests.get(f"{self.opa_url}/health", timeout=2)
            return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"OPA health check failed: {e}")
            return False
    
    def enforce(self, booking: BookingRequest, request_id: str) -> Dict[str, Any]:
        """Evaluate booking against all policy rules"""
        start_time = datetime.now()
        
        try:
            # Prepare input for OPA
            opa_input = {
                "input": booking.dict()
            }
            
            # Call OPA data.travel_policy.allow
            response = requests.post(
                f"{self.opa_url}/v1/data/travel_policy/allow",
                json=opa_input,
                timeout=5
            )
            
            if response.status_code != 200:
                self.logger.error(f"OPA call failed: {response.status_code} - {response.text}")
                raise Exception(f"OPA evaluation failed: {response.status_code}")
            
            opa_result = response.json()
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            return {
                "success": True,
                "result": opa_result.get("result", {}),
                "elapsed_ms": elapsed_ms
            }
        
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Cannot connect to OPA: {e}")
            return {
                "success": False,
                "error": f"OPA connection failed: {e}"
            }
        except Exception as e:
            self.logger.error(f"OPA enforcement error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# ==================== REMEDIATION GENERATOR ====================

class RemediationSuggester:
    """Generate remediation suggestions based on violations"""
    
    SUGGESTIONS = {
        "C13": {
            "suggestion": "Reduce daily allowance request to match employee grade limit",
            "options": [
                "Request approval from MD&CEO for exception",
                "Reduce tour duration to stay within budget",
                "Change destination with lower estimated costs"
            ]
        },
        "C14": {
            "suggestion": "Daily allowance for E8-E10 capped at $350",
            "options": [
                "Reduce per-day allowance request",
                "Reduce tour duration",
                "Seek executive exception approval"
            ]
        },
        "C2": {
            "suggestion": "Travel mode must match employee grade entitlements",
            "options": [
                "E7-Below: Economy Class only",
                "E8-E10: Business Class",
                "Directors: Business/Club Class",
                "MD&CEO: First Class"
            ]
        },
        "C16": {
            "suggestion": "Residential Training allowance: $200/day, max 30 days",
            "options": [
                "Verify training qualifies as 'Residential Training'",
                "Ensure duration does not exceed 30 days"
            ]
        }
    }
    
    def generate(self, violation_rule: str, details: Dict) -> Remediation:
        """Generate remediation for a violation"""
        template = self.SUGGESTIONS.get(violation_rule, {
            "suggestion": f"Review {violation_rule} requirements in travel policy",
            "options": ["Consult HR for policy clarification"]
        })
        
        return Remediation(
            violation_rule=violation_rule,
            suggestion=template.get("suggestion", ""),
            alternative_options=template.get("options", [])
        )

# ==================== AUDIT LOGGER ====================

class AuditLogger:
    """Log enforcement decisions to MongoDB"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def log_decision(self, request_id: str, decision: EnforcementDecision):
        """Log enforcement decision"""
        # TODO: Implement MongoDB storage
        self.logger.info(f"Decision logged: {request_id} - {decision.decision}")

# ==================== FASTAPI APP ====================

app = FastAPI(
    title="Stage 11: Enforcement Server",
    description="Real-time policy enforcement via OPA",
    version="1.0.0"
)

enforcer = OPAEnforcer()
remediation = RemediationSuggester()
audit = AuditLogger()

# ==================== ENDPOINTS ====================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "api": "running",
        "opa": "healthy" if enforcer.check_health() else "unhealthy"
    }

@app.post("/api/enforce", response_model=EnforcementDecision)
async def enforce_booking(booking: BookingRequest) -> EnforcementDecision:
    """
    Enforce booking against travel policy
    
    Returns:
    - Violations found
    - Rules passed
    - Remediation suggestions
    - Audit trail with stage metadata
    """
    request_id = f"REQ-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid4())[:8]}"
    
    # Check OPA availability
    if not enforcer.check_health():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "OPA service unavailable",
                "request_id": request_id
            }
        )
    
    # Enforce via OPA
    opa_result = enforcer.enforce(booking, request_id)
    
    if not opa_result["success"]:
        raise HTTPException(
            status_code=500,
            detail={
                "error": opa_result.get("error"),
                "request_id": request_id
            }
        )
    
    # Parse OPA result
    opa_data = opa_result.get("result", {})
    allowed = opa_data.get("allow", False)
    
    # Build violations list (mock for now, will integrate with OPA output)
    violations = []
    passed_rules = []
    remediations = []
    
    # For now: simple pass/fail logic
    # In production: OPA will return detailed violations
    if not allowed:
        # Generate sample violation
        violation = Violation(
            rule_id="C13",
            clause_id="C13",
            intent="LIMIT",
            severity="ERROR",
            message="Policy constraint violation detected",
            confidence=0.95,
            source_stage=["stage3", "stage5", "stage6"],
            ambiguity_flag=False
        )
        violations.append(violation)
        
        # Generate remediation
        remediations.append(remediation.generate("C13", {}))
    
    # Build decision
    decision = EnforcementDecision(
        request_id=request_id,
        timestamp=datetime.now().isoformat(),
        decision={
            "allowed": allowed,
            "overall_severity": "ERROR" if violations else "INFO"
        },
        violations=violations,
        passed_rules=passed_rules,
        remediation=remediations,
        audit_log=AuditLog(
            request_id=request_id,
            employee_id=booking.employee.employee_id,
            enforcement_timestamp=datetime.now().isoformat(),
            opa_response_time_ms=opa_result.get("elapsed_ms", 0),
            rules_evaluated=30,
            violations_found=len(violations),
            decision_outcome="APPROVED" if allowed else "DENIED",
            stage_metadata={
                "active_bundle_version": "v1.0.4",
                "policy_hash": "abc123",
                "generated_stages": ["Stage3", "Stage4", "Stage5", "Stage6", "Stage9"]
            }
        )
    )
    
    # Log decision
    audit.log_decision(request_id, decision)
    
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "allowed": False,
                "violations": [v.dict() for v in violations],
                "remediation": [r.dict() for r in remediations],
                "request_id": request_id
            }
        )
    
    return decision

@app.get("/api/status")
async def status():
    """API status and metadata"""
    return {
        "status": "running",
        "version": "1.0.0",
        "opa_connected": enforcer.check_health(),
        "timestamp": datetime.now().isoformat()
    }

# ==================== STARTUP ====================

@app.on_event("startup")
async def startup_event():
    """Verify OPA connection on startup"""
    logger.info("Stage 11 Enforcement Server starting...")
    
    if not enforcer.check_health():
        logger.warning("OPA service not available - starting in degraded mode")
    else:
        logger.info("✓ OPA service connected and healthy")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

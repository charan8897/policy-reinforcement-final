# Stage 11: Enforcement Server Integration - Implementation Plan

## Executive Summary
Stage 11 implements a FastAPI enforcement server that integrates with OPA runtime to evaluate travel policy violations in real-time. The server accepts booking requests, evaluates them against the policy rules, and returns detailed enforcement decisions with audit logs.

---

## TO-DO List

### Phase 1: Core Implementation (Week 1)
- [ ] **1.1** Create `stage11_enforcement_api.py` with FastAPI app
- [ ] **1.2** Define `BookingRequest` schema (extract from stage3_entities.json)
- [ ] **1.3** Implement `OPAEnforcer` class with decision logic
- [ ] **1.4** Create `/api/enforce` endpoint with JSON response format
- [ ] **1.5** Implement decision output format with all required fields
- [ ] **1.6** Create `AuditLogger` class for enforcement tracking
- [ ] **1.7** Link decisions back to rule/stage metadata

### Phase 2: OPA Deployment (Week 1)
- [ ] **2.1** Create `docker-compose.yml` for OPA + API setup
- [ ] **2.2** Create `deploy.sh` script for CLI-based deployment
- [ ] **2.3** Implement OPA bundle auto-loader script
- [ ] **2.4** Support both local Docker and remote OPA instances
- [ ] **2.5** Add OPA health check endpoint
- [ ] **2.6** Version registry auto-detection for active bundle

### Phase 3: Error Handling & Integration (Week 1)
- [ ] **3.1** Implement OPA connection error handling
- [ ] **3.2** Fallback mechanisms for OPA unavailability
- [ ] **3.3** Request validation and error responses
- [ ] **3.4** Create remediation suggestion generator
- [ ] **3.5** Link policy violations to stage/clause source

### Phase 4: Testing & Documentation (Week 2)
- [ ] **4.1** Create test scenarios for C1-C30 clauses
- [ ] **4.2** Integration tests with OPA instance
- [ ] **4.3** API documentation with curl examples
- [ ] **4.4** Deployment documentation with sys_passkey: 1234

---

## 1. BookingRequest Schema (from Stage 3 Entities)

```python
# Extracted from stage3_entities.json
class EmployeeInfo(BaseModel):
    employee_id: str
    designation: str  # "MD&CEO", "Director", "E8-E10", "E7-Below", etc.
    grade: str  # "E7", "E8", "E9", "E10", etc.
    employee_type: str  # "on_regular_rolls", "on_deputation", "director", "md_ceo"

class TravelDetails(BaseModel):
    travel_mode: str  # "Air (First Class)", "Air (Business Class)", "Air (Economy Class)"
    tour_duration_days: int
    destination: str
    departure_date: str  # ISO format
    return_date: str  # ISO format

class AllowanceDetails(BaseModel):
    daily_allowance_requested: float  # $ amount
    maximum_allowed_days: int  # e.g., 45
    total_allowance_requested: float  # daily * days

class HostingDetails(BaseModel):
    hosting_type: str  # "none", "partial", "full"
    lodging_provided: bool
    meals_provided: bool
    partial_allowance_pct: float  # 50% if partial

class ApprovalDetails(BaseModel):
    approver_designation: str  # "MD&CEO", "Functional Head", etc.
    visa_required: bool
    visa_fee_estimated: float
    reimbursement_method: str  # "company_pays", "employee_reimburses"

class InsuranceDetails(BaseModel):
    insurance_type: str  # "overseas_travel"
    coverage_amount: float

class BookingRequest(BaseModel):
    employee: EmployeeInfo
    travel: TravelDetails
    allowance: AllowanceDetails
    hosting: HostingDetails
    approval: ApprovalDetails
    insurance: InsuranceDetails
```

---

## 2. Decision Output Format (JSON)

```json
{
  "request_id": "REQ-2026-02-09-001",
  "timestamp": "2026-02-09T12:00:00Z",
  "decision": {
    "allowed": false,
    "overall_severity": "ERROR"
  },
  "violations": [
    {
      "rule_id": "C13",
      "clause_id": "C13",
      "intent": "LIMIT",
      "severity": "ERROR",
      "message": "Daily allowance exceeds limit",
      "details": {
        "requested": 500,
        "allowed": 350,
        "limit_reason": "Employee grade E8-E10 limited to $350/day"
      },
      "confidence": 1.0,
      "source_stage": ["stage3", "stage5", "stage6"],
      "ambiguity_flag": false
    }
  ],
  "passed_rules": [
    {
      "rule_id": "C2",
      "clause_id": "C2",
      "intent": "LIMIT",
      "severity": "ERROR",
      "message": "Travel mode compliant",
      "confidence": 0.95
    }
  ],
  "remediation": [
    {
      "violation_rule": "C13",
      "suggestion": "Reduce daily allowance request from $500 to $350 for E8-E10 employee",
      "alternative_options": [
        "Request approval from MD&CEO for exception",
        "Reduce tour duration to stay within budget"
      ]
    }
  ],
  "audit_log": {
    "request_id": "REQ-2026-02-09-001",
    "employee_id": "EMP001",
    "enforcement_timestamp": "2026-02-09T12:00:00Z",
    "opa_response_time_ms": 45,
    "rules_evaluated": 30,
    "violations_found": 1,
    "decision_outcome": "DENIED",
    "stage_metadata": {
      "active_bundle_version": "v1.0.4",
      "policy_hash": "abc123def456",
      "generated_stages": ["Stage1", "Stage3", "Stage4", "Stage5", "Stage6", "Stage9"]
    }
  }
}
```

---

## 3. OPA Deployment To-Do

### 3.1 docker-compose.yml
```yaml
version: '3.8'
services:
  opa:
    image: openpolicyagent/opa:latest
    ports:
      - "8181:8181"
    volumes:
      - ./opa_bundles:/bundles
    environment:
      - OPA_LOG_LEVEL=info
    command: run --server --bundle /bundles
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8181/health"]
      interval: 5s
      timeout: 3s
      retries: 5

  enforcement-api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      opa:
        condition: service_healthy
    environment:
      - OPA_URL=http://opa:8181
      - SYS_PASSKEY=1234
      - MONGODB_URI=mongodb://localhost:27017
    command: uvicorn stage11_enforcement_api:app --host 0.0.0.0 --port 8000
```

### 3.2 deploy.sh (CLI with sys_passkey: 1234)
```bash
#!/bin/bash
# Usage: ./deploy.sh --action [start|stop|status|reload-bundle] --passkey 1234

ACTION=$2
PASSKEY=$4
SYS_PASSKEY="1234"

if [ "$PASSKEY" != "$SYS_PASSKEY" ]; then
    echo "ERROR: Invalid sys_passkey"
    exit 1
fi

case $ACTION in
    start)
        docker-compose up -d
        echo "OPA + Enforcement API started"
        ;;
    stop)
        docker-compose down
        echo "Services stopped"
        ;;
    status)
        docker-compose ps
        curl http://localhost:8181/health
        ;;
    reload-bundle)
        # Auto-load active bundle version
        ACTIVE_VERSION=$(cat opa_bundles/ACTIVE_VERSION)
        echo "Loading bundle version: $ACTIVE_VERSION"
        # Script will auto-detect and load
        ;;
esac
```

### 3.3 Bundle Auto-loader
```python
# stage11_bundle_loader.py
def load_active_bundle():
    """Auto-detect and load active bundle from version registry"""
    # Read version_registry.json
    # Get active_version
    # Load from /opa_bundles/{active_version}/
```

### 3.4 Health Check Integration
```python
@app.get("/health")
async def health_check():
    """Check OPA + API health"""
    return {
        "api_status": "healthy",
        "opa_status": check_opa_health(),
        "active_bundle": get_active_bundle_version()
    }
```

---

## 4. Integration Points Checklist

### 4.1 Auto-load Active Bundle Version ✓
- [ ] Read version registry from `opa_bundles/version_registry.json`
- [ ] Auto-detect active version on startup
- [ ] Load bundle from `/opa_bundles/{active_version}/`

### 4.2 Audit Logging ✓
- [ ] Track all enforcement decisions
- [ ] Log employee_id, timestamp, decision_outcome
- [ ] Store in MongoDB: `enforcement_audit` collection
- [ ] Include OPA response time, rules evaluated count

### 4.3 Stage/Rule Metadata Linking ✓
- [ ] Embed stage metadata in each rule
- [ ] Link violations back to:
  - Clause ID (C1-C30)
  - Intent (LIMIT, RESTRICTION, etc.)
  - Confidence score from Stage 5/7
  - Source stages (3, 4, 5, 6, 9)

### 4.4 Decision Output with Confidence ✓
- [ ] Include confidence scores from Stage 5
- [ ] Severity mapping: INFORMATIONAL→INFO, ADVISORY→WARNING, RESTRICTION→ERROR
- [ ] Remediation suggestions based on violation type
- [ ] Link to ambiguity flags from Stage 4

---

## 5. Data Flow

```
BookingRequest
    ↓
[Validation]
    ↓
[OPA Evaluation]
    ↓
[Decision with violations]
    ↓
[Audit Log + Remediation]
    ↓
[JSON Response]
    ↓
[MongoDB Audit Storage]
```

---

## 6. Implementation Steps

### Step 1: Extract and Define Schema (30 min)
- [ ] Map stage3_entities to BookingRequest
- [ ] Validate all required fields are covered
- [ ] Create Pydantic models

### Step 2: Create Core API (1 hour)
- [ ] FastAPI app with /api/enforce endpoint
- [ ] OPAEnforcer class
- [ ] Decision logic

### Step 3: Docker Setup (1 hour)
- [ ] docker-compose.yml
- [ ] deploy.sh with passkey validation
- [ ] Bundle loader script

### Step 4: Audit & Metadata (1.5 hours)
- [ ] AuditLogger class
- [ ] Stage metadata embedding
- [ ] MongoDB integration

### Step 5: Error Handling (30 min)
- [ ] Remediation suggestion generator
- [ ] OPA health checks
- [ ] Fallback mechanisms

### Step 6: Testing (1.5 hours)
- [ ] Test scenarios C1-C30
- [ ] Integration tests
- [ ] Curl examples

---

## Expected Outcome

✅ Working enforcement server
✅ OPA integration via REST API
✅ Comprehensive decision output with remediation
✅ Audit trail with stage metadata
✅ Docker deployment with CLI management
✅ Auto-bundle loading from version registry
✅ Health checks and monitoring

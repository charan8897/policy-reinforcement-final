# Stage 11: Enforcement Server Integration

Real-time policy enforcement server using FastAPI + OPA (Open Policy Agent).

## Overview

Stage 11 implements a REST API server that:
- Accepts booking requests against the travel policy
- Evaluates requests via OPA (policy evaluation engine)
- Returns detailed enforcement decisions with violations and remediation
- Tracks audit logs with stage metadata and confidence scores
- Auto-loads active policy bundle version

## Quick Start

### 1. Start Services (with sys_passkey: 1234)

```bash
./deploy.sh --action start --passkey 1234
```

This will:
- Start OPA service (port 8181)
- Start Enforcement API (port 8000)
- Start MongoDB for audit logs (port 27017)

### 2. Verify Services Running

```bash
./deploy.sh --action status --passkey 1234
```

### 3. Test Enforcement

```bash
curl -X POST http://localhost:8000/api/enforce \
  -H "Content-Type: application/json" \
  -d '{
    "employee": {
      "employee_id": "EMP001",
      "designation": "Director",
      "grade": "E9",
      "employee_type": "on_regular_rolls"
    },
    "travel": {
      "travel_mode": "Air (Business Class/Club Class)",
      "tour_duration_days": 10,
      "destination": "Singapore",
      "departure_date": "2026-02-20",
      "return_date": "2026-03-01"
    },
    "allowance": {
      "daily_allowance_requested": 350.0,
      "maximum_allowed_days": 45,
      "total_allowance_requested": 3500.0
    },
    "hosting": {
      "hosting_type": "none",
      "lodging_provided": false,
      "meals_provided": false,
      "partial_allowance_pct": 50.0
    },
    "approval": {
      "approver_designation": "MD&CEO",
      "visa_required": false,
      "visa_fee_estimated": 0.0,
      "reimbursement_method": "company_pays"
    },
    "insurance": {
      "insurance_type": "overseas_travel",
      "coverage_amount": 50000.0
    }
  }'
```

Or run the built-in test:
```bash
./deploy.sh --action test --passkey 1234
```

## Available Commands

### Deploy Script

```bash
# Start services
./deploy.sh --action start --passkey 1234

# Stop services
./deploy.sh --action stop --passkey 1234

# Check status
./deploy.sh --action status --passkey 1234

# View logs
./deploy.sh --action logs --passkey 1234 --service enforcement-api
./deploy.sh --action logs --passkey 1234 --service opa
./deploy.sh --action logs --passkey 1234 --service mongodb

# Reload policy bundle
./deploy.sh --action reload-bundle --passkey 1234

# Run smoke test
./deploy.sh --action test --passkey 1234

# Show help
./deploy.sh --action help --passkey 1234
```

## API Endpoints

### Health Check
```bash
GET /health
```

Response:
```json
{
  "status": "healthy",
  "api": "running",
  "opa": "healthy"
}
```

### Enforce Booking
```bash
POST /api/enforce
Content-Type: application/json

{booking_request_json}
```

Response (success):
```json
{
  "request_id": "REQ-20260209-abcd1234",
  "timestamp": "2026-02-09T12:00:00Z",
  "decision": {
    "allowed": true,
    "overall_severity": "INFO"
  },
  "violations": [],
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
  "remediation": [],
  "audit_log": {
    "request_id": "REQ-20260209-abcd1234",
    "employee_id": "EMP001",
    "enforcement_timestamp": "2026-02-09T12:00:00Z",
    "opa_response_time_ms": 45,
    "rules_evaluated": 30,
    "violations_found": 0,
    "decision_outcome": "APPROVED",
    "stage_metadata": {
      "active_bundle_version": "v1.0.4",
      "policy_hash": "abc123",
      "generated_stages": ["Stage3", "Stage4", "Stage5", "Stage6", "Stage9"]
    }
  }
}
```

Response (violation):
```json
{
  "detail": {
    "allowed": false,
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
    "remediation": [
      {
        "violation_rule": "C13",
        "suggestion": "Reduce daily allowance request to match employee grade limit",
        "alternative_options": [
          "Request approval from MD&CEO for exception",
          "Reduce tour duration to stay within budget"
        ]
      }
    ],
    "request_id": "REQ-20260209-abcd1234"
  }
}
```

### Status
```bash
GET /api/status
```

Response:
```json
{
  "status": "running",
  "version": "1.0.0",
  "opa_connected": true,
  "timestamp": "2026-02-09T12:00:00Z"
}
```

## BookingRequest Schema

Based on actual policy entities from Stage 3:

```python
{
  "employee": {
    "employee_id": str,           # Unique ID
    "designation": str,           # MD&CEO, Director, E8-E10, E7-Below
    "grade": str,                 # E7, E8, E9, E10, etc.
    "employee_type": str          # on_regular_rolls, on_deputation, director, md_ceo
  },
  "travel": {
    "travel_mode": str,           # Air (First Class), Business Class, Economy Class
    "tour_duration_days": int,    # 1-365
    "destination": str,
    "departure_date": str,        # ISO format YYYY-MM-DD
    "return_date": str            # ISO format YYYY-MM-DD
  },
  "allowance": {
    "daily_allowance_requested": float,
    "maximum_allowed_days": int,  # From policy
    "total_allowance_requested": float
  },
  "hosting": {
    "hosting_type": str,          # none, partial, full
    "lodging_provided": bool,
    "meals_provided": bool,
    "partial_allowance_pct": float
  },
  "approval": {
    "approver_designation": str,
    "visa_required": bool,
    "visa_fee_estimated": float,
    "reimbursement_method": str
  },
  "insurance": {
    "insurance_type": str,
    "coverage_amount": float
  }
}
```

## Services

### OPA (Open Policy Agent)
- **Port**: 8181
- **API**: http://localhost:8181
- **Purpose**: Policy evaluation engine
- **Bundle**: Auto-loads from `opa_bundles/{active_version}/`
- **Health**: GET /health

### Enforcement API
- **Port**: 8000
- **API**: http://localhost:8000
- **Framework**: FastAPI
- **Routes**:
  - GET /health
  - GET /api/status
  - POST /api/enforce
- **Health**: GET /health

### MongoDB
- **Port**: 27017
- **Database**: docupolicy
- **Collections**: enforcement_audit
- **Purpose**: Audit trail and enforcement decision logs

## Decision Output Format

Each enforcement decision includes:

1. **Decision Status**
   - `allowed` (boolean)
   - `overall_severity` (INFO, WARNING, ERROR)

2. **Violations** (if any)
   - `rule_id` / `clause_id` (C1-C30)
   - `intent` (LIMIT, RESTRICTION, ADVISORY, etc.)
   - `severity` (ERROR, WARNING, INFO)
   - `message` (human-readable)
   - `details` (specific constraint details)
   - `confidence` (from Stage 5/7)
   - `source_stage` (which stages generated the rule)
   - `ambiguity_flag` (if real ambiguity from Stage 4)

3. **Passed Rules**
   - Same structure as violations
   - Only rules that passed

4. **Remediation**
   - `violation_rule` (which rule to fix)
   - `suggestion` (primary fix)
   - `alternative_options` (other options)

5. **Audit Log**
   - `request_id` (unique request identifier)
   - `employee_id`
   - `enforcement_timestamp`
   - `opa_response_time_ms`
   - `rules_evaluated` (total clauses checked)
   - `violations_found`
   - `decision_outcome` (APPROVED, DENIED, CONDITIONAL)
   - `stage_metadata` (active bundle version, stages used)

## Architecture

```
BookingRequest (JSON)
         ↓
[FastAPI Request Handler]
         ↓
[Validation via Pydantic]
         ↓
[OPA Health Check]
         ↓
[POST to OPA: /v1/data/travel_policy/allow]
         ↓
[OPA Evaluates Rego Rules]
         ↓
[Violation Detection]
         ↓
[Remediation Generation]
         ↓
[Audit Log Creation]
         ↓
[MongoDB Storage]
         ↓
[JSON Response]
```

## Environment Variables

```bash
OPA_URL=http://localhost:8181        # OPA service URL
SYS_PASSKEY=1234                     # System passkey for CLI operations
LOG_LEVEL=INFO                       # Logging level
PYTHON_UNBUFFERED=1                  # Unbuffered Python output
```

## Troubleshooting

### OPA Service Unavailable
```bash
# Check OPA health
curl http://localhost:8181/health

# View OPA logs
./deploy.sh --action logs --passkey 1234 --service opa

# Reload bundle
./deploy.sh --action reload-bundle --passkey 1234
```

### API Service Not Responding
```bash
# Check API health
curl http://localhost:8000/health

# View API logs
./deploy.sh --action logs --passkey 1234 --service enforcement-api

# Restart API
./deploy.sh --action stop --passkey 1234
./deploy.sh --action start --passkey 1234
```

### MongoDB Connection Issues
```bash
# Check MongoDB status
./deploy.sh --action status --passkey 1234

# View MongoDB logs
./deploy.sh --action logs --passkey 1234 --service mongodb
```

## Security

- **sys_passkey**: Required for all CLI operations (default: 1234)
- **Docker networks**: Isolated internal communication
- **Volume mounts**: Read-only for OPA bundles
- **Health checks**: Built-in service health monitoring

## Integration with Previous Stages

Stage 11 integrates data from:

- **Stage 3** (Entities): Field definitions and schema
- **Stage 4** (Ambiguities): Ambiguity flags for rules
- **Stage 5** (Clarification): Confidence scores and intents
- **Stage 6** (DSL): Rule definitions
- **Stage 9** (Rego Bundles): Compiled OPA rules
- **Version Registry**: Active bundle version tracking

## Next Steps

After Stage 11 implementation:
1. Run smoke tests with various booking scenarios
2. Test all 30 clauses (C1-C30) with edge cases
3. Validate audit logs in MongoDB
4. Performance testing with load scenarios
5. Integration with upstream booking system

## Support

For issues or questions:
- Check logs: `./deploy.sh --action logs --passkey 1234 --service <service>`
- Review STAGE_11_IMPLEMENTATION_PLAN.md for detailed design
- Test with: `./deploy.sh --action test --passkey 1234`

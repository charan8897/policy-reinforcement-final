#!/bin/bash

################################################################################
# Stage 11: Enforcement Server Deployment Script
# Usage: ./deploy.sh --action [start|stop|status|reload-bundle|logs] --passkey 1234
################################################################################

set -e

# System passkey for security
SYS_PASSKEY="1234"
COMPOSE_FILE="docker-compose.yml"
LOG_DIR="./logs"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "\n${GREEN}==================================${NC}"
    echo -e "${GREEN}Stage 11: Enforcement Server${NC}"
    echo -e "${GREEN}==================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

check_passkey() {
    if [ "$1" != "$SYS_PASSKEY" ]; then
        print_error "Invalid sys_passkey"
        exit 1
    fi
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "docker-compose is not installed"
        exit 1
    fi
    
    print_success "Docker and docker-compose found"
}

################################################################################
# Action Functions
################################################################################

action_start() {
    print_header
    print_info "Starting Stage 11 Enforcement Server..."
    
    check_docker
    
    # Create logs directory
    mkdir -p "$LOG_DIR"
    
    # Build and start services
    print_info "Building and starting services..."
    docker-compose -f "$COMPOSE_FILE" up -d
    
    # Wait for services to be healthy
    print_info "Waiting for services to be healthy..."
    sleep 10
    
    # Check health
    if [ "$(docker-compose -f "$COMPOSE_FILE" ps -q opa)" ]; then
        print_success "OPA service started"
    else
        print_error "OPA service failed to start"
        docker-compose -f "$COMPOSE_FILE" logs opa
        exit 1
    fi
    
    if [ "$(docker-compose -f "$COMPOSE_FILE" ps -q enforcement-api)" ]; then
        print_success "Enforcement API started"
    else
        print_error "Enforcement API failed to start"
        docker-compose -f "$COMPOSE_FILE" logs enforcement-api
        exit 1
    fi
    
    # Get active bundle version
    ACTIVE_VERSION=$(ls -d opa_bundles/v* 2>/dev/null | sort -V | tail -1 | xargs basename)
    
    print_header
    echo -e "${GREEN}Stage 11 Services Running:${NC}"
    echo -e "  OPA Service:       ${GREEN}http://localhost:8181${NC}"
    echo -e "  Enforcement API:   ${GREEN}http://localhost:8000${NC}"
    echo -e "  Active Bundle:     ${GREEN}$ACTIVE_VERSION${NC}"
    echo ""
    echo -e "${YELLOW}Quick Test:${NC}"
    echo "  curl http://localhost:8000/health"
    echo ""
    echo -e "${YELLOW}Example Request:${NC}"
    echo "  curl -X POST http://localhost:8000/api/enforce \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d @test_booking.json"
    echo ""
}

action_stop() {
    print_header
    print_info "Stopping Stage 11 Enforcement Server..."
    
    docker-compose -f "$COMPOSE_FILE" down
    
    print_success "Services stopped"
}

action_status() {
    print_header
    print_info "Service Status:"
    
    docker-compose -f "$COMPOSE_FILE" ps
    
    echo ""
    print_info "Checking OPA health..."
    if curl -s http://localhost:8181/health > /dev/null; then
        print_success "OPA is healthy"
    else
        print_error "OPA is unreachable"
    fi
    
    echo ""
    print_info "Checking Enforcement API health..."
    if curl -s http://localhost:8000/health > /dev/null; then
        print_success "Enforcement API is healthy"
    else
        print_error "Enforcement API is unreachable"
    fi
}

action_logs() {
    print_header
    SERVICE=$2
    
    if [ -z "$SERVICE" ]; then
        print_info "Available services: opa, enforcement-api, mongodb"
        print_info "Usage: ./deploy.sh --action logs --service <service-name>"
        return
    fi
    
    print_info "Showing logs for: $SERVICE"
    docker-compose -f "$COMPOSE_FILE" logs -f "$SERVICE"
}

action_reload_bundle() {
    print_header
    print_info "Reloading OPA bundle..."
    
    # Get active bundle version
    ACTIVE_VERSION=$(ls -d opa_bundles/v* 2>/dev/null | sort -V | tail -1 | xargs basename)
    
    if [ -z "$ACTIVE_VERSION" ]; then
        print_error "No bundle versions found in opa_bundles/"
        exit 1
    fi
    
    print_info "Active bundle version: $ACTIVE_VERSION"
    
    # OPA will automatically reload bundles on startup
    # To reload without restart:
    BUNDLE_PATH="opa_bundles/$ACTIVE_VERSION"
    
    if [ ! -d "$BUNDLE_PATH" ]; then
        print_error "Bundle path not found: $BUNDLE_PATH"
        exit 1
    fi
    
    print_info "Sending bundle to OPA..."
    if curl -X PUT http://localhost:8181/v1/bundles/travel_policy \
         -H "Content-Type: application/json" \
         -d @"$BUNDLE_PATH/manifest.json" 2>/dev/null; then
        print_success "Bundle reloaded successfully"
    else
        print_error "Failed to reload bundle"
        exit 1
    fi
}

action_test() {
    print_header
    print_info "Running smoke test..."
    
    # Create sample booking request
    TEST_JSON=$(cat <<'EOF'
{
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
}
EOF
)
    
    print_info "Sending test booking request..."
    curl -X POST http://localhost:8000/api/enforce \
         -H "Content-Type: application/json" \
         -d "$TEST_JSON" \
         | python3 -m json.tool
    
    print_success "Test complete"
}

action_help() {
    cat << EOF
Stage 11: Enforcement Server Deployment Script

Usage: ./deploy.sh --action <action> --passkey <passkey> [--service <service>]

Actions:
    start              - Start OPA + Enforcement API services
    stop               - Stop all services
    status             - Show service status
    logs               - Show service logs (use --service to specify)
    reload-bundle      - Reload OPA policy bundle
    test               - Run smoke test
    help               - Show this help message

Passkey: 1234 (sys_passkey for security)

Examples:
    ./deploy.sh --action start --passkey 1234
    ./deploy.sh --action status --passkey 1234
    ./deploy.sh --action logs --passkey 1234 --service enforcement-api
    ./deploy.sh --action test --passkey 1234

Environment:
    OPA:               http://localhost:8181
    Enforcement API:   http://localhost:8000
    MongoDB:           mongodb://localhost:27017

EOF
}

################################################################################
# Main Script
################################################################################

# Parse arguments
ACTION=""
PASSKEY=""
SERVICE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --action)
            ACTION="$2"
            shift 2
            ;;
        --passkey)
            PASSKEY="$2"
            shift 2
            ;;
        --service)
            SERVICE="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Validate passkey (except for help)
if [ "$ACTION" != "help" ] && [ -z "$ACTION" ]; then
    action_help
    exit 0
fi

if [ "$ACTION" != "help" ] && [ -z "$PASSKEY" ]; then
    print_error "Missing --passkey argument"
    exit 1
fi

if [ "$ACTION" != "help" ]; then
    check_passkey "$PASSKEY"
fi

# Execute action
case $ACTION in
    start)
        action_start
        ;;
    stop)
        action_stop
        ;;
    status)
        action_status
        ;;
    logs)
        action_logs "$ACTION" "$SERVICE"
        ;;
    reload-bundle)
        action_reload_bundle
        ;;
    test)
        action_test
        ;;
    help)
        action_help
        ;;
    *)
        print_error "Unknown action: $ACTION"
        echo ""
        action_help
        exit 1
        ;;
esac

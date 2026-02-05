#!/bin/bash

# Start the Field Validation Backend Server
# Usage: ./START_SERVER.sh

echo "=================================================="
echo "Starting Field Validation API Backend"
echo "=================================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "⚠️  Flask not found. Installing..."
    pip3 install flask google-generativeai
fi

# Check if rules.txt exists
RULES_FILE="/home/hutech/Documents/docupolicy/rules.txt"
if [ ! -f "$RULES_FILE" ]; then
    echo "❌ rules.txt not found at: $RULES_FILE"
    echo "Please run policy_validator.py to generate rules.txt first"
    exit 1
fi

echo "✓ Rules file found: $RULES_FILE"
echo ""

# Start the backend server
echo "Starting backend at http://127.0.0.1:5000"
echo "API endpoint: POST /api/validate-field"
echo "Health check: GET /api/health"
echo ""
echo "To test in browser:"
echo "  1. Open: file:///home/hutech/Documents/docupolicy/step2-realtime-validation/generic-plugin-demo.html"
echo "  2. Fill fields and blur to trigger validation"
echo ""
echo "Press Ctrl+C to stop the server"
echo "=================================================="
echo ""

cd /home/hutech/Documents/docupolicy/step2-realtime-validation

python3 backend_field_validator_v2.py

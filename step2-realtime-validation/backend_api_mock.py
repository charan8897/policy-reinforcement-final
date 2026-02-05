#!/usr/bin/env python3
"""Mock Backend API for Testing"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import os
from datetime import datetime

RULES_FILE = "/home/hutech/Documents/docupolicy/rules.txt"
LOG_FILE = "/home/hutech/Documents/docupolicy/validation_api.log"

app = Flask(__name__)
CORS(app)

# Mock validations based on field names
MOCK_VALIDATIONS = {
    "employee_grade": {
        "E8": {"status": "valid", "message": "✓ Grade E8 qualifies for Business Class travel", "suggestion": "Daily allowance: $350/day. Maximum 45 days. Directors travel by Business Class."},
        "E7": {"status": "valid", "message": "✓ Grade E7 qualifies for Economy Class travel", "suggestion": "Daily allowance: $300/day. Maximum 45 days. E7 and below travel by Economy Class."},
        "E1": {"status": "valid", "message": "✓ Grade E1 qualifies for Economy Class travel", "suggestion": "Daily allowance: $300/day. Employees grade E7 and below travel by Economy Class."},
        "": {"status": "warning", "message": "⚠ Grade field is empty", "suggestion": "Please enter employee grade (E1-E10)"},
    },
    "travel_days": {
        "7": {"status": "valid", "message": "✓ 7 days is within policy", "suggestion": "Travel days must not exceed 45 days. This complies."},
        "45": {"status": "valid", "message": "✓ 45 days is maximum allowed", "suggestion": "This is the maximum days allowed without special approval."},
        "50": {"status": "warning", "message": "⚠ 50 days exceeds standard limit", "suggestion": "Days exceeding 45 require MD&CEO approval. Extended stays cannot exceed 50% of sanctioned days."},
        "": {"status": "warning", "message": "⚠ Travel days field is empty", "suggestion": "Please enter number of travel days (max 45 without approval)"},
    },
    "employee_name": {
        "": {"status": "warning", "message": "⚠ Employee name is required", "suggestion": "Written request with employee name must be submitted for MD&CEO approval."},
    },
    "destination": {
        "": {"status": "info", "message": "ℹ Destination field is empty", "suggestion": "Enter destination country for MEA rate calculation and policy verification."},
    },
    "travel_purpose": {
        "": {"status": "info", "message": "ℹ Travel purpose field is empty", "suggestion": "Written request stating reason for travel must be submitted to functional head before MD&CEO approval."},
    }
}

def load_rules():
    try:
        with open(RULES_FILE, 'r') as f:
            return f.read()
    except Exception as e:
        return None

@app.route('/policy-plugin.js', methods=['GET'])
def serve_plugin():
    try:
        current_dir = '/home/hutech/Documents/docupolicy/step2-realtime-validation'
        plugin_path = os.path.join(current_dir, 'policy-plugin.js')
        
        if not os.path.exists(plugin_path):
            return jsonify({"error": f"Plugin not found at {plugin_path}"}), 404
            
        return send_file(plugin_path, mimetype='application/javascript')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "Policy Validation API (MOCK MODE)",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/validate-field', methods=['POST'])
def validate_field():
    try:
        data = request.get_json()
        
        if not data or 'field_name' not in data:
            return jsonify({"error": "Missing field_name"}), 400
        
        field_name = data.get('field_name')
        field_value = str(data.get('field_value', '')).strip()
        
        # Get mock validation
        if field_name in MOCK_VALIDATIONS:
            validation_map = MOCK_VALIDATIONS[field_name]
            result = validation_map.get(field_value, {
                "status": "info",
                "message": f"Validating {field_name}",
                "suggestion": f"Field {field_name} with value '{field_value}' is being checked against policy rules."
            })
        else:
            result = {
                "status": "info",
                "message": "Field validated",
                "suggestion": "This field has been validated against policy rules."
            }
        
        # Add relevant rules
        rules = load_rules()
        if rules:
            result["relevant_rules"] = [
                "All overseas travel must be sanctioned by MD&CEO",
                "Daily allowance based on MEA rates for destination",
                "Maximum 45 days travel per period",
                "Visa fees reimbursed by company",
                "Travel insurance arranged by company"
            ]
        
        result['request_id'] = f"{datetime.now().timestamp()}"
        result['field_name'] = field_name
        result['timestamp'] = datetime.now().isoformat()
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500


if __name__ == '__main__':
    print("=" * 80)
    print("POLICY VALIDATION API - MOCK MODE (For Testing)")
    print("=" * 80)
    print("Running server on http://localhost:5000")
    print("=" * 80 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=5000)

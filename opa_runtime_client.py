"""
OPA Runtime Client - FastAPI Integration for OPA Policy Enforcement
Communicates with OPA running in Docker container on localhost:8181

Features:
- Async REST API calls to OPA server (localhost:8181)
- Dynamic policy loading from bundle JSON (stage9_rego_bundles.json)
- Policy-agnostic enforcement with detailed violation reasons
- Bundle version management
- Error handling and logging
- Compliance checking and rule violation reporting
"""

import aiohttp
import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import os
from pathlib import Path


class OPARuntimeClient:
    """
    OPA Runtime Client for policy enforcement against OPA server running in Docker.
    
    Features:
    - Dynamic policy loading from stage9_rego_bundles.json
    - Policy-agnostic enforcement (works with any policy bundle)
    - Detailed violation reasons based on bundle metadata
    - Async REST API calls to OPA server (localhost:8181)
    """
    
    def __init__(self, opa_host: str = "localhost", opa_port: int = 8181, 
                 bundles_dir: str = "./opa_bundles", timeout: int = 30):
        """
        Initialize OPA Runtime Client
        
        Args:
            opa_host: OPA server hostname (default: localhost)
            opa_port: OPA server port (default: 8181)
            bundles_dir: Path to bundles directory
            timeout: Request timeout in seconds
        """
        self.opa_host = opa_host
        self.opa_port = opa_port
        self.opa_url = f"http://{opa_host}:{opa_port}"
        self.bundles_dir = Path(bundles_dir)
        self.timeout = timeout
        self.active_version = self._get_active_bundle_version()
        
        # Setup logging FIRST (before loading policies)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self.logger.info(f"OPA Runtime Client initialized")
        self.logger.info(f"  OPA URL: {self.opa_url}")
        self.logger.info(f"  Active Bundle: {self.active_version}")
        
        # Dynamic policy loading (after logger is set up)
        self.policies: List[Dict[str, Any]] = []
        self.policy_rules: Dict[str, Dict[str, Any]] = {}
        self.field_mapping: Dict[str, str] = {}  # Maps API field names to DSL field names
        self._load_policies_from_bundle()
    
    def _get_active_bundle_version(self) -> str:
        """Get active bundle version from version registry"""
        try:
            registry_file = self.bundles_dir / "version_registry.json"
            if registry_file.exists():
                with open(registry_file) as f:
                    registry = json.load(f)
                    active = registry.get('active_version', 'v1.0.0')
                    self.logger.info(f"Active bundle version: {active}")
                    return active
        except Exception as e:
            self.logger.warning(f"Could not read version registry: {e}")
        
        return "v1.0.4"  # Default fallback
    
    def _load_policies_from_bundle(self):
        """
        Dynamically load policies from stage9_rego_bundles.json
        
        Reads the bundle JSON and extracts all policy rules with their metadata
        for dynamic policy enforcement.
        """
        bundle_path = self.bundles_dir / self.active_version / "bundle_metadata.json"
        stage9_path = Path("/home/hutech/Documents/docupolicy/stage9_rego_bundles.json")
        
        policies_loaded = []
        
        # Try to load from stage9_rego_bundles.json (primary source)
        if stage9_path.exists():
            try:
                with open(stage9_path, 'r') as f:
                    bundle_data = json.load(f)
                
                policies = bundle_data.get('policies', [])
                for policy in policies:
                    policy_name = policy.get('policy_name', 'unknown')
                    package = policy.get('package', 'data.travel_policy')
                    rules = policy.get('rules', [])
                    
                    for rule in rules:
                        rule_name = rule.get('rego_rule_name', '')
                        clause_id = rule.get('clause_id', '')
                        intent = rule.get('intent', 'UNKNOWN')
                        action = rule.get('action', 'enforce')
                        is_ambiguous = rule.get('is_ambiguous', False)
                        confidence = rule.get('confidence', 0.5)
                        
                        # Create policy path for OPA query (use / instead of . after package)
                        policy_path = f"{package.replace('data.', 'data/')}/{rule_name}"
                        
                        policy_info = {
                            "path": policy_path,
                            "name": f"{clause_id}: {intent}",
                            "clause_id": clause_id,
                            "intent": intent,
                            "action": action,
                            "is_ambiguous": is_ambiguous,
                            "confidence": confidence,
                            "description": rule.get('description', '')
                        }
                        policies_loaded.append(policy_info)
                        
                        # Store detailed rule info for violation reasons
                        self.policy_rules[policy_path] = {
                            "clause_id": clause_id,
                            "intent": intent,
                            "action": action,
                            "confidence": confidence
                        }
                
                self.logger.info(f"Loaded {len(policies_loaded)} policies from stage9_rego_bundles.json")
                
                # Load field mapping from bundle
                field_mapping = bundle_data.get('field_mapping', {})
                if field_mapping:
                    self.field_mapping = field_mapping
                    self.logger.info(f"Loaded {len(field_mapping)} field mappings from bundle")
                else:
                    # Use default field mapping for travel policy
                    self.field_mapping = self.get_default_field_mapping()
                    self.logger.info("Using default field mapping for travel policy")
                
            except Exception as e:
                self.logger.warning(f"Could not load from stage9_rego_bundles.json: {e}")
        
        # Fallback: Try to load from bundle_metadata.json
        if not policies_loaded and bundle_path.exists():
            try:
                with open(bundle_path, 'r') as f:
                    bundle_data = json.load(f)
                
                # Extract rules from metadata
                rules = bundle_data.get('rules', [])
                for rule in rules:
                    clause_id = rule.get('clause_id', '')
                    intent = rule.get('intent', 'UNKNOWN')
                    policy_path = f"data.travel_policy.policy_{clause_id.lower()}"
                    
                    policy_info = {
                        "path": policy_path,
                        "name": f"{clause_id}: {intent}",
                        "clause_id": clause_id,
                        "intent": intent,
                        "action": rule.get('action', 'enforce'),
                        "is_ambiguous": rule.get('is_ambiguous', False),
                        "confidence": rule.get('confidence', 0.5),
                        "description": rule.get('description', '')
                    }
                    policies_loaded.append(policy_info)
                
                self.logger.info(f"Loaded {len(policies_loaded)} policies from bundle_metadata.json")
                
            except Exception as e:
                self.logger.warning(f"Could not load from bundle_metadata.json: {e}")
        
        # Filter to only enforce-type policies for enforcement checks
        self.policies = [p for p in policies_loaded if p.get('action') == 'enforce']
        
        # If no enforce policies found, use all policies
        if not self.policies:
            self.policies = policies_loaded
        
        self.logger.info(f"Total enforce policies: {len(self.policies)}")
    
    @staticmethod
    def get_default_field_mapping():
        """
        Default field mapping for travel policy.
        Maps user-friendly API field paths to DSL field names expected by Rego rules.
        
        Maps both flat field names and nested paths.
        """
        return {
            # Nested path mappings (flattened paths -> DSL field names)
            'employee_designation': 'directortype',
            'employee_grade': 'eligibleemployeegrades',
            'employee_type': 'eligibleemployees',
            'employee_employee_id': 'employee_id',
            'travel_tour_duration_days': 'maximumallowanceduration',
            'travel_travel_mode': 'travel_mode',
            'travel_destination': 'destination',
            'allowance_daily_allowance_requested': 'dailyallowance',
            'allowance_daily_allowance': 'dailyallowance',
            'allowance_maximum_allowed_days': 'maximumallowanceduration',
            'allowance_total_allowance_requested': 'total_allowance',
            # Flat field mappings
            'designation': 'directortype',
            'grade': 'eligibleemployeegrades',
            'employee_type': 'eligibleemployees',
            'tour_duration_days': 'maximumallowanceduration',
            'daily_allowance_requested': 'dailyallowance',
            'daily_allowance': 'dailyallowance',
            'maximum_allowed_days': 'maximumallowanceduration',
            # Direct DSL field names (identity mapping)
            'directortype': 'directortype',
            'eligibleemployeegrades': 'eligibleemployeegrades',
            'eligibleemployees': 'eligibleemployees',
            'dailyallowance': 'dailyallowance',
            'maximumallowanceduration': 'maximumallowanceduration',
            'mdceotravelmode': 'mdceotravelmode',
            'directortravelmode': 'directortravelmode',
            'e8toe10travelmode': 'e8toe10travelmode',
            'e7andbelowtravelmode': 'e7andbelowtravelmode',
            'visafeereimbursement': 'visafeereimbursement',
            'insurancecoverage': 'insurancecoverage',
        }
    
    def get_policies_for_enforcement(self, policy_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get policies for enforcement
        
        Args:
            policy_type: Optional filter by intent type (e.g., "LIMIT", "RESTRICTION")
        
        Returns:
            List of policy dictionaries with path and name
        """
        if policy_type:
            return [p for p in self.policies if p.get('intent') == policy_type]
        return self.policies
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check OPA server health
        
        Returns:
            dict: Health status
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.opa_url}/health",
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        self.logger.info("OPA server is healthy")
                        return {"status": "healthy", "opa_url": self.opa_url}
                    else:
                        self.logger.warning(f"OPA health check returned {response.status}")
                        return {"status": "unhealthy", "status_code": response.status}
        except Exception as e:
            self.logger.error(f"OPA health check failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def evaluate_policy(self, 
                            policy_path: str,
                            input_data: Dict[str, Any],
                            bundle_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate policy against input data
        
        Args:
            policy_path: OPA policy path (e.g., "data.travel_policy.policy_c13_limi")
            input_data: Input payload for policy evaluation
            bundle_version: Specific bundle version (uses active if None)
        
        Returns:
            dict: Policy evaluation result with allow/deny and violations
        """
        if bundle_version is None:
            bundle_version = self.active_version
        
        try:
            # Flatten input data for OPA (policies expect flat structure)
            flattened_input = self.flatten_input(input_data)
            
            # Prepare OPA query
            query_data = {
                "input": flattened_input,
                "bundle_version": bundle_version
            }
            
            self.logger.info(f"Evaluating policy: {policy_path}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.opa_url}/v1/data/{policy_path}",
                    json=query_data,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        self.logger.info(f"Policy evaluation succeeded for {policy_path}")
                        return {
                            "status": "success",
                            "policy": policy_path,
                            "result": result,
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        self.logger.error(f"Policy evaluation failed: {result}")
                        return {
                            "status": "error",
                            "error": result,
                            "timestamp": datetime.now().isoformat()
                        }
        
        except asyncio.TimeoutError:
            self.logger.error(f"Policy evaluation timeout for {policy_path}")
            return {
                "status": "error",
                "error": f"Timeout evaluating {policy_path}",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Policy evaluation error for {policy_path}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    # Field mapping: Dynamically extracted from bundle policies
    FIELD_MAPPING = {}
    
    @staticmethod
    def flatten_input(input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten nested input data and map to DSL field names.
        
        Maps user-friendly API field names to the field names expected by Rego policies.
        Uses the field_mapping to translate field names.
        
        Input: {"employee": {"designation": "Director", "grade": "E9"}}
        Output: {"directortype": "Director", "eligibleemployeegrades": "E9"}
        """
        flattened = {}
        
        def _flatten_and_map(data, prefix=''):
            for key, value in data.items():
                if isinstance(value, dict):
                    _flatten_and_map(value, prefix + key + '_')
                elif isinstance(value, list):
                    # Handle list values - preserve as-is
                    flattened[key] = value
                else:
                    # Map field name using field_mapping
                    mapped_key = key
                    
                    # Try to find mapping for this field
                    # Check direct mapping first
                    if key in OPARuntimeClient.get_default_field_mapping():
                        mapping = OPARuntimeClient.get_default_field_mapping()[key]
                        if mapping:
                            mapped_key = mapping
                    
                    flattened[mapped_key] = value
        
        _flatten_and_map(input_data)
        return flattened
    
    def _generate_violation_reason(self, policy_path: str, policy_result: Dict[str, Any], input_data: Dict[str, Any]) -> str:
        """
        Generate detailed violation reason based on bundle metadata and input
        
        Args:
            policy_path: OPA policy path
            policy_result: Policy evaluation result
            input_data: Original input data
        
        Returns:
            Detailed violation reason string
        """
        # Get rule metadata from bundle
        rule_info = self.policy_rules.get(policy_path, {})
        clause_id = rule_info.get('clause_id', '')
        intent = rule_info.get('intent', '')
        action = rule_info.get('action', '')
        
        # Build detailed reason
        reasons = []
        
        if clause_id:
            reasons.append(f"Clause {clause_id}")
        
        if intent:
            reasons.append(f"Intent: {intent.replace('_', ' ').title()}")
        
        # Add specific details based on input data
        if input_data:
            employee = input_data.get('employee', {})
            travel = input_data.get('travel', {})
            allowance = input_data.get('allowance', {})
            
            if employee.get('designation'):
                reasons.append(f"Designation: {employee.get('designation')}")
            if employee.get('grade'):
                reasons.append(f"Grade: {employee.get('grade')}")
            if travel.get('travel_mode'):
                reasons.append(f"Travel Mode: {travel.get('travel_mode')}")
            if travel.get('destination'):
                reasons.append(f"Destination: {travel.get('destination')}")
            if allowance.get('daily_allowance_requested'):
                reasons.append(f"Requested Allowance: ${allowance.get('daily_allowance_requested')}")
        
        # If policy has a reason field, use it
        if policy_result.get('reason'):
            return f"{policy_result.get('reason')} (Clause {clause_id})"
        
        # Build comprehensive reason
        if reasons:
            return "; ".join(reasons)
        
        return f"Policy violation detected for {policy_path}"
    
    async def batch_evaluate(self,
                            policies: List[Dict[str, Any]],
                            input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate multiple policies in parallel
        
        Args:
            policies: List of policy objects with 'path' and 'name' keys
            input_data: Common input data for all policies
        
        Returns:
            dict: Results for all policies with violations summary
        """
        self.logger.info(f"Starting batch evaluation of {len(policies)} policies")
        
        tasks = [
            self.evaluate_policy(policy['path'], input_data)
            for policy in policies
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        violations = []
        allowed = 0
        denied = 0
        
        for i, result in enumerate(results):
            policy_info = policies[i]
            policy_path = policy_info.get('path', f'policy_{i}')
            
            if isinstance(result, Exception):
                self.logger.error(f"Batch evaluation error for policy {i}: {result}")
                violations.append({
                    "policy": policy_info.get('name', f'policy_{i}'),
                    "clause_id": policy_info.get('clause_id', ''),
                    "reason": f"Evaluation error: {str(result)}",
                    "severity": "error"
                })
                denied += 1
            elif result.get('status') == 'success':
                # OPA returns {"result": {"allow": true, ...}}} - extract inner result
                inner_result = result.get('result', {})
                policy_result = inner_result.get('result', {}) if isinstance(inner_result, dict) else {}
                
                # Check if rule exists in bundle
                rule_info = self.policy_rules.get(policy_path, {})
                has_rule = bool(rule_info)
                
                if not policy_result.get('allow', False) or not has_rule:
                    # Rule conditions not met OR rule not found → DENIED
                    denied += 1
                    # Generate detailed violation reason
                    reason = self._generate_violation_reason(policy_path, policy_result, input_data)
                    
                    violations.append({
                        "policy": policy_info.get('name', policy_path),
                        "clause_id": policy_info.get('clause_id', ''),
                        "intent": policy_info.get('intent', ''),
                        "reason": reason,
                        "severity": policy_info.get('action', 'enforce'),
                        "confidence": policy_info.get('confidence', 0.5)
                    })
                else:
                    allowed += 1
        
        return {
            "status": "complete",
            "total_policies": len(policies),
            "allowed": allowed,
            "denied": denied,
            "violations": violations,
            "timestamp": datetime.now().isoformat()
        }
    
    async def enforce_policies(self, 
                              input_data: Dict[str, Any],
                              policy_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Enforce all policies from the loaded bundle
        
        Args:
            input_data: Input data for policy evaluation
            policy_filter: Optional filter by intent type (e.g., "LIMIT", "RESTRICTION")
        
        Returns:
            dict: Enforcement result with compliance status and violations
        """
        employee_id = input_data.get('employee', {}).get('employee_id', 'unknown')
        self.logger.info(f"Enforcing policies for: {employee_id}")
        
        try:
            # Get policies to check (dynamically loaded)
            policies_to_check = self.get_policies_for_enforcement(policy_filter)
            
            if not policies_to_check:
                self.logger.warning("No policies loaded for enforcement")
                return {
                    "status": "warning",
                    "employee_id": employee_id,
                    "compliant": True,
                    "message": "No enforce-type policies found in bundle",
                    "evaluation_result": {
                        "status": "complete",
                        "total_policies": 0,
                        "allowed": 0,
                        "denied": 0,
                        "violations": [],
                        "timestamp": datetime.now().isoformat()
                    },
                    "timestamp": datetime.now().isoformat()
                }
            
            self.logger.info(f"Evaluating {len(policies_to_check)} policies")
            
            # Batch evaluate all policies
            batch_result = await self.batch_evaluate(policies_to_check, input_data)
            
            # Determine overall compliance
            is_compliant = batch_result['denied'] == 0
            
            return {
                "status": "success",
                "employee_id": employee_id,
                "compliant": is_compliant,
                "evaluation_result": batch_result,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            self.logger.error(f"Policy enforcement failed: {e}")
            return {
                "status": "error",
                "employee_id": employee_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def enforce_travel_policy(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enforce travel policy for employee request (legacy wrapper)
        
        Uses dynamically loaded policies from bundle instead of hardcoded paths.
        
        Args:
            employee_data: Employee travel request data
        
        Returns:
            dict: Enforcement result with compliance status and violations
        """
        return await self.enforce_policies(employee_data)
    
    async def get_bundle_info(self) -> Dict[str, Any]:
        """
        Get information about loaded bundles from OPA
        
        Returns:
            dict: Bundle information
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.opa_url}/v1/data",
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.info("Bundle info retrieved from OPA")
                        return {
                            "status": "success",
                            "bundle_info": data,
                            "active_version": self.active_version,
                            "local_policies_loaded": len(self.policies)
                        }
                    else:
                        return {"status": "error", "status_code": response.status}
        except Exception as e:
            self.logger.error(f"Failed to get bundle info: {e}")
            return {"status": "error", "error": str(e)}
    
    async def reload_bundle(self, version: str) -> Dict[str, Any]:
        """
        Trigger OPA to reload a specific bundle version
        
        Args:
            version: Bundle version to reload (e.g., "v1.0.4")
        
        Returns:
            dict: Reload status
        """
        self.logger.info(f"Requesting OPA to reload bundle version: {version}")
        
        try:
            # OPA auto-loads bundles, but we can verify
            bundle_path = self.bundles_dir / version / "bundle_metadata.json"
            if bundle_path.exists():
                self.active_version = version
                # Reload policies from new bundle
                self._load_policies_from_bundle()
                self.logger.info(f"Bundle version switched to: {version}")
                return {
                    "status": "success",
                    "active_version": version,
                    "policies_loaded": len(self.policies),
                    "message": "Bundle version activated"
                }
            else:
                self.logger.error(f"Bundle version not found: {version}")
                return {
                    "status": "error",
                    "error": f"Bundle version {version} not found"
                }
        except Exception as e:
            self.logger.error(f"Bundle reload failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def sync_health_check(self) -> Dict[str, Any]:
        """Synchronous wrapper for health check"""
        return asyncio.run(self.health_check())
    
    def sync_evaluate_policy(self, policy_path: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for policy evaluation"""
        return asyncio.run(self.evaluate_policy(policy_path, input_data))
    
    def sync_enforce_policies(self, input_data: Dict[str, Any], policy_filter: Optional[str] = None) -> Dict[str, Any]:
        """Synchronous wrapper for policy enforcement"""
        return asyncio.run(self.enforce_policies(input_data, policy_filter))
    
    def sync_enforce_travel_policy(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for travel policy enforcement"""
        return asyncio.run(self.enforce_travel_policy(employee_data))


# FastAPI Integration Helper
def create_oparuntime_client(opa_host: str = "localhost", opa_port: int = 8181) -> OPARuntimeClient:
    """
    Factory function to create OPA Runtime Client
    
    Useful for FastAPI dependency injection
    """
    return OPARuntimeClient(opa_host=opa_host, opa_port=opa_port)


if __name__ == "__main__":
    """Test the OPA Runtime Client"""
    import sys
    
    # Test data
    test_input = {
        "employee": {
            "employee_id": "EMP001",
            "designation": "Director",
            "grade": "E9",
            "employee_type": "on_regular_rolls"
        },
        "travel": {
            "travel_mode": "Air (Business Class/Club Class)",
            "tour_duration_days": 10,
            "destination": "Singapore"
        },
        "allowance": {
            "daily_allowance_requested": 500.0,
            "maximum_allowed_days": 45,
            "total_allowance_requested": 5000.0
        }
    }
    
    async def test():
        client = OPARuntimeClient()
        
        # Show loaded policies
        print(f"\nLoaded {len(client.policies)} policies for enforcement:")
        for p in client.policies[:5]:
            print(f"  - {p['name']}: {p['path']}")
        
        # Health check
        health = await client.health_check()
        print(f"\nHealth Check: {json.dumps(health, indent=2)}")
        
        # Travel policy enforcement
        enforce_result = await client.enforce_travel_policy(test_input)
        print(f"\nTravel Policy Enforcement: {json.dumps(enforce_result, indent=2)}")
    
    # Run tests
    asyncio.run(test())

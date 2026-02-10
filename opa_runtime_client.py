"""
OPA Runtime Client - FastAPI Integration for OPA Policy Enforcement
Communicates with OPA running in Docker container on localhost:8181
Enhanced with detailed violation reporting
"""

import aiohttp
import asyncio
import json
import logging
import shutil
from typing import Dict, Any, Optional, List
from datetime import datetime
import os
from pathlib import Path

class OPARuntimeClient:
    """
    OPA Runtime Client for policy enforcement against OPA server running in Docker.
    
    Features:
    - Async REST API calls to OPA server (localhost:8181)
    - Policy evaluation with DETAILED violation reasons
    - Bundle version management
    - Comprehensive error handling and logging
    - Compliance checking with granular detail
    """
    
    def __init__(self, opa_host: str = "0.0.0.0", opa_port: int = 8181, 
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
        
        # Setup logging FIRST (needed for version detection)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Get active version AFTER logging is setup
        self.active_version = self._get_active_bundle_version()
        
        self.logger.info(f"OPA Runtime Client initialized")
        self.logger.info(f"  OPA URL: {self.opa_url}")
        self.logger.info(f"  Active Bundle: {self.active_version}")
        
        # Prepare bundle for OPA loading
        self._prepare_bundle()
    
    def _prepare_bundle(self):
        """
        Prepare bundle structure for OPA bundle mode.
        OPA expects bundle at bundles_dir root, not in version subdirectory.
        """
        bundle_root = self.bundles_dir
        
        # Check if bundle root has required files
        has_manifest = (bundle_root / "manifest.json").exists()
        has_data = (bundle_root / "data.json").exists()
        has_policy = (bundle_root / ".policy").exists()
        
        if has_manifest and has_data and has_policy:
            self.logger.info(f"Bundle already prepared at {bundle_root}")
            return
        
        self.logger.info(f"Preparing bundle structure at {bundle_root}")
        
        # Get the active version directory
        version_dir = bundle_root / self.active_version
        
        # If active version doesn't exist, find available version
        if not version_dir.exists():
            self.logger.warning(f"Active version {self.active_version} not found, looking for alternatives...")
            # Find the first version directory that exists
            for item in bundle_root.iterdir():
                if item.is_dir() and item.name.startswith('v'):
                    version_dir = item
                    self.active_version = item.name
                    self.logger.info(f"Using alternative version: {self.active_version}")
                    break
            else:
                self.logger.error(f"No version directories found in {bundle_root}")
                return
        
        # Copy manifest.json
        src_manifest = version_dir / "manifest.json"
        if src_manifest.exists():
            import shutil
            shutil.copy(src_manifest, bundle_root / "manifest.json")
            self.logger.info(f"Copied manifest.json to bundle root")
        
        # Copy data.json
        src_data = version_dir / "data.json"
        if src_data.exists():
            shutil.copy(src_data, bundle_root / "data.json")
            self.logger.info(f"Copied data.json to bundle root")
        
        # Copy .policy directory
        src_policy = version_dir / ".policy"
        if src_policy.exists():
            import shutil
            if (bundle_root / ".policy").exists():
                shutil.rmtree(bundle_root / ".policy")
            shutil.copytree(src_policy, bundle_root / ".policy")
            self.logger.info(f"Copied .policy directory to bundle root")
        
        self.logger.info(f"Bundle preparation complete for version {self.active_version}")
    
    def _get_active_bundle_version(self) -> str:
        """Get active bundle version from version registry or filesystem"""
        # First try versions.json (new format)
        versions_file = self.bundles_dir / "versions.json"
        if versions_file.exists():
            try:
                with open(versions_file) as f:
                    versions = json.load(f)
                    active = versions.get('active', versions.get('latest', None))
                    if active:
                        # Normalize version format (e.g., "1.0.0" -> "v1.0.0")
                        if not active.startswith('v'):
                            active = f'v{active}'
                        self.logger.info(f"Active version from versions.json: {active}")
                        return active
            except Exception as e:
                self.logger.warning(f"Could not read versions.json: {e}")
        
        # Fallback to version_registry.json (old format)
        try:
            registry_file = self.bundles_dir / "version_registry.json"
            if registry_file.exists():
                with open(registry_file) as f:
                    registry = json.load(f)
                    active = registry.get('active_version', None)
                    if active:
                        self.logger.info(f"Active version from version_registry.json: {active}")
                        return active
        except Exception as e:
            self.logger.warning(f"Could not read version registry: {e}")
        
        # Final fallback: find the latest version directory from filesystem
        self.logger.info("No active version found in registry, looking for available versions...")
        versions = []
        for item in self.bundles_dir.iterdir():
            if item.is_dir() and item.name.startswith('v'):
                versions.append(item.name)
        
        if versions:
            # Sort versions and get the latest
            versions.sort(key=lambda v: [int(x) for x in v[1:].split('.')])
            latest_version = versions[-1]
            self.logger.info(f"Found latest version from filesystem: {latest_version}")
            return latest_version
        
        self.logger.warning("No version directories found, returning default")
        return "v1.0.0"
    
    def _extract_violation_reason(self, clause_id: str, policy_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract detailed violation reason from policy evaluation
        
        Args:
            clause_id: Clause ID being evaluated
            policy_result: Raw OPA result
        
        Returns:
            dict: Detailed violation information
        """
        reason_data = {
            "clause_id": clause_id,
            "denied": True,
            "reason": "Policy denied",
            "details": []
        }
        
        # Parse OPA response for constraint violations
        if isinstance(policy_result, dict):
            # Check result structure
            if 'result' in policy_result:
                inner_result = policy_result['result']
                
                # Check for allow field
                if 'allow' in inner_result:
                    reason_data["allow"] = inner_result['allow']
                    if not inner_result['allow']:
                        reason_data["details"].append("Evaluation returned: allow=false")
                
                # Check for constraint field
                if 'constraint' in inner_result:
                    constraint = inner_result['constraint']
                    reason_data["constraint"] = constraint
                    reason_data["details"].append(f"Constraint: {constraint}")
                
                # Check for action field
                if 'action' in inner_result:
                    action = inner_result['action']
                    reason_data["action"] = action
                    reason_data["details"].append(f"Action: {action}")
                
                # Check for status field
                if 'status' in inner_result:
                    status = inner_result['status']
                    reason_data["status"] = status
                    reason_data["details"].append(f"Status: {status}")
        
        # If still no details, it's an empty response
        if not reason_data["details"]:
            reason_data["details"].append("OPA returned empty result - no matching conditions")
            reason_data["reason"] = "No matching conditions in policy"
        
        return reason_data
    
    async def health_check(self) -> Dict[str, Any]:
        """Check OPA server health"""
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
        Evaluate policy against input data with detailed result
        
        Args:
            policy_path: OPA policy path (e.g., "data.travel_policy.allow_c13_limit")
            input_data: Input payload for policy evaluation
            bundle_version: Specific bundle version (uses active if None)
        
        Returns:
            dict: Detailed policy evaluation result
        """
        if bundle_version is None:
            bundle_version = self.active_version
        
        try:
            self.logger.info(f"Evaluating policy: {policy_path}")
            
            # Convert policy path to OPA URL format
            # data.travel_policy → data/travel_policy
            url_path = policy_path.replace('.', '/')
            opa_url = f"{self.opa_url}/v1/data/{url_path}"
            
            self.logger.debug(f"OPA URL: {opa_url}")
            self.logger.debug(f"Input keys: {list(input_data.keys())}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    opa_url,
                    json={"input": input_data},
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        self.logger.info(f"Policy evaluation succeeded for {policy_path}")
                        # Extract the actual result - OPA returns { "result": {...} }
                        policy_results = result.get("result", {})
                        self.logger.debug(f"Policy results: {list(policy_results.keys())}")
                        return {
                            "status": "success",
                            "policy": policy_path,
                            "result": policy_results,  # The actual rules and their results
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
                "error": "Request timeout",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Policy evaluation exception: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def _process_package_results(self, policies: List[Dict[str, Any]], package_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process OPA package result to extract individual rule evaluations
        
        Args:
            policies: List of policy metadata
            package_result: Result from evaluating the entire package
        
        Returns:
            dict: Formatted batch result with compliance info
        """
        violations = []
        compliance_summary = []
        allowed = 0
        denied = 0
        
        policy_results = package_result.get('result', {})
        
        for policy_info in policies:
            clause_id = policy_info.get('clause_id')
            policy_name = policy_info.get('name')
            
            # Find the rule result for this clause
            rule_name = f"allow_{clause_id.lower()}_*"
            matching_rules = {k: v for k, v in policy_results.items() if k.startswith(f"allow_{clause_id.lower()}_")}
            
            is_allowed = False
            rule_reason = "No matching conditions in policy"
            
            if matching_rules:
                first_rule = list(matching_rules.values())[0]
                is_allowed = first_rule.get('allow', False) if isinstance(first_rule, dict) else False
                rule_reason = first_rule.get('reason', 'No message') if isinstance(first_rule, dict) else 'Invalid result'
            
            # Only count as PASS if rules matched AND allow is true
            # If no matching rules, it should be marked as FAIL
            if matching_rules and is_allowed:
                allowed += 1
                compliance_summary.append({
                    "clause_id": clause_id,
                    "status": "PASS",
                    "message": rule_reason
                })
            else:
                denied += 1
                violations.append({
                    "clause_id": clause_id,
                    "denied": True,
                    "reason": rule_reason,
                    "details": [],
                    "policy": policy_name
                })
                compliance_summary.append({
                    "clause_id": clause_id,
                    "status": "FAIL",
                    "reason": rule_reason,
                    "details": []
                })
        
        return {
            "violations": violations,
            "compliance_summary": compliance_summary,
            "summary": {
                "passed": allowed,
                "failed": denied,
                "total": allowed + denied,
                "pass_rate": f"{(allowed / (allowed + denied) * 100):.1f}%" if (allowed + denied) > 0 else "0%"
            }
        }
    
    async def batch_evaluate_with_details(self,
                                         policies: List[Dict[str, Any]],
                                         input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate multiple policies with DETAILED violation information
        
        Args:
            policies: List of policy dicts with 'path', 'name', 'clause_id' keys
            input_data: Common input data for all policies
        
        Returns:
            dict: Results with detailed violations
        """
        self.logger.info(f"Starting batch evaluation of {len(policies)} policies with detail extraction")
        
        tasks = [
            self.evaluate_policy(policy['path'], input_data)
            for policy in policies
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results with DETAILED violation information
        violations = []
        compliance_summary = []
        allowed = 0
        denied = 0
        
        for i, result in enumerate(results):
            policy_info = policies[i]
            policy_name = policy_info.get('name', f'policy_{i}')
            clause_id = policy_info.get('clause_id', f'C{i}')
            
            if isinstance(result, Exception):
                denied += 1
                violations.append({
                    "policy": policy_name,
                    "clause_id": clause_id,
                    "denied": True,
                    "reason": "Evaluation error",
                    "error": str(result),
                    "error_type": type(result).__name__
                })
                compliance_summary.append({
                    "clause_id": clause_id,
                    "status": "ERROR",
                    "message": str(result)
                })
            
            elif result.get('status') == 'success':
                policy_results = result.get('result', {})
                
                # The result is now all rules from the package, find our specific rule
                rule_name = f"allow_{clause_id.lower()}_*"  # Pattern like allow_c2_*
                matching_rules = {k: v for k, v in policy_results.items() if k.startswith(f"allow_{clause_id.lower()}_")}
                
                # Get the first matching rule result
                is_allowed = False
                if matching_rules:
                    first_rule = list(matching_rules.values())[0]
                    is_allowed = first_rule.get('allow', False) if isinstance(first_rule, dict) else False
                    self.logger.debug(f"Clause {clause_id}: Found rules {list(matching_rules.keys())}, result={is_allowed}")
                else:
                    self.logger.debug(f"Clause {clause_id}: No matching rules in result. Available: {list(policy_results.keys())}")
                
                # Extract violation details
                violation_info = self._extract_violation_reason(clause_id, result)
                
                # Only count as PASS if rules matched AND allow is true
                if matching_rules and is_allowed:
                    allowed += 1
                    compliance_summary.append({
                        "clause_id": clause_id,
                        "status": "PASS",
                        "message": f"{policy_name} passed"
                    })
                else:
                    denied += 1
                    violations.append(violation_info)
                    compliance_summary.append({
                        "clause_id": clause_id,
                        "status": "FAIL",
                        "reason": violation_info.get("reason"),
                        "details": violation_info.get("details", [])
                    })
            else:
                denied += 1
                violations.append({
                    "policy": policy_name,
                    "clause_id": clause_id,
                    "denied": True,
                    "reason": f"Unexpected status: {result.get('status')}",
                    "details": [str(result)]
                })
                compliance_summary.append({
                    "clause_id": clause_id,
                    "status": "UNKNOWN",
                    "message": f"Unexpected status: {result.get('status')}"
                })
        
        return {
            "status": "complete",
            "summary": {
                "total_policies": len(policies),
                "passed": allowed,
                "failed": denied,
                "pass_rate": f"{(allowed/len(policies)*100):.1f}%" if policies else "N/A"
            },
            "compliance_summary": compliance_summary,
            "violations": violations,
            "timestamp": datetime.now().isoformat()
        }
    
    async def enforce_travel_policy(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enforce travel policy with DETAILED violation reporting
        Dynamically loads all rules from bundle metadata (not hardcoded)
        
        Args:
            employee_data: Employee travel request data
        
        Returns:
            dict: Detailed enforcement result
        """
        employee_id = employee_data.get('employee', {}).get('employee_id', 'UNKNOWN')
        self.logger.info(f"Enforcing travel policy for employee: {employee_id}")
        
        try:
            # Dynamically load all policy rules from bundle metadata
            policies_to_check = []
            
            # Try to load from bundle metadata (if available)
            bundle_metadata_path = "/home/hutech/Documents/docupolicy/opa_bundles/v1.0.0/bundle_metadata.json"
            try:
                import json as json_lib
                with open(bundle_metadata_path, 'r') as f:
                    metadata = json_lib.load(f)
                    travel_policy = metadata.get('policies', {}).get('travel_policy', {})
                    rules = travel_policy.get('rules', [])
                    
                    # Convert metadata rules to policy check format
                    for rule in rules:
                        policies_to_check.append({
                            "path": f"data.travel_policy.{rule.get('rego_rule_name')}",
                            "name": f"Clause {rule.get('clause_id')} - {rule.get('intent')}",
                            "clause_id": rule.get('clause_id'),
                            "description": rule.get('rego_code', '').split('\n')[2].strip() if rule.get('rego_code') else 'Policy rule'
                        })
                    
                    self.logger.info(f"Dynamically loaded {len(policies_to_check)} policies from bundle metadata")
                    
            except Exception as e:
                self.logger.warning(f"Failed to load bundle metadata: {e}. Using fallback rules.")
                # Fallback to hardcoded rules if metadata unavailable
                policies_to_check = [
                    {
                        "path": "data.travel_policy.allow_c2_info",
                        "name": "Clause C2 - INFORMATIONAL",
                        "clause_id": "C2",
                        "description": "Validates policy applicability"
                    },
                    {
                        "path": "data.travel_policy.allow_c13_rest",
                        "name": "Clause C13 - RESTRICTION",
                        "clause_id": "C13",
                        "description": "Validates daily allowance restrictions"
                    },
                ]
            
            # Query the whole package once instead of individual rules
            # This is more efficient and returns all rules with their results
            package_result = await self.evaluate_policy("data.travel_policy", employee_data)
            
            # Get the actual rule results from the package
            policy_results = package_result.get('result', {})
            
            # If package result is empty, query individual rules
            if not policy_results:
                self.logger.info("Package result empty, querying individual rules")
                policy_results = {}
                for policy_info in policies_to_check:
                    rule_path = policy_info['path']
                    rule_result = await self.evaluate_policy(rule_path, employee_data)
                    rule_data = rule_result.get('result', {})
                    if rule_data:
                        policy_results[rule_path.split('.')[-1]] = rule_data
                    self.logger.debug(f"Rule {rule_path}: {rule_data}")
            
            # Create a fake package result for processing
            package_result_for_processing = {"result": policy_results}
            
            # Process the package result to extract individual rule results
            batch_result = self._process_package_results(policies_to_check, package_result_for_processing)
            
            # Determine overall compliance
            is_compliant = batch_result['summary']['failed'] == 0
            
            return {
                "status": "success",
                "employee_id": employee_id,
                "compliant": is_compliant,
                "compliance": batch_result,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            self.logger.error(f"Travel policy enforcement failed: {e}")
            return {
                "status": "error",
                "employee_id": employee_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def get_bundle_info(self) -> Dict[str, Any]:
        """Get information about loaded bundles from OPA"""
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
                            "active_version": self.active_version
                        }
                    else:
                        return {"status": "error", "status_code": response.status}
        except Exception as e:
            self.logger.error(f"Failed to get bundle info: {e}")
            return {"status": "error", "error": str(e)}
    
    # Synchronous wrappers for compatibility
    def sync_health_check(self) -> Dict[str, Any]:
        """Synchronous wrapper for health check"""
        return asyncio.run(self.health_check())
    
    def sync_enforce_travel_policy(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for travel policy enforcement"""
        return asyncio.run(self.enforce_travel_policy(employee_data))


def create_opa_client(opa_host: str = "localhost", opa_port: int = 8181) -> OPARuntimeClient:
    """Factory function for OPA Runtime Client (useful for FastAPI dependency injection)"""
    return OPARuntimeClient(opa_host=opa_host, opa_port=opa_port)


if __name__ == "__main__":
    """Test the OPA Runtime Client"""
    
    test_input = {
        "employee": {
            "employee_id": "EMP002",
            "designation": "Senior Manager",
            "grade": "E7",
            "employee_type": "on_regular_rolls"
        },
        "travel": {
            "travel_mode": "Air (Economy Class)",
            "tour_duration_days": 15,
            "destination": "USA"
        },
        "allowance": {
            "daily_allowance_requested": 400.0,
            "maximum_allowed_days": 45
        }
    }
    
    async def test():
        client = OPARuntimeClient()
        
        # Health check
        health = await client.health_check()
        logging.info(f"Health Check: {health['status']}")
        
        # Travel policy enforcement
        enforce_result = await client.enforce_travel_policy(test_input)
        logging.info(f"Travel Policy Enforcement: {enforce_result['status']}, Compliant: {enforce_result.get('compliant', 'N/A')}")
    
    asyncio.run(test())

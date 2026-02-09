"""
OPA Runtime Client - FastAPI Integration for OPA Policy Enforcement
Communicates with OPA running in Docker container on localhost:8181
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
    - Async REST API calls to OPA server (localhost:8181)
    - Policy evaluation with input data
    - Bundle version management
    - Error handling and logging
    - Compliance checking and rule violation reporting
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
        
        # Setup logging
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
            policy_path: OPA policy path (e.g., "data.travel_policy.allow_c13_limit")
            input_data: Input payload for policy evaluation
            bundle_version: Specific bundle version (uses active if None)
        
        Returns:
            dict: Policy evaluation result with allow/deny and violations
        """
        if bundle_version is None:
            bundle_version = self.active_version
        
        try:
            # Prepare OPA query
            query_data = {
                "input": input_data,
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
            if isinstance(result, Exception):
                self.logger.error(f"Batch evaluation error for policy {i}: {result}")
                violations.append({
                    "policy": policies[i].get('name', f'policy_{i}'),
                    "error": str(result)
                })
            elif result.get('status') == 'success':
                policy_result = result.get('result', {})
                if not policy_result.get('allow', False):
                    denied += 1
                    violations.append({
                        "policy": policies[i].get('name'),
                        "reason": policy_result.get('reason', 'Policy denied')
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
    
    async def enforce_travel_policy(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enforce travel policy for employee request
        
        Args:
            employee_data: Employee travel request data
        
        Returns:
            dict: Enforcement result with compliance status and violations
        """
        self.logger.info(f"Enforcing travel policy for employee: {employee_data.get('employee', {}).get('employee_id')}")
        
        try:
            # Key policy checks
            policies_to_check = [
                {"path": "data.travel_policy.allow_c2_limit", "name": "Travel Mode Entitlement"},
                {"path": "data.travel_policy.allow_c13_limit", "name": "Daily Allowance Limit"},
                {"path": "data.travel_policy.allow_c16_limit", "name": "Residential Training"},
                {"path": "data.travel_policy.allow_c29_approval", "name": "Travel Approval"},
            ]
            
            batch_result = await self.batch_evaluate(policies_to_check, employee_data)
            
            # Determine overall compliance
            is_compliant = batch_result['denied'] == 0
            
            return {
                "status": "success",
                "employee_id": employee_data.get('employee', {}).get('employee_id'),
                "compliant": is_compliant,
                "evaluation_result": batch_result,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            self.logger.error(f"Travel policy enforcement failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
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
                            "active_version": self.active_version
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
                self.logger.info(f"Bundle version switched to: {version}")
                return {
                    "status": "success",
                    "active_version": version,
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
    
    def sync_enforce_travel_policy(self, employee_data: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for travel policy enforcement"""
        return asyncio.run(self.enforce_travel_policy(employee_data))


# FastAPI Integration Helper
def create_opa_client(opa_host: str = "localhost", opa_port: int = 8181) -> OPARuntimeClient:
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
            "daily_allowance_requested": 350.0,
            "maximum_allowed_days": 45
        }
    }
    
    async def test():
        client = OPARuntimeClient()
        
        # Health check
        health = await client.health_check()
        print(f"Health Check: {json.dumps(health, indent=2)}")
        
        # Single policy evaluation
        result = await client.evaluate_policy(
            "data.travel_policy.allow_c13_limit",
            test_input
        )
        print(f"\nPolicy Evaluation: {json.dumps(result, indent=2)}")
        
        # Travel policy enforcement
        enforce_result = await client.enforce_travel_policy(test_input)
        print(f"\nTravel Policy Enforcement: {json.dumps(enforce_result, indent=2)}")
    
    # Run tests
    asyncio.run(test())

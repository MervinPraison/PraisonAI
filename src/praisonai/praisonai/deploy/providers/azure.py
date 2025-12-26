"""
Azure provider for cloud deployment (Container Apps).
"""
import subprocess
import json
from typing import Dict, Any
from .base import BaseProvider
from ..models import DeployResult
from ..doctor import DoctorReport, DoctorCheckResult, check_azure_cli


class AzureProvider(BaseProvider):
    """Azure deployment provider using Container Apps."""
    
    def doctor(self) -> DoctorReport:
        """Run Azure-specific health checks."""
        checks = [check_azure_cli()]
        
        # Check if resource group exists
        if self.config.resource_group:
            try:
                result = subprocess.run(
                    ['az', 'group', 'show',
                     '--name', self.config.resource_group,
                     '--output', 'json'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    checks.append(DoctorCheckResult(
                        name="Resource Group",
                        passed=True,
                        message=f"Resource group exists: {self.config.resource_group}"
                    ))
                else:
                    checks.append(DoctorCheckResult(
                        name="Resource Group",
                        passed=False,
                        message=f"Resource group not found: {self.config.resource_group}",
                        fix_suggestion=f"Run: az group create --name {self.config.resource_group} --location {self.config.region}"
                    ))
            except Exception as e:
                checks.append(DoctorCheckResult(
                    name="Resource Group",
                    passed=False,
                    message=f"Failed to check resource group: {e}",
                    fix_suggestion="Check Azure CLI configuration"
                ))
        
        return DoctorReport(checks=checks)
    
    def plan(self) -> Dict[str, Any]:
        """Generate Azure deployment plan."""
        plan = {
            "provider": "azure",
            "service_name": self.config.service_name,
            "region": self.config.region,
            "resource_group": self.config.resource_group,
            "subscription_id": self.config.subscription_id,
            "cpu": self.config.cpu,
            "memory": self.config.memory,
            "min_replicas": self.config.min_instances,
            "max_replicas": self.config.max_instances,
            "image": self.config.image or f"{self.config.service_name}:latest",
            "steps": [
                "1. Create resource group (if not exists)",
                "2. Create Container Apps environment",
                "3. Create or update Container App",
                "4. Get app URL"
            ]
        }
        
        return plan
    
    def deploy(self) -> DeployResult:
        """Deploy to Azure Container Apps."""
        try:
            if not self.config.resource_group:
                return DeployResult(
                    success=False,
                    message="Resource group is required for Azure deployment",
                    error="Please specify resource_group in cloud config"
                )
            
            # Step 1: Create resource group if not exists
            print(f"📦 Creating resource group: {self.config.resource_group}")
            try:
                subprocess.run(
                    ['az', 'group', 'create',
                     '--name', self.config.resource_group,
                     '--location', self.config.region],
                    capture_output=True,
                    timeout=30
                )
            except Exception:
                pass  # May already exist
            
            # Step 2: Create Container Apps environment
            env_name = f"{self.config.service_name}-env"
            print(f"🌍 Creating Container Apps environment: {env_name}")
            
            try:
                subprocess.run(
                    ['az', 'containerapp', 'env', 'create',
                     '--name', env_name,
                     '--resource-group', self.config.resource_group,
                     '--location', self.config.region],
                    capture_output=True,
                    timeout=120
                )
            except Exception:
                pass  # May already exist
            
            # Step 3: Create or update Container App
            print(f"🚀 Deploying Container App: {self.config.service_name}")
            
            cmd = [
                'az', 'containerapp', 'create',
                '--name', self.config.service_name,
                '--resource-group', self.config.resource_group,
                '--environment', env_name,
                '--image', self.config.image or f"{self.config.service_name}:latest",
                '--target-port', '8005',
                '--ingress', 'external',
                '--cpu', str(self.config.cpu),
                '--memory', f"{self.config.memory}Gi",
                '--min-replicas', str(self.config.min_instances),
                '--max-replicas', str(self.config.max_instances)
            ]
            
            # Add environment variables
            if self.config.env_vars:
                env_args = []
                for k, v in self.config.env_vars.items():
                    env_args.extend(['--env-vars', f"{k}={v}"])
                cmd.extend(env_args)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180
            )
            
            if result.returncode != 0:
                # Try update instead
                cmd[1] = 'update'
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=180
                )
            
            if result.returncode == 0:
                # Get app URL
                try:
                    show_result = subprocess.run(
                        ['az', 'containerapp', 'show',
                         '--name', self.config.service_name,
                         '--resource-group', self.config.resource_group,
                         '--output', 'json'],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if show_result.returncode == 0:
                        app_data = json.loads(show_result.stdout)
                        url = app_data.get('properties', {}).get('configuration', {}).get('ingress', {}).get('fqdn')
                        if url:
                            url = f"https://{url}"
                    else:
                        url = None
                except Exception:
                    url = None
                
                return DeployResult(
                    success=True,
                    message=f"Container App deployed successfully",
                    url=url,
                    metadata={
                        "resource_group": self.config.resource_group,
                        "app_name": self.config.service_name,
                        "region": self.config.region
                    }
                )
            else:
                return DeployResult(
                    success=False,
                    message="Failed to deploy Container App",
                    error=result.stderr
                )
        
        except Exception as e:
            return DeployResult(
                success=False,
                message="Azure deployment failed",
                error=str(e)
            )

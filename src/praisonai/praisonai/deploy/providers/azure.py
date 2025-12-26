"""
Azure provider for cloud deployment (Container Apps).
"""
import subprocess
import json
from typing import Dict, Any
from .base import BaseProvider
from ..models import DeployResult, DeployStatus, DestroyResult, ServiceState
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
    
    def status(self) -> DeployStatus:
        """Get current Azure Container App status."""
        try:
            if not self.config.resource_group:
                return DeployStatus(
                    state=ServiceState.UNKNOWN,
                    message="Resource group not configured",
                    service_name=self.config.service_name,
                    provider="azure",
                    region=self.config.region
                )
            
            result = subprocess.run(
                ['az', 'containerapp', 'show',
                 '--name', self.config.service_name,
                 '--resource-group', self.config.resource_group,
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return DeployStatus(
                    state=ServiceState.NOT_FOUND,
                    message=f"Container App not found: {result.stderr}",
                    service_name=self.config.service_name,
                    provider="azure",
                    region=self.config.region
                )
            
            data = json.loads(result.stdout)
            properties = data.get('properties', {})
            provisioning_state = properties.get('provisioningState', 'Unknown')
            running_status = properties.get('runningStatus', {}).get('state', 'Unknown')
            
            # Get URL
            ingress = properties.get('configuration', {}).get('ingress', {})
            fqdn = ingress.get('fqdn')
            url = f"https://{fqdn}" if fqdn else None
            
            # Get replica count
            template = properties.get('template', {})
            scale = template.get('scale', {})
            min_replicas = scale.get('minReplicas', 0)
            max_replicas = scale.get('maxReplicas', 0)
            
            # Map status to ServiceState
            if provisioning_state == 'Succeeded' and running_status == 'Running':
                state = ServiceState.RUNNING
            elif provisioning_state == 'Succeeded' and running_status == 'Stopped':
                state = ServiceState.STOPPED
            elif provisioning_state in ['Creating', 'Updating']:
                state = ServiceState.PENDING
            elif provisioning_state == 'Failed':
                state = ServiceState.FAILED
            else:
                state = ServiceState.UNKNOWN
            
            return DeployStatus(
                state=state,
                url=url,
                message=f"Provisioning: {provisioning_state}, Running: {running_status}",
                service_name=self.config.service_name,
                provider="azure",
                region=self.config.region,
                healthy=state == ServiceState.RUNNING,
                instances_running=min_replicas if state == ServiceState.RUNNING else 0,
                instances_desired=min_replicas,
                created_at=data.get('systemData', {}).get('createdAt'),
                updated_at=data.get('systemData', {}).get('lastModifiedAt'),
                metadata={
                    "resource_group": self.config.resource_group,
                    "provisioning_state": provisioning_state,
                    "running_status": running_status,
                    "min_replicas": min_replicas,
                    "max_replicas": max_replicas
                }
            )
            
        except Exception as e:
            return DeployStatus(
                state=ServiceState.UNKNOWN,
                message=f"Failed to get status: {e}",
                service_name=self.config.service_name,
                provider="azure",
                region=self.config.region
            )
    
    def destroy(self, force: bool = False) -> DestroyResult:
        """Destroy Azure Container App and related resources."""
        try:
            if not self.config.resource_group:
                return DestroyResult(
                    success=False,
                    message="Resource group not configured",
                    error="Please specify resource_group in cloud config"
                )
            
            deleted_resources = []
            
            # Step 1: Delete the Container App
            print(f"🗑️ Deleting Container App: {self.config.service_name}")
            result = subprocess.run(
                ['az', 'containerapp', 'delete',
                 '--name', self.config.service_name,
                 '--resource-group', self.config.resource_group,
                 '--yes'],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                deleted_resources.append(f"containerapp:{self.config.service_name}")
            else:
                return DestroyResult(
                    success=False,
                    message="Failed to delete Container App",
                    error=result.stderr,
                    resources_deleted=deleted_resources
                )
            
            # Step 2: Optionally delete environment if force
            if force:
                env_name = f"{self.config.service_name}-env"
                print(f"🗑️ Deleting Container Apps environment: {env_name}")
                env_result = subprocess.run(
                    ['az', 'containerapp', 'env', 'delete',
                     '--name', env_name,
                     '--resource-group', self.config.resource_group,
                     '--yes'],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if env_result.returncode == 0:
                    deleted_resources.append(f"containerapp-env:{env_name}")
            
            return DestroyResult(
                success=True,
                message="Successfully destroyed Azure Container App",
                resources_deleted=deleted_resources,
                metadata={
                    "resource_group": self.config.resource_group,
                    "region": self.config.region
                }
            )
            
        except Exception as e:
            return DestroyResult(
                success=False,
                message="Failed to destroy Azure resources",
                error=str(e)
            )

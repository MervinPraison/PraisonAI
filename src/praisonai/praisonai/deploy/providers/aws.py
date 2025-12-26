"""
AWS provider for cloud deployment (ECS Fargate).
"""
import subprocess
import json
from typing import Dict, Any
from .base import BaseProvider
from ..models import CloudConfig, DeployResult, DeployStatus, DestroyResult, ServiceState
from ..doctor import DoctorReport, DoctorCheckResult, check_aws_cli


class AWSProvider(BaseProvider):
    """AWS deployment provider using ECS Fargate."""
    
    def doctor(self) -> DoctorReport:
        """Run AWS-specific health checks."""
        checks = [check_aws_cli()]
        
        # Check if region is configured
        try:
            result = subprocess.run(
                ['aws', 'configure', 'get', 'region'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                checks.append(DoctorCheckResult(
                    name="AWS Region",
                    passed=True,
                    message=f"Region configured: {result.stdout.strip()}"
                ))
            else:
                checks.append(DoctorCheckResult(
                    name="AWS Region",
                    passed=False,
                    message="No default region configured",
                    fix_suggestion="Run: aws configure set region us-east-1"
                ))
        except Exception as e:
            checks.append(DoctorCheckResult(
                name="AWS Region",
                passed=False,
                message=f"Failed to check region: {e}",
                fix_suggestion="Run: aws configure"
            ))
        
        return DoctorReport(checks=checks)
    
    def plan(self) -> Dict[str, Any]:
        """Generate AWS deployment plan."""
        cluster_name = self.config.cluster_name or f"{self.config.service_name}-cluster"
        
        plan = {
            "provider": "aws",
            "service_name": self.config.service_name,
            "region": self.config.region,
            "cluster_name": cluster_name,
            "launch_type": "FARGATE",
            "cpu": self.config.cpu,
            "memory": self.config.memory,
            "desired_count": self.config.min_instances,
            "image": self.config.image or f"{self.config.service_name}:latest",
            "steps": [
                "1. Create ECS cluster (if not exists)",
                "2. Create task definition",
                "3. Create or update ECS service",
                "4. Wait for service to stabilize"
            ]
        }
        
        return plan
    
    def deploy(self) -> DeployResult:
        """Deploy to AWS ECS Fargate."""
        try:
            cluster_name = self.config.cluster_name or f"{self.config.service_name}-cluster"
            
            # Step 1: Create cluster if not exists
            print(f"📦 Creating ECS cluster: {cluster_name}")
            try:
                subprocess.run(
                    ['aws', 'ecs', 'create-cluster',
                     '--cluster-name', cluster_name,
                     '--region', self.config.region],
                    capture_output=True,
                    timeout=30
                )
            except Exception:
                pass  # Cluster may already exist
            
            # Step 2: Register task definition
            print(f"📝 Registering task definition")
            
            task_def = {
                "family": self.config.service_name,
                "networkMode": "awsvpc",
                "requiresCompatibilities": ["FARGATE"],
                "cpu": self.config.cpu,
                "memory": self.config.memory,
                "containerDefinitions": [
                    {
                        "name": self.config.service_name,
                        "image": self.config.image or f"{self.config.service_name}:latest",
                        "portMappings": [
                            {
                                "containerPort": 8005,
                                "protocol": "tcp"
                            }
                        ],
                        "environment": [
                            {"name": k, "value": v}
                            for k, v in (self.config.env_vars or {}).items()
                        ]
                    }
                ]
            }
            
            result = subprocess.run(
                ['aws', 'ecs', 'register-task-definition',
                 '--cli-input-json', json.dumps(task_def),
                 '--region', self.config.region],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return DeployResult(
                    success=False,
                    message="Failed to register task definition",
                    error=result.stderr
                )
            
            # Step 3: Create or update service
            print(f"🚀 Deploying service: {self.config.service_name}")
            
            # Try to update first, create if doesn't exist
            update_result = subprocess.run(
                ['aws', 'ecs', 'update-service',
                 '--cluster', cluster_name,
                 '--service', self.config.service_name,
                 '--task-definition', self.config.service_name,
                 '--desired-count', str(self.config.min_instances),
                 '--region', self.config.region],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if update_result.returncode != 0:
                # Service doesn't exist, create it
                # Note: This is simplified - production would need VPC/subnet/security group config
                return DeployResult(
                    success=False,
                    message="Service creation requires VPC configuration",
                    error="Please create the service manually with proper VPC/subnet/security group configuration, then use update"
                )
            
            return DeployResult(
                success=True,
                message=f"Service deployed successfully to AWS ECS",
                url=f"https://console.aws.amazon.com/ecs/home?region={self.config.region}#/clusters/{cluster_name}/services/{self.config.service_name}",
                metadata={
                    "cluster": cluster_name,
                    "service": self.config.service_name,
                    "region": self.config.region
                }
            )
        
        except Exception as e:
            return DeployResult(
                success=False,
                message="AWS deployment failed",
                error=str(e)
            )
    
    def status(self) -> DeployStatus:
        """Get current AWS ECS service status."""
        try:
            cluster_name = self.config.cluster_name or f"{self.config.service_name}-cluster"
            
            result = subprocess.run(
                ['aws', 'ecs', 'describe-services',
                 '--cluster', cluster_name,
                 '--services', self.config.service_name,
                 '--region', self.config.region,
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return DeployStatus(
                    state=ServiceState.NOT_FOUND,
                    message=f"Service not found or error: {result.stderr}",
                    service_name=self.config.service_name,
                    provider="aws",
                    region=self.config.region
                )
            
            data = json.loads(result.stdout)
            services = data.get('services', [])
            
            if not services:
                return DeployStatus(
                    state=ServiceState.NOT_FOUND,
                    message="Service not found",
                    service_name=self.config.service_name,
                    provider="aws",
                    region=self.config.region
                )
            
            service = services[0]
            status_str = service.get('status', 'UNKNOWN')
            running_count = service.get('runningCount', 0)
            desired_count = service.get('desiredCount', 0)
            
            # Map AWS status to ServiceState
            if status_str == 'ACTIVE' and running_count > 0:
                state = ServiceState.RUNNING
            elif status_str == 'ACTIVE' and running_count == 0:
                state = ServiceState.STOPPED
            elif status_str == 'DRAINING':
                state = ServiceState.PENDING
            elif status_str == 'INACTIVE':
                state = ServiceState.STOPPED
            else:
                state = ServiceState.UNKNOWN
            
            return DeployStatus(
                state=state,
                url=f"https://console.aws.amazon.com/ecs/home?region={self.config.region}#/clusters/{cluster_name}/services/{self.config.service_name}",
                message=f"Status: {status_str}",
                service_name=self.config.service_name,
                provider="aws",
                region=self.config.region,
                healthy=running_count >= desired_count and running_count > 0,
                instances_running=running_count,
                instances_desired=desired_count,
                created_at=service.get('createdAt'),
                metadata={
                    "cluster": cluster_name,
                    "task_definition": service.get('taskDefinition'),
                    "launch_type": service.get('launchType'),
                    "deployments": len(service.get('deployments', []))
                }
            )
            
        except Exception as e:
            return DeployStatus(
                state=ServiceState.UNKNOWN,
                message=f"Failed to get status: {e}",
                service_name=self.config.service_name,
                provider="aws",
                region=self.config.region
            )
    
    def destroy(self, force: bool = False) -> DestroyResult:
        """Destroy AWS ECS service and related resources."""
        try:
            cluster_name = self.config.cluster_name or f"{self.config.service_name}-cluster"
            deleted_resources = []
            
            # Step 1: Update service desired count to 0
            print(f"🛑 Stopping service: {self.config.service_name}")
            subprocess.run(
                ['aws', 'ecs', 'update-service',
                 '--cluster', cluster_name,
                 '--service', self.config.service_name,
                 '--desired-count', '0',
                 '--region', self.config.region],
                capture_output=True,
                timeout=30
            )
            
            # Step 2: Delete the service
            print(f"🗑️ Deleting service: {self.config.service_name}")
            result = subprocess.run(
                ['aws', 'ecs', 'delete-service',
                 '--cluster', cluster_name,
                 '--service', self.config.service_name,
                 '--force' if force else '--no-force',
                 '--region', self.config.region],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                deleted_resources.append(f"ecs-service:{self.config.service_name}")
            else:
                return DestroyResult(
                    success=False,
                    message="Failed to delete service",
                    error=result.stderr,
                    resources_deleted=deleted_resources
                )
            
            # Step 3: Optionally delete cluster if empty
            if force:
                print(f"🗑️ Deleting cluster: {cluster_name}")
                cluster_result = subprocess.run(
                    ['aws', 'ecs', 'delete-cluster',
                     '--cluster', cluster_name,
                     '--region', self.config.region],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if cluster_result.returncode == 0:
                    deleted_resources.append(f"ecs-cluster:{cluster_name}")
            
            return DestroyResult(
                success=True,
                message=f"Successfully destroyed AWS ECS service",
                resources_deleted=deleted_resources,
                metadata={
                    "cluster": cluster_name,
                    "region": self.config.region
                }
            )
            
        except Exception as e:
            return DestroyResult(
                success=False,
                message="Failed to destroy AWS resources",
                error=str(e)
            )

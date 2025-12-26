"""
AWS provider for cloud deployment (ECS Fargate).
"""
import subprocess
import json
from typing import Dict, Any
from .base import BaseProvider
from ..models import CloudConfig, DeployResult
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

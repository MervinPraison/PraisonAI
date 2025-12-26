"""
GCP provider for cloud deployment (Cloud Run).
"""
import subprocess
import json
from typing import Dict, Any
from .base import BaseProvider
from ..models import DeployResult
from ..doctor import DoctorReport, DoctorCheckResult, check_gcp_cli


class GCPProvider(BaseProvider):
    """GCP deployment provider using Cloud Run."""
    
    def doctor(self) -> DoctorReport:
        """Run GCP-specific health checks."""
        checks = [check_gcp_cli()]
        
        # Check if Cloud Run API is enabled
        if self.config.project_id:
            try:
                result = subprocess.run(
                    ['gcloud', 'services', 'list',
                     '--enabled',
                     '--filter', 'name:run.googleapis.com',
                     '--project', self.config.project_id,
                     '--format', 'json'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    services = json.loads(result.stdout)
                    if services:
                        checks.append(DoctorCheckResult(
                            name="Cloud Run API",
                            passed=True,
                            message="Cloud Run API is enabled"
                        ))
                    else:
                        checks.append(DoctorCheckResult(
                            name="Cloud Run API",
                            passed=False,
                            message="Cloud Run API is not enabled",
                            fix_suggestion=f"Run: gcloud services enable run.googleapis.com --project={self.config.project_id}"
                        ))
            except Exception as e:
                checks.append(DoctorCheckResult(
                    name="Cloud Run API",
                    passed=False,
                    message=f"Failed to check Cloud Run API: {e}",
                    fix_suggestion="Check gcloud configuration"
                ))
        
        return DoctorReport(checks=checks)
    
    def plan(self) -> Dict[str, Any]:
        """Generate GCP deployment plan."""
        plan = {
            "provider": "gcp",
            "service_name": self.config.service_name,
            "region": self.config.region,
            "project_id": self.config.project_id,
            "cpu": self.config.cpu,
            "memory": f"{self.config.memory}Mi",
            "min_instances": self.config.min_instances,
            "max_instances": self.config.max_instances,
            "image": self.config.image or f"gcr.io/{self.config.project_id}/{self.config.service_name}:latest",
            "steps": [
                "1. Enable Cloud Run API (if not enabled)",
                "2. Deploy service to Cloud Run",
                "3. Set IAM policy for public access (optional)",
                "4. Get service URL"
            ]
        }
        
        return plan
    
    def deploy(self) -> DeployResult:
        """Deploy to GCP Cloud Run."""
        try:
            if not self.config.project_id:
                return DeployResult(
                    success=False,
                    message="Project ID is required for GCP deployment",
                    error="Please specify project_id in cloud config"
                )
            
            # Step 1: Enable Cloud Run API
            print(f"🔧 Enabling Cloud Run API")
            try:
                subprocess.run(
                    ['gcloud', 'services', 'enable', 'run.googleapis.com',
                     '--project', self.config.project_id],
                    capture_output=True,
                    timeout=60
                )
            except Exception:
                pass  # May already be enabled
            
            # Step 2: Deploy to Cloud Run
            print(f"🚀 Deploying to Cloud Run: {self.config.service_name}")
            
            cmd = [
                'gcloud', 'run', 'deploy', self.config.service_name,
                '--image', self.config.image or f"gcr.io/{self.config.project_id}/{self.config.service_name}:latest",
                '--platform', 'managed',
                '--region', self.config.region,
                '--project', self.config.project_id,
                '--cpu', str(self.config.cpu),
                '--memory', f"{self.config.memory}Mi",
                '--min-instances', str(self.config.min_instances),
                '--max-instances', str(self.config.max_instances),
                '--port', '8005',
                '--allow-unauthenticated'
            ]
            
            # Add environment variables
            if self.config.env_vars:
                env_str = ','.join([f"{k}={v}" for k, v in self.config.env_vars.items()])
                cmd.extend(['--set-env-vars', env_str])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180
            )
            
            if result.returncode == 0:
                # Extract URL from output
                try:
                    show_result = subprocess.run(
                        ['gcloud', 'run', 'services', 'describe',
                         self.config.service_name,
                         '--platform', 'managed',
                         '--region', self.config.region,
                         '--project', self.config.project_id,
                         '--format', 'json'],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if show_result.returncode == 0:
                        service_data = json.loads(show_result.stdout)
                        url = service_data.get('status', {}).get('url')
                    else:
                        url = None
                except Exception:
                    url = None
                
                return DeployResult(
                    success=True,
                    message=f"Service deployed successfully to Cloud Run",
                    url=url,
                    metadata={
                        "project_id": self.config.project_id,
                        "service_name": self.config.service_name,
                        "region": self.config.region
                    }
                )
            else:
                return DeployResult(
                    success=False,
                    message="Failed to deploy to Cloud Run",
                    error=result.stderr
                )
        
        except Exception as e:
            return DeployResult(
                success=False,
                message="GCP deployment failed",
                error=str(e)
            )

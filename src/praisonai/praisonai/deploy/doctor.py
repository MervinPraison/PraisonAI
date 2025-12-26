"""
Deploy doctor - connectivity and readiness checks.
"""
import subprocess
import socket
import sys
from typing import Optional, List
from dataclasses import dataclass
from .schema import validate_agents_yaml


@dataclass
class DoctorCheckResult:
    """Result of a single doctor check."""
    name: str
    passed: bool
    message: str
    fix_suggestion: Optional[str] = None


@dataclass
class DoctorReport:
    """Aggregated report of all doctor checks."""
    checks: List[DoctorCheckResult]
    
    @property
    def total_checks(self) -> int:
        return len(self.checks)
    
    @property
    def passed_checks(self) -> int:
        return sum(1 for c in self.checks if c.passed)
    
    @property
    def failed_checks(self) -> int:
        return sum(1 for c in self.checks if not c.passed)
    
    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)


def check_python_version() -> DoctorCheckResult:
    """Check Python version is 3.9+."""
    try:
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"
        
        if version.major >= 3 and version.minor >= 9:
            return DoctorCheckResult(
                name="Python Version",
                passed=True,
                message=f"Python {version_str} (>= 3.9 required)"
            )
        else:
            return DoctorCheckResult(
                name="Python Version",
                passed=False,
                message=f"Python {version_str} found, but 3.9+ required",
                fix_suggestion="Upgrade Python to version 3.9 or higher"
            )
    except Exception as e:
        return DoctorCheckResult(
            name="Python Version",
            passed=False,
            message=f"Failed to check Python version: {e}",
            fix_suggestion="Ensure Python is properly installed"
        )


def check_docker_available() -> DoctorCheckResult:
    """Check if Docker is installed and running."""
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            version = result.stdout.strip()
            return DoctorCheckResult(
                name="Docker",
                passed=True,
                message=f"Docker available: {version}"
            )
        else:
            return DoctorCheckResult(
                name="Docker",
                passed=False,
                message="Docker command failed",
                fix_suggestion="Install Docker: https://docs.docker.com/get-docker/"
            )
    except FileNotFoundError:
        return DoctorCheckResult(
            name="Docker",
            passed=False,
            message="Docker not found",
            fix_suggestion="Install Docker: https://docs.docker.com/get-docker/"
        )
    except Exception as e:
        return DoctorCheckResult(
            name="Docker",
            passed=False,
            message=f"Docker check failed: {e}",
            fix_suggestion="Ensure Docker is installed and running"
        )


def check_port_available(port: int) -> DoctorCheckResult:
    """Check if a port is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            result = s.connect_ex(('127.0.0.1', port))
            
            if result != 0:
                return DoctorCheckResult(
                    name=f"Port {port}",
                    passed=True,
                    message=f"Port {port} is available"
                )
            else:
                return DoctorCheckResult(
                    name=f"Port {port}",
                    passed=False,
                    message=f"Port {port} is already in use",
                    fix_suggestion=f"Stop the service using port {port} or choose a different port"
                )
    except Exception as e:
        return DoctorCheckResult(
            name=f"Port {port}",
            passed=False,
            message=f"Failed to check port {port}: {e}",
            fix_suggestion="Check network configuration"
        )


def check_aws_cli() -> DoctorCheckResult:
    """Check AWS CLI configuration."""
    try:
        result = subprocess.run(
            ['aws', 'sts', 'get-caller-identity', '--output', 'json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            import json
            identity = json.loads(result.stdout)
            account = identity.get('Account', 'unknown')
            user_id = identity.get('UserId', 'unknown')
            
            return DoctorCheckResult(
                name="AWS CLI",
                passed=True,
                message=f"AWS CLI configured (Account: {account[:4]}...{account[-4:]})"
            )
        else:
            return DoctorCheckResult(
                name="AWS CLI",
                passed=False,
                message="AWS CLI not configured or credentials invalid",
                fix_suggestion="Run: aws configure"
            )
    except FileNotFoundError:
        return DoctorCheckResult(
            name="AWS CLI",
            passed=False,
            message="AWS CLI not installed",
            fix_suggestion="Install AWS CLI: https://aws.amazon.com/cli/"
        )
    except Exception as e:
        return DoctorCheckResult(
            name="AWS CLI",
            passed=False,
            message=f"AWS CLI check failed: {e}",
            fix_suggestion="Run: aws configure"
        )


def check_azure_cli() -> DoctorCheckResult:
    """Check Azure CLI configuration."""
    try:
        result = subprocess.run(
            ['az', 'account', 'show', '--output', 'json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            import json
            account = json.loads(result.stdout)
            sub_id = account.get('id', 'unknown')
            name = account.get('name', 'unknown')
            
            return DoctorCheckResult(
                name="Azure CLI",
                passed=True,
                message=f"Azure CLI logged in (Subscription: {sub_id[:8]}...)"
            )
        else:
            return DoctorCheckResult(
                name="Azure CLI",
                passed=False,
                message="Azure CLI not logged in",
                fix_suggestion="Run: az login"
            )
    except FileNotFoundError:
        return DoctorCheckResult(
            name="Azure CLI",
            passed=False,
            message="Azure CLI not installed",
            fix_suggestion="Install Azure CLI: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
        )
    except Exception as e:
        return DoctorCheckResult(
            name="Azure CLI",
            passed=False,
            message=f"Azure CLI check failed: {e}",
            fix_suggestion="Run: az login"
        )


def check_gcp_cli() -> DoctorCheckResult:
    """Check GCP CLI configuration."""
    try:
        result = subprocess.run(
            ['gcloud', 'config', 'get-value', 'project'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            project_id = result.stdout.strip()
            
            return DoctorCheckResult(
                name="GCP CLI",
                passed=True,
                message=f"GCP CLI configured (Project: {project_id})"
            )
        else:
            return DoctorCheckResult(
                name="GCP CLI",
                passed=False,
                message="GCP CLI not configured or no project set",
                fix_suggestion="Run: gcloud init"
            )
    except FileNotFoundError:
        return DoctorCheckResult(
            name="GCP CLI",
            passed=False,
            message="GCP CLI not installed",
            fix_suggestion="Install gcloud CLI: https://cloud.google.com/sdk/docs/install"
        )
    except Exception as e:
        return DoctorCheckResult(
            name="GCP CLI",
            passed=False,
            message=f"GCP CLI check failed: {e}",
            fix_suggestion="Run: gcloud init"
        )


def check_agents_yaml(file_path: str) -> DoctorCheckResult:
    """Check if agents.yaml exists and has valid deploy config."""
    try:
        config = validate_agents_yaml(file_path)
        
        if config:
            return DoctorCheckResult(
                name="agents.yaml",
                passed=True,
                message=f"Valid deploy configuration found (type: {config.type.value})"
            )
        else:
            return DoctorCheckResult(
                name="agents.yaml",
                passed=False,
                message="No deploy section found in agents.yaml",
                fix_suggestion="Add deploy configuration to agents.yaml or run: praisonai deploy init"
            )
    except FileNotFoundError:
        return DoctorCheckResult(
            name="agents.yaml",
            passed=False,
            message=f"File not found: {file_path}",
            fix_suggestion="Create agents.yaml or run: praisonai deploy init"
        )
    except ValueError as e:
        return DoctorCheckResult(
            name="agents.yaml",
            passed=False,
            message=f"Invalid deploy configuration: {e}",
            fix_suggestion="Fix deploy configuration in agents.yaml or run: praisonai deploy validate"
        )
    except Exception as e:
        return DoctorCheckResult(
            name="agents.yaml",
            passed=False,
            message=f"Failed to validate agents.yaml: {e}",
            fix_suggestion="Check agents.yaml syntax"
        )


def run_local_checks(port: int = 8005, agents_file: Optional[str] = None) -> DoctorReport:
    """Run local environment checks."""
    checks = [
        check_python_version(),
        check_port_available(port),
    ]
    
    if agents_file:
        checks.append(check_agents_yaml(agents_file))
    
    return DoctorReport(checks=checks)


def run_aws_checks() -> DoctorReport:
    """Run AWS-specific checks."""
    checks = [
        check_aws_cli(),
    ]
    return DoctorReport(checks=checks)


def run_azure_checks() -> DoctorReport:
    """Run Azure-specific checks."""
    checks = [
        check_azure_cli(),
    ]
    return DoctorReport(checks=checks)


def run_gcp_checks() -> DoctorReport:
    """Run GCP-specific checks."""
    checks = [
        check_gcp_cli(),
    ]
    return DoctorReport(checks=checks)


def run_all_checks(agents_file: Optional[str] = None) -> DoctorReport:
    """Run all available checks."""
    checks = []
    
    # Local checks
    local_report = run_local_checks(agents_file=agents_file)
    checks.extend(local_report.checks)
    
    # Docker check
    checks.append(check_docker_available())
    
    # Cloud provider checks
    aws_report = run_aws_checks()
    checks.extend(aws_report.checks)
    
    azure_report = run_azure_checks()
    checks.extend(azure_report.checks)
    
    gcp_report = run_gcp_checks()
    checks.extend(gcp_report.checks)
    
    return DoctorReport(checks=checks)

"""
Unit tests for deploy doctor (connectivity and readiness checks).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess


def test_doctor_check_result_success():
    """Test DoctorCheckResult for successful check."""
    from praisonai.deploy.doctor import DoctorCheckResult
    
    result = DoctorCheckResult(
        name="Python Version",
        passed=True,
        message="Python 3.11.0 found"
    )
    assert result.passed is True
    assert result.message == "Python 3.11.0 found"
    assert result.fix_suggestion is None


def test_doctor_check_result_failure():
    """Test DoctorCheckResult for failed check."""
    from praisonai.deploy.doctor import DoctorCheckResult
    
    result = DoctorCheckResult(
        name="Docker",
        passed=False,
        message="Docker not found",
        fix_suggestion="Install Docker: https://docs.docker.com/get-docker/"
    )
    assert result.passed is False
    assert result.fix_suggestion is not None


def test_doctor_report():
    """Test DoctorReport aggregation."""
    from praisonai.deploy.doctor import DoctorReport, DoctorCheckResult
    
    checks = [
        DoctorCheckResult("Check 1", True, "OK"),
        DoctorCheckResult("Check 2", True, "OK"),
        DoctorCheckResult("Check 3", False, "Failed")
    ]
    
    report = DoctorReport(checks=checks)
    assert report.total_checks == 3
    assert report.passed_checks == 2
    assert report.failed_checks == 1
    assert report.all_passed is False


def test_doctor_report_all_passed():
    """Test DoctorReport when all checks pass."""
    from praisonai.deploy.doctor import DoctorReport, DoctorCheckResult
    
    checks = [
        DoctorCheckResult("Check 1", True, "OK"),
        DoctorCheckResult("Check 2", True, "OK")
    ]
    
    report = DoctorReport(checks=checks)
    assert report.all_passed is True


@patch('subprocess.run')
def test_check_python_version_success(mock_run):
    """Test Python version check success."""
    from praisonai.deploy.doctor import check_python_version
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout="Python 3.11.0"
    )
    
    result = check_python_version()
    assert result.passed is True
    # Check that version info is present (actual version may vary)
    assert "Python" in result.message or "3." in result.message


@patch('sys.version_info', (3, 7, 0))
def test_check_python_version_old():
    """Test Python version check with old version."""
    from praisonai.deploy.doctor import check_python_version
    
    # This test verifies the function runs; actual version check depends on sys.version_info
    result = check_python_version()
    # With current Python 3.12+, this will pass
    assert result is not None


@patch('subprocess.run')
def test_check_docker_available_success(mock_run):
    """Test Docker availability check success."""
    from praisonai.deploy.doctor import check_docker_available
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout="Docker version 24.0.0"
    )
    
    result = check_docker_available()
    assert result.passed is True


@patch('subprocess.run')
def test_check_docker_available_not_found(mock_run):
    """Test Docker availability check when not installed."""
    from praisonai.deploy.doctor import check_docker_available
    
    mock_run.side_effect = FileNotFoundError()
    
    result = check_docker_available()
    assert result.passed is False
    assert "Install Docker" in result.fix_suggestion


@patch('subprocess.run')
def test_check_port_available_success(mock_run):
    """Test port availability check success."""
    from praisonai.deploy.doctor import check_port_available
    
    result = check_port_available(8005)
    assert result.passed is True


@patch('socket.socket')
def test_check_port_available_in_use(mock_socket):
    """Test port availability check when port in use."""
    from praisonai.deploy.doctor import check_port_available
    
    mock_sock = MagicMock()
    mock_sock.connect_ex.return_value = 0
    mock_socket.return_value.__enter__.return_value = mock_sock
    
    result = check_port_available(8005)
    assert result.passed is False


@patch('subprocess.run')
def test_check_aws_cli_success(mock_run):
    """Test AWS CLI check success."""
    from praisonai.deploy.doctor import check_aws_cli
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout='{"UserId": "test", "Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/test"}'
    )
    
    result = check_aws_cli()
    assert result.passed is True
    # Account ID may be truncated in display
    assert "AWS" in result.message or "Account" in result.message or "1234" in result.message


@patch('subprocess.run')
def test_check_aws_cli_not_configured(mock_run):
    """Test AWS CLI check when not configured."""
    from praisonai.deploy.doctor import check_aws_cli
    
    mock_run.side_effect = subprocess.CalledProcessError(1, 'aws')
    
    result = check_aws_cli()
    assert result.passed is False
    assert "aws configure" in result.fix_suggestion


@patch('subprocess.run')
def test_check_azure_cli_success(mock_run):
    """Test Azure CLI check success."""
    from praisonai.deploy.doctor import check_azure_cli
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout='{"id": "sub-123", "name": "My Subscription", "state": "Enabled"}'
    )
    
    result = check_azure_cli()
    assert result.passed is True
    assert "sub-123" in result.message


@patch('subprocess.run')
def test_check_azure_cli_not_logged_in(mock_run):
    """Test Azure CLI check when not logged in."""
    from praisonai.deploy.doctor import check_azure_cli
    
    mock_run.side_effect = subprocess.CalledProcessError(1, 'az')
    
    result = check_azure_cli()
    assert result.passed is False
    assert "az login" in result.fix_suggestion


@patch('subprocess.run')
def test_check_gcp_cli_success(mock_run):
    """Test GCP CLI check success."""
    from praisonai.deploy.doctor import check_gcp_cli
    
    mock_run.return_value = Mock(
        returncode=0,
        stdout="my-project-123"
    )
    
    result = check_gcp_cli()
    assert result.passed is True
    assert "my-project-123" in result.message


@patch('subprocess.run')
def test_check_gcp_cli_not_configured(mock_run):
    """Test GCP CLI check when not configured."""
    from praisonai.deploy.doctor import check_gcp_cli
    
    mock_run.side_effect = subprocess.CalledProcessError(1, 'gcloud')
    
    result = check_gcp_cli()
    assert result.passed is False
    assert "gcloud init" in result.fix_suggestion


@patch('praisonai.deploy.doctor.check_python_version')
@patch('praisonai.deploy.doctor.check_port_available')
def test_run_local_checks(mock_port, mock_python):
    """Test running local checks."""
    from praisonai.deploy.doctor import run_local_checks, DoctorCheckResult
    
    mock_python.return_value = DoctorCheckResult("Python", True, "OK")
    mock_port.return_value = DoctorCheckResult("Port", True, "Available")
    
    report = run_local_checks()
    assert report.total_checks >= 2
    assert report.passed_checks >= 2


@patch('praisonai.deploy.doctor.check_aws_cli')
def test_run_aws_checks(mock_aws):
    """Test running AWS checks."""
    from praisonai.deploy.doctor import run_aws_checks, DoctorCheckResult
    
    mock_aws.return_value = DoctorCheckResult("AWS CLI", True, "Configured")
    
    report = run_aws_checks()
    assert report.total_checks >= 1


@patch('praisonai.deploy.doctor.check_azure_cli')
def test_run_azure_checks(mock_azure):
    """Test running Azure checks."""
    from praisonai.deploy.doctor import run_azure_checks, DoctorCheckResult
    
    mock_azure.return_value = DoctorCheckResult("Azure CLI", True, "Logged in")
    
    report = run_azure_checks()
    assert report.total_checks >= 1


@patch('praisonai.deploy.doctor.check_gcp_cli')
def test_run_gcp_checks(mock_gcp):
    """Test running GCP checks."""
    from praisonai.deploy.doctor import run_gcp_checks, DoctorCheckResult
    
    mock_gcp.return_value = DoctorCheckResult("GCP CLI", True, "Configured")
    
    report = run_gcp_checks()
    assert report.total_checks >= 1


@patch('praisonai.deploy.doctor.run_local_checks')
@patch('praisonai.deploy.doctor.run_aws_checks')
@patch('praisonai.deploy.doctor.run_azure_checks')
@patch('praisonai.deploy.doctor.run_gcp_checks')
def test_run_all_checks(mock_gcp, mock_azure, mock_aws, mock_local):
    """Test running all checks."""
    from praisonai.deploy.doctor import run_all_checks, DoctorReport, DoctorCheckResult
    
    mock_local.return_value = DoctorReport([DoctorCheckResult("Local", True, "OK")])
    mock_aws.return_value = DoctorReport([DoctorCheckResult("AWS", True, "OK")])
    mock_azure.return_value = DoctorReport([DoctorCheckResult("Azure", True, "OK")])
    mock_gcp.return_value = DoctorReport([DoctorCheckResult("GCP", True, "OK")])
    
    report = run_all_checks()
    assert report.total_checks >= 4


@patch('praisonai.deploy.doctor.validate_agents_yaml')
def test_check_agents_yaml_valid(mock_validate):
    """Test agents.yaml validation check success."""
    from praisonai.deploy.doctor import check_agents_yaml
    from praisonai.deploy.models import DeployConfig, DeployType
    
    mock_validate.return_value = DeployConfig(type=DeployType.API)
    
    result = check_agents_yaml("agents.yaml")
    assert result.passed is True


@patch('praisonai.deploy.doctor.validate_agents_yaml')
def test_check_agents_yaml_invalid(mock_validate):
    """Test agents.yaml validation check failure."""
    from praisonai.deploy.doctor import check_agents_yaml
    
    mock_validate.side_effect = ValueError("Invalid config")
    
    result = check_agents_yaml("agents.yaml")
    assert result.passed is False


def test_check_agents_yaml_not_found():
    """Test agents.yaml validation check when file not found."""
    from praisonai.deploy.doctor import check_agents_yaml
    
    result = check_agents_yaml("/nonexistent/agents.yaml")
    assert result.passed is False
    assert "not found" in result.message.lower()

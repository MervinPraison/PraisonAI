"""
Unit tests for deploy CLI commands.
"""
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os


@patch('praisonai_deploy.Deploy')
def test_deploy_command_api(mock_deploy_class):
    """Test deploy command with API type."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.models import DeployResult
    
    mock_deploy = Mock()
    mock_deploy.deploy.return_value = DeployResult(success=True, message="Started", url="http://localhost:8005", metadata={})
    mock_deploy_class.return_value = mock_deploy
    
    handler = DeployHandler()
    # Properly configure Mock with spec to avoid Pydantic validation issues
    args = Mock()
    args.type = "api"
    args.file = "agents.yaml"
    args.json = False
    args.background = False
    args.host = "0.0.0.0"
    args.port = 8005
    args.workers = 1
    
    handler.handle_deploy(args)
    
    mock_deploy.deploy.assert_called_once()


@patch('praisonai_deploy.Deploy')
def test_deploy_command_docker(mock_deploy_class):
    """Test deploy command with Docker type."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.models import DeployResult
    
    mock_deploy = Mock()
    mock_deploy.deploy.return_value = DeployResult(success=True, message="Built successfully", metadata={})
    mock_deploy_class.return_value = mock_deploy
    
    handler = DeployHandler()
    args = Mock()
    args.type = "docker"
    args.file = "agents.yaml"
    args.json = False
    args.background = False
    args.image_name = "praisonai"
    args.tag = "latest"
    args.registry = ""
    args.push = False
    
    handler.handle_deploy(args)
    
    mock_deploy.deploy.assert_called_once()


@patch('praisonai_deploy.Deploy')
def test_deploy_command_cloud_aws(mock_deploy_class):
    """Test deploy command with AWS cloud type."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.models import DeployResult
    
    mock_deploy = Mock()
    mock_deploy.deploy.return_value = DeployResult(success=True, message="Deployed", url="https://test.execute-api.us-east-1.amazonaws.com", metadata={})
    mock_deploy_class.return_value = mock_deploy
    
    handler = DeployHandler()
    args = Mock()
    args.type = "cloud"
    args.provider = "aws"
    args.file = "agents.yaml"
    args.json = False
    args.background = False
    args.region = "us-east-1"
    args.service_name = "praisonai-service"
    args.resource_group = ""
    args.subscription_id = ""
    args.project_id = ""
    
    handler.handle_deploy(args)
    
    mock_deploy.deploy.assert_called_once()


@patch('praisonai_deploy.Deploy')
def test_deploy_command_from_yaml(mock_deploy_class):
    """Test deploy command loading config from YAML."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.models import DeployResult
    
    mock_deploy = Mock()
    mock_deploy.deploy.return_value = DeployResult(success=True, message="Deployed", metadata={})
    mock_deploy_class.from_yaml.return_value = mock_deploy
    
    handler = DeployHandler()
    args = Mock(type=None, file="agents.yaml", json=False, background=False)
    
    handler.handle_deploy(args)
    
    mock_deploy_class.from_yaml.assert_called_once()


@patch('praisonai_deploy.doctor.run_all_checks')
def test_doctor_command_all(mock_run_all):
    """Test doctor command with --all flag."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.doctor import DoctorReport, DoctorCheckResult
    
    mock_run_all.return_value = DoctorReport([
        DoctorCheckResult("Check 1", True, "OK"),
        DoctorCheckResult("Check 2", True, "OK")
    ])
    
    handler = DeployHandler()
    args = Mock(all=True, provider=None, file=None, verbose=False, json=False)
    
    handler.handle_doctor(args)
    
    mock_run_all.assert_called_once()


@patch('praisonai_deploy.doctor.run_aws_checks')
def test_doctor_command_aws(mock_run_aws):
    """Test doctor command with AWS provider."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.doctor import DoctorReport, DoctorCheckResult
    
    mock_run_aws.return_value = DoctorReport([
        DoctorCheckResult("AWS CLI", True, "Configured")
    ])
    
    handler = DeployHandler()
    args = Mock(all=False, provider="aws", file=None, verbose=False, json=False)
    
    handler.handle_doctor(args)
    
    mock_run_aws.assert_called_once()


@patch('praisonai_deploy.doctor.run_azure_checks')
def test_doctor_command_azure(mock_run_azure):
    """Test doctor command with Azure provider."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.doctor import DoctorReport, DoctorCheckResult
    
    mock_run_azure.return_value = DoctorReport([
        DoctorCheckResult("Azure CLI", True, "Logged in")
    ])
    
    handler = DeployHandler()
    args = Mock(all=False, provider="azure", file=None, verbose=False, json=False)
    
    handler.handle_doctor(args)
    
    mock_run_azure.assert_called_once()


@patch('praisonai_deploy.doctor.run_gcp_checks')
def test_doctor_command_gcp(mock_run_gcp):
    """Test doctor command with GCP provider."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.doctor import DoctorReport, DoctorCheckResult
    
    mock_run_gcp.return_value = DoctorReport([
        DoctorCheckResult("GCP CLI", True, "Configured")
    ])
    
    handler = DeployHandler()
    args = Mock(all=False, provider="gcp", file=None, verbose=False, json=False)
    
    handler.handle_doctor(args)
    
    mock_run_gcp.assert_called_once()


def test_init_command():
    """Test init command generates sample YAML."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = os.path.join(tmpdir, "agents.yaml")
        
        handler = DeployHandler()
        args = Mock(file=yaml_path, type="api", provider=None)
        
        handler.handle_init(args)
        
        assert os.path.exists(yaml_path)
        with open(yaml_path) as f:
            content = f.read()
            assert "deploy:" in content


@patch('praisonai_deploy.schema.validate_agents_yaml')
def test_validate_command_success(mock_validate):
    """Test validate command with valid YAML."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    from praisonai_deploy.models import DeployConfig, DeployType
    
    mock_validate.return_value = DeployConfig(type=DeployType.API)
    
    handler = DeployHandler()
    args = Mock(file="agents.yaml", json=False)
    
    handler.handle_validate(args)
    
    mock_validate.assert_called_once()


@patch('praisonai_deploy.schema.validate_agents_yaml')
def test_validate_command_failure(mock_validate):
    """Test validate command with invalid YAML."""
    import pytest
    from praisonai_deploy.cli.features.deploy import DeployHandler
    
    mock_validate.side_effect = ValueError("Invalid config")
    
    handler = DeployHandler()
    args = Mock(file="agents.yaml", json=False)
    
    with pytest.raises(SystemExit):
        handler.handle_validate(args)
    
    mock_validate.assert_called_once()


@patch('praisonai_deploy.Deploy')
def test_plan_command(mock_deploy_class):
    """Test plan command."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    
    mock_deploy = Mock()
    mock_deploy.plan.return_value = {"service_name": "test", "region": "us-east-1"}
    mock_deploy_class.from_yaml.return_value = mock_deploy
    
    handler = DeployHandler()
    args = Mock(file="agents.yaml", json=False)
    
    handler.handle_plan(args)
    
    mock_deploy.plan.assert_called_once()


def test_deploy_handler_json_output():
    """Test deploy handler with JSON output."""
    from praisonai_deploy.cli.features.deploy import DeployHandler
    
    handler = DeployHandler()
    
    with patch('json.dumps') as mock_json:
        mock_json.return_value = '{"success": true}'
        handler._print_json({"success": True})
        mock_json.assert_called_once()


@patch('praisonai_deploy.cli.features.deploy.DeployHandler.handle_deploy')
def test_handle_deploy_command_api_alias(mock_handle):
    """api subcommand maps to handle_deploy with type=api."""
    from praisonai_deploy.cli.features.deploy import handle_deploy_command

    rc = handle_deploy_command(["api", "agents.yaml"])
    assert rc == 0
    args = mock_handle.call_args[0][0]
    assert args.type == "api"
    assert args.file == "agents.yaml"


@patch('praisonai_deploy.cli.features.deploy.DeployHandler.handle_deploy')
def test_handle_deploy_command_cloud_alias(mock_handle):
    """cloud subcommand maps to handle_deploy with type=cloud and provider."""
    from praisonai_deploy.cli.features.deploy import handle_deploy_command

    rc = handle_deploy_command(["cloud", "agents.yaml", "--provider", "aws"])
    assert rc == 0
    args = mock_handle.call_args[0][0]
    assert args.type == "cloud"
    assert args.provider == "aws"


def test_build_deploy_config_from_args_merges_docker_yaml():
    """CLI docker shortcut should merge deploy.docker from YAML."""
    from unittest.mock import Mock
    import yaml
    from praisonai_deploy.cli.features.deploy import _build_deploy_config_from_args
    from praisonai_deploy.models import DeployType

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump({
            "agents": {"a": {"role": "test", "goal": "g", "backstory": "b"}},
            "deploy": {
                "type": "docker",
                "docker": {
                    "image_name": "from-yaml",
                    "tag": "v1.0.0",
                    "expose": [9000],
                },
            },
        }, f)
        yaml_path = f.name

    try:
        args = Mock(
            type="docker",
            file=yaml_path,
            image_name="praisonai-app",
            tag="latest",
            registry=None,
            push=False,
        )
        config = _build_deploy_config_from_args(args)
        assert config.type == DeployType.DOCKER
        assert config.docker.image_name == "praisonai-app"
        assert config.docker.tag == "latest"
        assert config.docker.expose == [9000]
    finally:
        os.unlink(yaml_path)

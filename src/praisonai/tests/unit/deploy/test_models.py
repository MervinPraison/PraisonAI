"""
Unit tests for deploy models and configuration.
"""
import pytest
from pydantic import ValidationError


def test_deploy_type_enum():
    """Test DeployType enum values."""
    from praisonai.deploy.models import DeployType
    
    assert DeployType.API == "api"
    assert DeployType.DOCKER == "docker"
    assert DeployType.CLOUD == "cloud"


def test_cloud_provider_enum():
    """Test CloudProvider enum values."""
    from praisonai.deploy.models import CloudProvider
    
    assert CloudProvider.AWS == "aws"
    assert CloudProvider.AZURE == "azure"
    assert CloudProvider.GCP == "gcp"


def test_api_config_defaults():
    """Test APIConfig with default values."""
    from praisonai.deploy.models import APIConfig
    
    config = APIConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 8005
    assert config.workers == 1
    assert config.cors_enabled is True
    assert config.auth_enabled is False


def test_api_config_custom():
    """Test APIConfig with custom values."""
    from praisonai.deploy.models import APIConfig
    
    config = APIConfig(
        host="0.0.0.0",
        port=8080,
        workers=4,
        cors_enabled=False,
        auth_enabled=True,
        auth_token="secret123"
    )
    assert config.host == "0.0.0.0"
    assert config.port == 8080
    assert config.workers == 4
    assert config.auth_token == "secret123"


def test_docker_config_defaults():
    """Test DockerConfig with default values."""
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig()
    assert config.image_name == "praisonai-app"
    assert config.tag == "latest"
    assert config.base_image == "python:3.11-slim"
    assert config.expose == [8005]
    assert config.registry is None
    assert config.push is False


def test_docker_config_custom():
    """Test DockerConfig with custom values."""
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig(
        image_name="my-agent",
        tag="v1.0.0",
        base_image="python:3.12-alpine",
        expose=[8080, 9090],
        registry="ghcr.io/myorg",
        push=True
    )
    assert config.image_name == "my-agent"
    assert config.tag == "v1.0.0"
    assert config.expose == [8080, 9090]
    assert config.registry == "ghcr.io/myorg"
    assert config.push is True


def test_cloud_config_aws():
    """Test CloudConfig for AWS."""
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AWS,
        region="us-east-1",
        service_name="my-agent-service",
        cpu="256",
        memory="512"
    )
    assert config.provider == CloudProvider.AWS
    assert config.region == "us-east-1"
    assert config.service_name == "my-agent-service"


def test_cloud_config_azure():
    """Test CloudConfig for Azure."""
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.AZURE,
        region="eastus",
        service_name="my-agent-service",
        resource_group="my-rg",
        subscription_id="sub-123"
    )
    assert config.provider == CloudProvider.AZURE
    assert config.resource_group == "my-rg"
    assert config.subscription_id == "sub-123"


def test_cloud_config_gcp():
    """Test CloudConfig for GCP."""
    from praisonai.deploy.models import CloudConfig, CloudProvider
    
    config = CloudConfig(
        provider=CloudProvider.GCP,
        region="us-central1",
        service_name="my-agent-service",
        project_id="my-project-123"
    )
    assert config.provider == CloudProvider.GCP
    assert config.project_id == "my-project-123"


def test_deploy_config_api_type():
    """Test DeployConfig with API type."""
    from praisonai.deploy.models import DeployConfig, DeployType, APIConfig
    
    config = DeployConfig(
        type=DeployType.API,
        api=APIConfig(port=8080)
    )
    assert config.type == DeployType.API
    assert config.api.port == 8080
    assert config.docker is None
    assert config.cloud is None


def test_deploy_config_docker_type():
    """Test DeployConfig with Docker type."""
    from praisonai.deploy.models import DeployConfig, DeployType, DockerConfig
    
    config = DeployConfig(
        type=DeployType.DOCKER,
        docker=DockerConfig(image_name="test-app")
    )
    assert config.type == DeployType.DOCKER
    assert config.docker.image_name == "test-app"


def test_deploy_config_cloud_type():
    """Test DeployConfig with Cloud type."""
    from praisonai.deploy.models import DeployConfig, DeployType, CloudConfig, CloudProvider
    
    config = DeployConfig(
        type=DeployType.CLOUD,
        cloud=CloudConfig(
            provider=CloudProvider.AWS,
            region="us-west-2",
            service_name="test-service"
        )
    )
    assert config.type == DeployType.CLOUD
    assert config.cloud.provider == CloudProvider.AWS


def test_deploy_config_validation_api_auto_defaults():
    """Test DeployConfig auto-creates API config with defaults for API type."""
    from praisonai.deploy.models import DeployConfig, DeployType, APIConfig
    
    config = DeployConfig(type=DeployType.API)
    assert config.api is not None
    assert isinstance(config.api, APIConfig)
    assert config.api.port == 8005


def test_deploy_config_validation_docker_auto_defaults():
    """Test DeployConfig auto-creates Docker config with defaults for Docker type."""
    from praisonai.deploy.models import DeployConfig, DeployType, DockerConfig
    
    config = DeployConfig(type=DeployType.DOCKER)
    assert config.docker is not None
    assert isinstance(config.docker, DockerConfig)
    assert config.docker.image_name == "praisonai-app"


def test_deploy_config_validation_cloud_missing():
    """Test DeployConfig validation fails when Cloud config missing for Cloud type."""
    from praisonai.deploy.models import DeployConfig, DeployType
    
    with pytest.raises(ValueError, match="cloud config required"):
        DeployConfig(type=DeployType.CLOUD)


def test_deploy_result_success():
    """Test DeployResult for successful deployment."""
    from praisonai.deploy.models import DeployResult
    
    result = DeployResult(
        success=True,
        message="Deployment successful",
        url="http://localhost:8005",
        metadata={"container_id": "abc123"}
    )
    assert result.success is True
    assert result.url == "http://localhost:8005"
    assert result.metadata["container_id"] == "abc123"


def test_deploy_result_failure():
    """Test DeployResult for failed deployment."""
    from praisonai.deploy.models import DeployResult
    
    result = DeployResult(
        success=False,
        message="Deployment failed: connection timeout",
        error="Connection timeout after 30s"
    )
    assert result.success is False
    assert result.error is not None
    assert result.url is None


def test_agent_config_minimal():
    """Test AgentConfig with minimal required fields."""
    from praisonai.deploy.models import AgentConfig
    
    config = AgentConfig(
        name="test-agent",
        entrypoint="agents.yaml"
    )
    assert config.name == "test-agent"
    assert config.entrypoint == "agents.yaml"
    assert config.env == {}
    assert config.secrets == {}


def test_agent_config_full():
    """Test AgentConfig with all fields."""
    from praisonai.deploy.models import AgentConfig
    
    config = AgentConfig(
        name="test-agent",
        entrypoint="agents.yaml",
        env={"MODEL": "gpt-4"},
        secrets={"API_KEY": "secret-ref"},
        ports=[8005, 8006],
        resources={"cpu": "1", "memory": "2Gi"}
    )
    assert config.name == "test-agent"
    assert config.env["MODEL"] == "gpt-4"
    assert config.secrets["API_KEY"] == "secret-ref"
    assert config.ports == [8005, 8006]
    assert config.resources["memory"] == "2Gi"

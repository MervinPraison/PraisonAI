"""
Unit tests for deploy YAML schema validation.
"""
import pytest
import tempfile
import os


def test_validate_agents_yaml_with_deploy_api():
    """Test YAML validation with API deploy config."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    yaml_content = """
name: Test Agent
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users

deploy:
  type: api
  api:
    host: 0.0.0.0
    port: 8080
    workers: 2
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        f.flush()
        
        try:
            config = validate_agents_yaml(f.name)
            assert config.type.value == "api"
            assert config.api.port == 8080
            assert config.api.workers == 2
        finally:
            os.unlink(f.name)


def test_validate_agents_yaml_with_deploy_docker():
    """Test YAML validation with Docker deploy config."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    yaml_content = """
name: Test Agent
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users

deploy:
  type: docker
  docker:
    image_name: my-agent
    tag: v1.0.0
    registry: ghcr.io/myorg
    push: true
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        f.flush()
        
        try:
            config = validate_agents_yaml(f.name)
            assert config.type.value == "docker"
            assert config.docker.image_name == "my-agent"
            assert config.docker.tag == "v1.0.0"
            assert config.docker.push is True
        finally:
            os.unlink(f.name)


def test_validate_agents_yaml_with_deploy_cloud_aws():
    """Test YAML validation with AWS cloud deploy config."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    yaml_content = """
name: Test Agent
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users

deploy:
  type: cloud
  cloud:
    provider: aws
    region: us-east-1
    service_name: my-agent-service
    cpu: "256"
    memory: "512"
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        f.flush()
        
        try:
            config = validate_agents_yaml(f.name)
            assert config.type.value == "cloud"
            assert config.cloud.provider.value == "aws"
            assert config.cloud.region == "us-east-1"
            assert config.cloud.service_name == "my-agent-service"
        finally:
            os.unlink(f.name)


def test_validate_agents_yaml_with_deploy_cloud_azure():
    """Test YAML validation with Azure cloud deploy config."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    yaml_content = """
name: Test Agent
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users

deploy:
  type: cloud
  cloud:
    provider: azure
    region: eastus
    service_name: my-agent-service
    resource_group: my-rg
    subscription_id: sub-123
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        f.flush()
        
        try:
            config = validate_agents_yaml(f.name)
            assert config.type.value == "cloud"
            assert config.cloud.provider.value == "azure"
            assert config.cloud.resource_group == "my-rg"
        finally:
            os.unlink(f.name)


def test_validate_agents_yaml_with_deploy_cloud_gcp():
    """Test YAML validation with GCP cloud deploy config."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    yaml_content = """
name: Test Agent
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users

deploy:
  type: cloud
  cloud:
    provider: gcp
    region: us-central1
    service_name: my-agent-service
    project_id: my-project-123
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        f.flush()
        
        try:
            config = validate_agents_yaml(f.name)
            assert config.type.value == "cloud"
            assert config.cloud.provider.value == "gcp"
            assert config.cloud.project_id == "my-project-123"
        finally:
            os.unlink(f.name)


def test_validate_agents_yaml_no_deploy_section():
    """Test YAML validation when no deploy section present."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    yaml_content = """
name: Test Agent
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        f.flush()
        
        try:
            config = validate_agents_yaml(f.name)
            assert config is None
        finally:
            os.unlink(f.name)


def test_validate_agents_yaml_invalid_type():
    """Test YAML validation with invalid deploy type."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    yaml_content = """
name: Test Agent
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users

deploy:
  type: invalid_type
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        f.flush()
        
        try:
            with pytest.raises(ValueError):
                validate_agents_yaml(f.name)
        finally:
            os.unlink(f.name)


def test_validate_agents_yaml_missing_required_config():
    """Test YAML validation with missing required config for type."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    yaml_content = """
name: Test Agent
framework: praisonai

agents:
  assistant:
    name: Assistant
    role: Helper
    goal: Help users

deploy:
  type: api
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        f.flush()
        
        try:
            config = validate_agents_yaml(f.name)
            assert config.api is not None
        finally:
            os.unlink(f.name)


def test_validate_agents_yaml_file_not_found():
    """Test YAML validation with non-existent file."""
    from praisonai.deploy.schema import validate_agents_yaml
    
    with pytest.raises(FileNotFoundError):
        validate_agents_yaml("/nonexistent/file.yaml")


def test_generate_sample_yaml_api():
    """Test generating sample YAML for API deploy."""
    from praisonai.deploy.schema import generate_sample_yaml
    from praisonai.deploy.models import DeployType
    
    yaml_str = generate_sample_yaml(DeployType.API)
    assert "type: api" in yaml_str
    assert "api:" in yaml_str
    assert "host:" in yaml_str
    assert "port:" in yaml_str


def test_generate_sample_yaml_docker():
    """Test generating sample YAML for Docker deploy."""
    from praisonai.deploy.schema import generate_sample_yaml
    from praisonai.deploy.models import DeployType
    
    yaml_str = generate_sample_yaml(DeployType.DOCKER)
    assert "type: docker" in yaml_str
    assert "docker:" in yaml_str
    assert "image_name:" in yaml_str
    assert "tag:" in yaml_str


def test_generate_sample_yaml_cloud_aws():
    """Test generating sample YAML for AWS cloud deploy."""
    from praisonai.deploy.schema import generate_sample_yaml
    from praisonai.deploy.models import DeployType, CloudProvider
    
    yaml_str = generate_sample_yaml(DeployType.CLOUD, CloudProvider.AWS)
    assert "type: cloud" in yaml_str
    assert "cloud:" in yaml_str
    assert "provider: aws" in yaml_str
    assert "region:" in yaml_str


def test_generate_sample_yaml_cloud_azure():
    """Test generating sample YAML for Azure cloud deploy."""
    from praisonai.deploy.schema import generate_sample_yaml
    from praisonai.deploy.models import DeployType, CloudProvider
    
    yaml_str = generate_sample_yaml(DeployType.CLOUD, CloudProvider.AZURE)
    assert "type: cloud" in yaml_str
    assert "provider: azure" in yaml_str
    assert "resource_group:" in yaml_str


def test_generate_sample_yaml_cloud_gcp():
    """Test generating sample YAML for GCP cloud deploy."""
    from praisonai.deploy.schema import generate_sample_yaml
    from praisonai.deploy.models import DeployType, CloudProvider
    
    yaml_str = generate_sample_yaml(DeployType.CLOUD, CloudProvider.GCP)
    assert "type: cloud" in yaml_str
    assert "provider: gcp" in yaml_str
    assert "project_id:" in yaml_str

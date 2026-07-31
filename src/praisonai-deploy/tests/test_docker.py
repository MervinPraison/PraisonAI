"""
Unit tests for Docker deploy functionality.
"""
from unittest.mock import Mock, patch
import os


def test_generate_dockerfile_basic():
    """Test generating basic Dockerfile."""
    from praisonai_deploy.docker import generate_dockerfile
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig()
    dockerfile = generate_dockerfile("agents.yaml", config)
    
    assert "FROM python:3.11-slim" in dockerfile
    assert "COPY agents.yaml" in dockerfile
    assert "COPY api_server.py" in dockerfile
    assert "pip install" in dockerfile and "praisonai" in dockerfile
    assert "8005" in dockerfile


def test_generate_dockerfile_absolute_path_uses_basename():
    """Absolute agent paths must not break Docker COPY instructions."""
    from praisonai_deploy.docker import generate_dockerfile
    from praisonai_deploy.models import DockerConfig

    dockerfile = generate_dockerfile("/tmp/project/agents.yaml", DockerConfig())

    assert "COPY agents.yaml /app/agents.yaml" in dockerfile
    assert "/tmp/project" not in dockerfile


def test_collect_runtime_env_vars():
    """Runtime env vars from the host are collected for containers."""
    from praisonai_deploy.docker import collect_runtime_env_vars
    import os

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
        env = collect_runtime_env_vars()

    assert env.get("OPENAI_API_KEY") == "sk-test"


def test_generate_dockerfile_custom_base():
    """Test generating Dockerfile with custom base image."""
    from praisonai_deploy.docker import generate_dockerfile
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig(base_image="python:3.12-alpine")
    dockerfile = generate_dockerfile("agents.yaml", config)
    
    assert "FROM python:3.12-alpine" in dockerfile


def test_generate_dockerfile_multiple_ports():
    """Test generating Dockerfile with multiple exposed ports."""
    from praisonai_deploy.docker import generate_dockerfile
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig(expose=[8005, 8006, 9090])
    dockerfile = generate_dockerfile("agents.yaml", config)
    
    assert "EXPOSE 8005" in dockerfile
    assert "EXPOSE 8006" in dockerfile
    assert "EXPOSE 9090" in dockerfile


@patch('subprocess.run')
def test_build_docker_image_success(mock_run):
    """Test building Docker image successfully."""
    from praisonai_deploy.docker import build_docker_image
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig(image_name="test-app", tag="v1.0.0")
    mock_run.return_value = Mock(returncode=0)
    
    result = build_docker_image(config, "/tmp/test")
    
    assert result.success is True
    assert "test-app:v1.0.0" in result.message


@patch('subprocess.run')
def test_build_docker_image_failure(mock_run):
    """Test building Docker image failure."""
    from praisonai_deploy.docker import build_docker_image
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig(image_name="test-app")
    mock_run.side_effect = Exception("Build failed")
    
    result = build_docker_image(config, "/tmp/test")
    
    assert result.success is False
    assert result.error is not None


@patch('subprocess.run')
def test_run_docker_container_success(mock_run):
    """Test running Docker container successfully."""
    from praisonai_deploy.docker import run_docker_container
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig(image_name="test-app", tag="latest")
    mock_run.return_value = Mock(returncode=0, stdout="abc123def456")
    
    result = run_docker_container(config)
    
    assert result.success is True
    assert "container_id" in result.metadata


@patch('subprocess.run')
def test_run_docker_container_with_env(mock_run):
    """Test running Docker container with environment variables."""
    from praisonai_deploy.docker import run_docker_container
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig(image_name="test-app")
    env_vars = {"MODEL": "gpt-4", "API_KEY": "secret"}
    mock_run.return_value = Mock(returncode=0, stdout="abc123")
    
    result = run_docker_container(config, env_vars=env_vars)
    
    assert result.success is True


@patch('subprocess.run')
def test_push_docker_image_success(mock_run):
    """Test pushing Docker image successfully."""
    from praisonai_deploy.docker import push_docker_image
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig(
        image_name="test-app",
        tag="v1.0.0",
        registry="ghcr.io/myorg",
        push=True
    )
    mock_run.return_value = Mock(returncode=0)
    
    result = push_docker_image(config)
    
    assert result.success is True


@patch('subprocess.run')
def test_push_docker_image_failure(mock_run):
    """Test pushing Docker image failure."""
    from praisonai_deploy.docker import push_docker_image
    from praisonai_deploy.models import DockerConfig
    
    config = DockerConfig(
        image_name="test-app",
        registry="ghcr.io/myorg",
        push=True
    )
    mock_run.side_effect = Exception("Push failed")
    
    result = push_docker_image(config)
    
    assert result.success is False


@patch('subprocess.run')
def test_stop_docker_container(mock_run):
    """Test stopping Docker container."""
    from praisonai_deploy.docker import stop_docker_container
    
    mock_run.return_value = Mock(returncode=0)
    
    result = stop_docker_container("abc123")
    assert result is True


@patch('subprocess.run')
def test_check_docker_installed_success(mock_run):
    """Test checking Docker installation successfully."""
    from praisonai_deploy.docker import check_docker_installed
    
    mock_run.return_value = Mock(returncode=0, stdout="Docker version 24.0.0")
    
    result = check_docker_installed()
    assert result is True


@patch('subprocess.run')
def test_check_docker_installed_failure(mock_run):
    """Test checking Docker installation failure."""
    from praisonai_deploy.docker import check_docker_installed
    
    mock_run.side_effect = FileNotFoundError()
    
    result = check_docker_installed()
    assert result is False

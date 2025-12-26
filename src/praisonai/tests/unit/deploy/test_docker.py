"""
Unit tests for Docker deploy functionality.
"""
from unittest.mock import Mock, patch
import tempfile
import os


def test_generate_dockerfile_basic():
    """Test generating basic Dockerfile."""
    from praisonai.deploy.docker import generate_dockerfile
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig()
    dockerfile = generate_dockerfile("agents.yaml", config)
    
    assert "FROM python:3.11-slim" in dockerfile
    assert "COPY agents.yaml" in dockerfile
    assert "pip install praisonai" in dockerfile
    assert "EXPOSE 8005" in dockerfile


def test_generate_dockerfile_custom_base():
    """Test generating Dockerfile with custom base image."""
    from praisonai.deploy.docker import generate_dockerfile
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig(base_image="python:3.12-alpine")
    dockerfile = generate_dockerfile("agents.yaml", config)
    
    assert "FROM python:3.12-alpine" in dockerfile


def test_generate_dockerfile_multiple_ports():
    """Test generating Dockerfile with multiple exposed ports."""
    from praisonai.deploy.docker import generate_dockerfile
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig(expose=[8005, 8006, 9090])
    dockerfile = generate_dockerfile("agents.yaml", config)
    
    assert "EXPOSE 8005" in dockerfile
    assert "EXPOSE 8006" in dockerfile
    assert "EXPOSE 9090" in dockerfile


@patch('subprocess.run')
def test_build_docker_image_success(mock_run):
    """Test building Docker image successfully."""
    from praisonai.deploy.docker import build_docker_image
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig(image_name="test-app", tag="v1.0.0")
    mock_run.return_value = Mock(returncode=0)
    
    result = build_docker_image(config, "/tmp/test")
    
    assert result.success is True
    assert "test-app:v1.0.0" in result.message


@patch('subprocess.run')
def test_build_docker_image_failure(mock_run):
    """Test building Docker image failure."""
    from praisonai.deploy.docker import build_docker_image
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig(image_name="test-app")
    mock_run.side_effect = Exception("Build failed")
    
    result = build_docker_image(config, "/tmp/test")
    
    assert result.success is False
    assert result.error is not None


@patch('subprocess.run')
def test_run_docker_container_success(mock_run):
    """Test running Docker container successfully."""
    from praisonai.deploy.docker import run_docker_container
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig(image_name="test-app", tag="latest")
    mock_run.return_value = Mock(returncode=0, stdout="abc123def456")
    
    result = run_docker_container(config)
    
    assert result.success is True
    assert "container_id" in result.metadata


@patch('subprocess.run')
def test_run_docker_container_with_env(mock_run):
    """Test running Docker container with environment variables."""
    from praisonai.deploy.docker import run_docker_container
    from praisonai.deploy.models import DockerConfig
    
    config = DockerConfig(image_name="test-app")
    env_vars = {"MODEL": "gpt-4", "API_KEY": "secret"}
    mock_run.return_value = Mock(returncode=0, stdout="abc123")
    
    result = run_docker_container(config, env_vars=env_vars)
    
    assert result.success is True


@patch('subprocess.run')
def test_push_docker_image_success(mock_run):
    """Test pushing Docker image successfully."""
    from praisonai.deploy.docker import push_docker_image
    from praisonai.deploy.models import DockerConfig
    
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
    from praisonai.deploy.docker import push_docker_image
    from praisonai.deploy.models import DockerConfig
    
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
    from praisonai.deploy.docker import stop_docker_container
    
    mock_run.return_value = Mock(returncode=0)
    
    result = stop_docker_container("abc123")
    assert result is True


@patch('subprocess.run')
def test_check_docker_installed_success(mock_run):
    """Test checking Docker installation successfully."""
    from praisonai.deploy.docker import check_docker_installed
    
    mock_run.return_value = Mock(returncode=0, stdout="Docker version 24.0.0")
    
    result = check_docker_installed()
    assert result is True


@patch('subprocess.run')
def test_check_docker_installed_failure(mock_run):
    """Test checking Docker installation failure."""
    from praisonai.deploy.docker import check_docker_installed
    
    mock_run.side_effect = FileNotFoundError()
    
    result = check_docker_installed()
    assert result is False

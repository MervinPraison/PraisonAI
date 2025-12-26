"""
Unit tests for API server deploy functionality.
"""
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os


@patch('subprocess.Popen')
def test_start_api_server_success(mock_popen):
    """Test starting API server successfully."""
    from praisonai.deploy.api import start_api_server
    from praisonai.deploy.models import APIConfig
    
    config = APIConfig(host="127.0.0.1", port=8005)
    mock_process = Mock()
    mock_process.pid = 12345
    mock_popen.return_value = mock_process
    
    result = start_api_server("agents.yaml", config)
    
    assert result.success is True
    assert result.metadata["pid"] == 12345


@patch('subprocess.Popen')
def test_start_api_server_background(mock_popen):
    """Test starting API server in background mode."""
    from praisonai.deploy.api import start_api_server
    from praisonai.deploy.models import APIConfig
    
    config = APIConfig(host="0.0.0.0", port=8080)
    mock_process = Mock()
    mock_process.pid = 12345
    mock_popen.return_value = mock_process
    
    result = start_api_server("agents.yaml", config, background=True)
    
    assert result.success is True
    assert "background" in result.message.lower() or "started" in result.message.lower()


def test_generate_api_server_code():
    """Test generating API server code."""
    from praisonai.deploy.api import generate_api_server_code
    
    code = generate_api_server_code("agents.yaml")
    
    assert "from flask import Flask" in code or "from fastapi import FastAPI" in code
    assert "agents.yaml" in code


def test_generate_api_server_code_with_auth():
    """Test generating API server code with authentication."""
    from praisonai.deploy.api import generate_api_server_code
    from praisonai.deploy.models import APIConfig
    
    config = APIConfig(auth_enabled=True, auth_token="secret123")
    code = generate_api_server_code("agents.yaml", config)
    
    assert "auth" in code.lower() or "token" in code.lower()


@patch('subprocess.run')
def test_check_api_health_success(mock_run):
    """Test checking API health successfully."""
    from praisonai.deploy.api import check_api_health
    
    mock_run.return_value = Mock(returncode=0, stdout='{"status": "ok"}')
    
    result = check_api_health("http://localhost:8005")
    assert result is True


@patch('subprocess.run')
def test_check_api_health_failure(mock_run):
    """Test checking API health failure."""
    from praisonai.deploy.api import check_api_health
    
    mock_run.side_effect = Exception("Connection refused")
    
    result = check_api_health("http://localhost:8005")
    assert result is False


def test_stop_api_server():
    """Test stopping API server."""
    from praisonai.deploy.api import stop_api_server
    
    with patch('os.kill') as mock_kill:
        result = stop_api_server(12345)
        assert result is True
        mock_kill.assert_called_once()


def test_stop_api_server_not_found():
    """Test stopping API server when PID not found."""
    from praisonai.deploy.api import stop_api_server
    
    with patch('os.kill', side_effect=ProcessLookupError()):
        result = stop_api_server(99999)
        assert result is False

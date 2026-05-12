"""Test for agent server readiness timeout warning functionality."""

import time
import threading
import logging
import pytest
from unittest.mock import patch, MagicMock
from praisonaiagents.agents.agents import _AgentServerRegistry


def test_server_readiness_timeout_emits_warning(caplog):
    """A server that does not start in time must produce a WARNING log entry."""
    registry = _AgentServerRegistry()
    
    # Create a mock FastAPI app that won't signal readiness
    mock_app = MagicMock()
    
    # Register the app but don't set the ready event
    with patch.dict(registry._apps, {8000: mock_app}):
        with patch.dict(registry._ready_events, {8000: threading.Event()}):
            with patch.dict(registry._started, {8000: False}):
                with patch("threading.Thread.start"):  # Prevent real server spawning
                    with caplog.at_level(logging.WARNING):
                        # Use a very short timeout to ensure the test doesn't hang
                        with patch.dict("os.environ", {"PRAISONAI_SERVER_READY_TIMEOUT": "0.1"}):
                            result = registry.start_server_if_needed(8000, host="127.0.0.1")
                    
                    # The method should still return True but log a warning
                    assert result is True
                    assert "8000" in caplog.text
                    assert "did not become ready" in caplog.text.lower()


def test_server_readiness_timeout_configurable_via_env():
    """The timeout should be configurable via PRAISONAI_SERVER_READY_TIMEOUT."""
    registry = _AgentServerRegistry()
    
    # Create a mock FastAPI app
    mock_app = MagicMock()
    
    # Register the app but don't set the ready event
    with patch.dict(registry._apps, {8001: mock_app}):
        with patch.dict(registry._ready_events, {8001: threading.Event()}):
            with patch.dict(registry._started, {8001: False}):
                with patch("threading.Thread.start"):  # Prevent real server spawning
                    # Test with custom timeout
                    with patch.dict("os.environ", {"PRAISONAI_SERVER_READY_TIMEOUT": "0.05"}):
                        start_time = time.time()
                        result = registry.start_server_if_needed(8001, host="127.0.0.1")
                        duration = time.time() - start_time
                    
                    # Should respect the custom timeout and complete quickly
                    assert result is True
                    assert duration < 1.0  # Should be much less than default 5s


def test_server_readiness_success_no_warning(caplog):
    """A server that starts in time should not produce any warning."""
    registry = _AgentServerRegistry()
    
    # Create a mock FastAPI app
    mock_app = MagicMock()
    ready_event = threading.Event()
    
    # Register the app and signal readiness immediately
    with patch.dict(registry._apps, {8002: mock_app}):
        with patch.dict(registry._ready_events, {8002: ready_event}):
            with patch.dict(registry._started, {8002: False}):
                with patch("threading.Thread.start"):  # Prevent real server spawning
                    # Set the event immediately to simulate quick startup
                    ready_event.set()
                    
                    with caplog.at_level(logging.WARNING):
                        result = registry.start_server_if_needed(8002, host="127.0.0.1")
                    
                    # Should succeed without warnings
                    assert result is True
                    assert "did not become ready" not in caplog.text.lower()


def test_default_timeout_value(monkeypatch):
    """Test that the default timeout is 5.0 seconds when env var is not set."""
    registry = _AgentServerRegistry()
    
    # Create a mock FastAPI app
    mock_app = MagicMock()
    ready_event = threading.Event()
    
    # Register the app but don't set the ready event
    with patch.dict(registry._apps, {8003: mock_app}):
        with patch.dict(registry._ready_events, {8003: ready_event}):
            with patch.dict(registry._started, {8003: False}):
                with patch("threading.Thread.start"):  # Prevent real server spawning
                    # Remove only the specific env var so other env vars (PATH etc.) remain intact
                    monkeypatch.delenv("PRAISONAI_SERVER_READY_TIMEOUT", raising=False)
                    with patch("threading.Event.wait") as mock_wait:
                        mock_wait.return_value = False
                        result = registry.start_server_if_needed(8003, host="127.0.0.1")
                    
                    # Should have called wait with default timeout of 5.0
                    mock_wait.assert_called_once_with(timeout=5.0)
                    assert result is True


def test_invalid_timeout_env_var_fallback(caplog):
    """Test that invalid PRAISONAI_SERVER_READY_TIMEOUT falls back to default with warning."""
    registry = _AgentServerRegistry()
    
    # Create a mock FastAPI app
    mock_app = MagicMock()
    ready_event = threading.Event()
    
    # Register the app but don't set the ready event
    with patch.dict(registry._apps, {8004: mock_app}):
        with patch.dict(registry._ready_events, {8004: ready_event}):
            with patch.dict(registry._started, {8004: False}):
                with patch("threading.Thread.start"):  # Prevent real server spawning
                    # Test with invalid timeout value
                    with patch.dict("os.environ", {"PRAISONAI_SERVER_READY_TIMEOUT": "invalid"}):
                        with caplog.at_level(logging.WARNING):
                            with patch("threading.Event.wait") as mock_wait:
                                mock_wait.return_value = False
                                result = registry.start_server_if_needed(8004, host="127.0.0.1")
                    
                    # Should have fallen back to 5.0 and logged warning
                    mock_wait.assert_called_once_with(timeout=5.0)
                    assert result is True
                    assert "Invalid PRAISONAI_SERVER_READY_TIMEOUT" in caplog.text
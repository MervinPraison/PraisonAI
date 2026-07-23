"""Tests for CLI backend debug logging."""

import logging

import pytest
from unittest.mock import AsyncMock, Mock

from praisonaiagents.cli_backend.debug import (
    backend_label,
    cli_backend_debug_enabled,
    log_cli_backend_execution,
)
from praisonaiagents.cli_backend.protocols import CliBackendConfig, CliBackendResult


@pytest.mark.parametrize(
    "env,expected",
    [
        ({}, False),
        ({"PRAISONAI_CLI_BACKEND_DEBUG": "1"}, True),
        ({"PRAISONAI_CLI_BACKEND_DEBUG": "true"}, True),
        ({"LOGLEVEL": "DEBUG"}, True),
        ({"LOGLEVEL": "INFO"}, False),
    ],
)
def test_cli_backend_debug_enabled(monkeypatch, env, expected):
    monkeypatch.delenv("PRAISONAI_CLI_BACKEND_DEBUG", raising=False)
    monkeypatch.delenv("LOGLEVEL", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert cli_backend_debug_enabled() is expected


def test_backend_label_uses_config_command():
    backend = Mock()
    backend.config = CliBackendConfig(command="gemini")
    assert backend_label(backend) == "gemini"


def test_backend_label_falls_back_to_class_name():
    class CustomBackend:
        pass

    assert backend_label(CustomBackend()) == "CustomBackend"


def test_log_cli_backend_execution_when_disabled(caplog):
    caplog.set_level(logging.INFO)
    backend = Mock()
    backend.config = CliBackendConfig(command="gemini")
    result = CliBackendResult(content="ok", metadata={"command": ["gemini", "-p", "hi"]})
    log = logging.getLogger("test.cli_backend_debug")

    log_cli_backend_execution(
        log,
        backend=backend,
        result=result,
        agent_name="assistant",
        session_id="sess-1",
    )

    assert not caplog.records


def test_log_cli_backend_execution_when_enabled(monkeypatch, caplog):
    monkeypatch.setenv("PRAISONAI_CLI_BACKEND_DEBUG", "1")
    caplog.set_level(logging.INFO)
    backend = Mock()
    backend.config = CliBackendConfig(command="gemini")
    result = CliBackendResult(
        content="ok",
        metadata={"command": ["gemini", "--yolo", "-p", "hi"]},
    )
    log = logging.getLogger("test.cli_backend_debug")

    log_cli_backend_execution(
        log,
        backend=backend,
        result=result,
        agent_name="assistant",
        session_id="sess-1",
    )

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "CLI backend delegation" in message
    assert "agent='assistant'" in message
    assert "backend='gemini'" in message
    assert "transport=subprocess" in message
    assert "praisonai_llm_http=false" in message
    assert "gemini" in message

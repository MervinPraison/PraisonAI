"""A transport name must not hide explicit post-dispatch failure signals."""

import ssl

import pytest

from praisonaiagents.llm.error_classifier import is_replay_unsafe
from praisonaiagents.llm.llm import LLM


class ReadTimeout(Exception):
    """Provider-shaped timeout without requiring a transport dependency."""


class ReadTimeoutError(ReadTimeout):
    """Subclass shape used by a second transport's timeout errors."""


@pytest.mark.parametrize("error_type", [Exception, ssl.SSLError])
@pytest.mark.parametrize("message", ["TLS transport: read timeout", "SSL connection reset by peer"])
def test_transport_label_does_not_hide_post_dispatch_signal(error_type, message):
    assert is_replay_unsafe(error_type(message)) is True


@pytest.mark.parametrize("error_type", [Exception, ssl.SSLError])
@pytest.mark.parametrize("side_effecting", [False, True])
def test_failover_gates_transport_read_failure_only_for_tool_turn(error_type, side_effecting):
    decision = LLM(model="fake").resolve_failover_decision(
        error_type("TLS transport: read timeout"),
        {"attempt": 1, "max_retries": 3, "side_effecting": side_effecting},
    )
    assert decision.is_retryable is (not side_effecting)
    assert decision.action == ("surface_error" if side_effecting else "retry")
    if side_effecting:
        assert decision.reason == "provider_outcome_unknown"


def test_explicit_connect_failure_keeps_type_precedence():
    class ConnectTimeout(Exception):
        pass

    assert is_replay_unsafe(ConnectTimeout("TLS connection timed out")) is False
    assert is_replay_unsafe(ssl.SSLError("TLS handshake failure")) is False
    assert is_replay_unsafe(ssl.SSLCertVerificationError("certificate verify failed")) is False


@pytest.mark.parametrize("error_type", [Exception, ssl.SSLError, ConnectionResetError, ReadTimeout, ReadTimeoutError])
@pytest.mark.parametrize(
    "message",
    [
        "TLS handshake failed: connection reset by peer",
        "SSL handshake read timed out",
        "connection reset during TLS handshake",
        "SSL handshake timed out",
    ],
)
def test_handshake_scoped_failure_stays_pre_dispatch(error_type, message):
    assert is_replay_unsafe(error_type(message)) is False
    decision = LLM(model="fake").resolve_failover_decision(
        error_type(message), {"attempt": 1, "max_retries": 3, "side_effecting": True},
    )
    assert decision.action == "retry"


@pytest.mark.parametrize("error_type", [Exception, ssl.SSLError, ConnectionResetError, ReadTimeout, ReadTimeoutError])
@pytest.mark.parametrize("message", [
    "TLS handshake completed; read timeout",
    "connection reset after TLS handshake",
    "handshake succeeded, response ended prematurely",
])
def test_completed_handshake_does_not_hide_response_failure(error_type, message):
    error = error_type(message)
    assert is_replay_unsafe(error) is True
    decision = LLM(model="fake").resolve_failover_decision(
        error, {"attempt": 1, "max_retries": 3, "side_effecting": True},
    )
    assert decision.action == "surface_error"
    assert decision.reason == "provider_outcome_unknown"


@pytest.mark.parametrize("error_type", [ConnectionResetError, ReadTimeout, ReadTimeoutError])
def test_typed_reset_and_timeout_without_handshake_remain_unsafe(error_type):
    assert is_replay_unsafe(error_type("request failed")) is True

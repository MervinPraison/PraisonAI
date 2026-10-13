"""Issue #5802: failed turns carry a typed wire error, not just a bare string."""

import asyncio

from praisonai_bot.gateway.server import _turn_error_payload


class _Resp:
    headers = {"retry-after": "29.5"}


class _RateLimit(Exception):
    status_code = 429
    response = _Resp()


def test_rate_limit_is_retryable_with_retry_after():
    err = _turn_error_payload(_RateLimit("Too many requests"))
    assert err["code"] == "rate_limit"
    assert err["retryable"] is True
    assert err["retry_after_seconds"] == 30
    assert "Too many" not in err["message"]


def test_context_overflow_is_not_retryable():
    err = _turn_error_payload(Exception("maximum context length exceeded"))
    assert err["code"] == "context_overflow"
    assert err["retryable"] is False
    assert err["retry_after_seconds"] is None


def test_core_typed_error_kind_is_preserved():
    from praisonaiagents.errors import PraisonAIError

    err = _turn_error_payload(PraisonAIError("no credit", error_category="billing"))
    assert err == {
        "code": "billing",
        "retryable": False,
        "retry_after_seconds": None,
        "message": "The model provider account is out of credit.",
    }


def test_unknown_error_maps_to_internal_with_safe_message():
    err = _turn_error_payload(RuntimeError("secret sk-abc leaked in traceback"))
    assert err["code"] == "internal"
    assert err["retryable"] is False
    assert "sk-abc" not in err["message"]


def test_timeout_is_transient():
    assert _turn_error_payload(asyncio.TimeoutError())["code"] == "transient"


def test_retry_after_is_not_capped():
    class _LongResp:
        headers = {"retry-after": "3600"}

    class _LongRateLimit(Exception):
        status_code = 429
        response = _LongResp()

    assert _turn_error_payload(_LongRateLimit("slow down"))["retry_after_seconds"] == 3600


def test_terminal_turn_carries_typed_error():
    from praisonai_bot.gateway.server import _TerminalTurn

    err = {"code": "transient", "retryable": True}
    turn = _TerminalTurn("wedged", outcome_status="error", error=err)
    assert turn == "wedged" and turn.outcome_status == "error" and turn.error is err
    assert _TerminalTurn("ok").error is None

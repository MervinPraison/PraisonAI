"""Unit tests for gateway crash/shutdown forensics (Issue #2436).

Covers the pure, core-side helpers: protocol conformance, log formatting,
supervision detection, and the drain-timeout headroom predicate.
"""

import pytest

from praisonaiagents.gateway import (
    ShutdownForensicsProtocol,
    drain_timeout_has_headroom,
    format_forensics_for_log,
    is_supervised,
)


class _DummyForensics:
    def snapshot(self, signal_name=None):
        return {"signal": signal_name, "pid": 1}

    def spawn_diagnostic(self, ctx, log_dir):
        return None


def test_protocol_conformance():
    assert isinstance(_DummyForensics(), ShutdownForensicsProtocol)


def test_format_none_is_unavailable():
    assert format_forensics_for_log(None) == "gateway-forensics: <unavailable>"
    assert format_forensics_for_log("nope") == "gateway-forensics: <unavailable>"


def test_format_empty_dict():
    assert format_forensics_for_log({}) == "gateway-forensics: <empty>"


def test_format_renders_known_keys_in_order():
    ctx = {
        "signal": "SIGTERM",
        "pid": 1234,
        "ppid": 1,
        "supervised": True,
        "loadavg_1m": 0.5,
        "traced": False,
        "maxrss_kb": 99000,
    }
    line = format_forensics_for_log(ctx)
    assert line.startswith("gateway-forensics: ")
    assert "signal=SIGTERM" in line
    assert "pid=1234" in line
    assert "supervised=yes" in line
    assert "traced=no" in line
    assert "loadavg_1m=0.50" in line
    # order: signal before pid before supervised
    assert line.index("signal=") < line.index("pid=") < line.index("supervised=")


def test_format_omits_none_values_and_unknown_keys():
    ctx = {"signal": None, "pid": 7, "extra": "ignored"}
    line = format_forensics_for_log(ctx)
    assert "signal" not in line
    assert "extra" not in line
    assert "pid=7" in line


def test_is_supervised_ppid_one():
    assert is_supervised(1, None) is True


def test_is_supervised_invocation_id():
    assert is_supervised(4321, "abc123") is True


def test_not_supervised():
    assert is_supervised(4321, None) is False
    assert is_supervised(4321, "") is False
    assert is_supervised(None, None) is False


def test_headroom_drain_disabled_is_true():
    assert drain_timeout_has_headroom(5, 0) is True
    assert drain_timeout_has_headroom(5, None) is True


def test_headroom_unknown_stop_timeout_is_true():
    assert drain_timeout_has_headroom(None, 30) is True


def test_headroom_sufficient():
    assert drain_timeout_has_headroom(70, 30, headroom_s=30) is True
    assert drain_timeout_has_headroom(60, 30, headroom_s=30) is True


def test_headroom_insufficient():
    assert drain_timeout_has_headroom(40, 30, headroom_s=30) is False
    assert drain_timeout_has_headroom(10, 30) is False


def test_headroom_non_numeric_is_fail_open():
    assert drain_timeout_has_headroom("x", 30) is True
    assert drain_timeout_has_headroom(40, "y") is True


def test_snapshot_never_raises_and_is_serialisable():
    pytest.importorskip("praisonai.gateway.forensics", reason="wrapper not installed")
    from praisonai.gateway.forensics import ShutdownForensics

    ctx = ShutdownForensics(log_dir=None).snapshot(signal_name="SIGTERM")
    assert ctx["signal"] == "SIGTERM"
    assert isinstance(ctx.get("pid"), int)
    import json

    json.dumps(ctx)

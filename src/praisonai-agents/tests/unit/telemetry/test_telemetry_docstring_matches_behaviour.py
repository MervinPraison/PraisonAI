"""G-28: the telemetry module docstring must describe what the code does.

It said telemetry was opt-out; the code is opt-in (off unless enabled), and
the opt-out variables win over the opt-in one.
"""

import os
import subprocess
import sys

import pytest

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_VARS = ("PRAISONAI_TELEMETRY_ENABLED", "PRAISONAI_PERFORMANCE_ENABLED", "DO_NOT_TRACK",
         "PRAISONAI_TELEMETRY_DISABLED", "PRAISONAI_DISABLE_TELEMETRY", "PRAISONAI_PERFORMANCE_DISABLED")


def test_docstring_says_off_by_default():
    from praisonaiagents.telemetry import telemetry
    doc = telemetry.__doc__
    assert "opt-out via environment" not in doc
    assert "off by default" in doc and "PRAISONAI_TELEMETRY_ENABLED" in doc and "DO_NOT_TRACK" in doc


@pytest.mark.parametrize("env,disabled", [
    ({}, True),
    ({"PRAISONAI_TELEMETRY_ENABLED": "true"}, False),
    ({"PRAISONAI_TELEMETRY_ENABLED": "true", "DO_NOT_TRACK": "1"}, True),
])
def test_documented_switches(tmp_path, env, disabled):
    clean = {k: v for k, v in os.environ.items() if k not in _VARS}
    proc = subprocess.run(
        [sys.executable, "-c", "from praisonaiagents.telemetry import telemetry as t; print(t._is_monitoring_disabled())"],
        capture_output=True, text=True, cwd=str(tmp_path), timeout=60,
        env={**clean, **env, "PYTHONPATH": PKG_ROOT})
    assert proc.returncode == 0, proc.stderr[-1000:]
    assert proc.stdout.strip().splitlines()[-1] == str(disabled)

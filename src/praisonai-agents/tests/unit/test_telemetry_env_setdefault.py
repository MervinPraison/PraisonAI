"""T-07: the SDK turns third-party telemetry off by default, but never
overwrites a value the host process set on purpose.

Importing ``praisonaiagents.llm`` or ``praisonaiagents.memory`` set
``LITELLM_TELEMETRY=False`` and building a ``Knowledge`` set
``ANONYMIZED_TELEMETRY=False``, replacing whatever the host had chosen for
every library in the process.
"""
import os
import subprocess
import sys

import pytest

PROBES = {
    "llm": ("LITELLM_TELEMETRY", "import praisonaiagents.llm"),
    "memory": ("LITELLM_TELEMETRY", "import praisonaiagents.memory.memory"),
    "knowledge": ("ANONYMIZED_TELEMETRY",
                  "from praisonaiagents.knowledge.knowledge import Knowledge; Knowledge()"),
}


def _value_after(code, key, preset):
    env = {k: v for k, v in os.environ.items() if k not in ("LITELLM_TELEMETRY", "ANONYMIZED_TELEMETRY")}
    if preset is not None:
        env[key] = preset
    out = subprocess.run(
        [sys.executable, "-c", f"{code}\nimport os; print(repr(os.environ.get({key!r})))"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("probe", sorted(PROBES))
def test_host_value_is_kept(probe):
    key, code = PROBES[probe]
    assert _value_after(code, key, "True") == "'True'"


@pytest.mark.parametrize("probe", sorted(PROBES))
def test_default_is_still_off(probe):
    key, code = PROBES[probe]
    assert _value_after(code, key, None) == "'False'"

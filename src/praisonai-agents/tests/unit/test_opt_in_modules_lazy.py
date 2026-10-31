"""Regression guard (#6167): opt-in modules must not load on ``import Agent``."""

import subprocess
import sys

_SCRIPT = r"""
import sys
from praisonaiagents import Agent  # noqa: F401
import praisonaiagents.session as session

lazy = (
    "praisonaiagents.agent.server_registry",
    "praisonaiagents.goal.judge",
    "praisonaiagents.session.encrypted_store",
)
loaded = [m for m in lazy if m in sys.modules]
assert not loaded, f"eagerly imported: {loaded}"

# Public encryption exports still resolve lazily.
from praisonaiagents.session import (  # noqa: E402
    EncryptedSessionStore, SessionEncryptionError, generate_session_key,
)
assert "praisonaiagents.session.encrypted_store" in sys.modules
assert session.EncryptedSessionStore is EncryptedSessionStore
assert callable(generate_session_key) and issubclass(SessionEncryptionError, Exception)
"""


def test_opt_in_modules_not_loaded_on_agent_import():
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr

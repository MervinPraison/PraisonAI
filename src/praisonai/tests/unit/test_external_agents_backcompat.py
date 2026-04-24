"""Backward-compatibility tests for the legacy ``--external-agent`` flag.

These tests guard against regressions introduced by the Phase 1b CLI Backend
Protocol work (PRs #1521 / #1531). They mix direct-import tests for the
integration classes and subprocess tests for argparse surface.
"""

import os
import subprocess
import sys


REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)


def _build_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONPATH"] = os.pathsep.join([
        os.path.join(REPO_ROOT, "src", "praisonai-agents"),
        os.path.join(REPO_ROOT, "src", "praisonai"),
        env.get("PYTHONPATH", ""),
    ])
    return env


def _run_cli(*args, timeout=30):
    return subprocess.run(
        [sys.executable, "-m", "praisonai.cli.main", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=REPO_ROOT,
        env=_build_env(),
    )


# ---- Direct-import back-compat ---------------------------------------------


def test_external_agents_handler_still_importable():
    """``ExternalAgentsHandler`` must remain importable at its original path."""
    from praisonai.cli.features.external_agents import ExternalAgentsHandler
    handler = ExternalAgentsHandler(verbose=False)
    assert handler.list_integrations() == ['claude', 'gemini', 'codex', 'cursor']


def test_claude_code_integration_still_importable():
    """Legacy ``ClaudeCodeIntegration`` class must remain importable."""
    from praisonai.integrations.claude_code import ClaudeCodeIntegration
    integration = ClaudeCodeIntegration()
    assert integration.cli_command == 'claude'


# ---- argparse-surface back-compat ------------------------------------------


def test_external_agent_flag_present_in_help():
    """``--external-agent`` must still be listed in ``--help``."""
    r = _run_cli("--help")
    assert r.returncode == 0
    assert "--external-agent" in r.stdout


def test_external_agent_flag_choices_preserved():
    """Help text must still include all four legacy choices."""
    r = _run_cli("--help")
    assert r.returncode == 0
    for choice in ("claude", "gemini", "codex", "cursor"):
        assert choice in r.stdout, (
            f"legacy --external-agent choice '{choice}' missing from --help"
        )


def test_external_agent_direct_flag_present_in_help():
    """``--external-agent-direct`` must still be listed in ``--help``."""
    r = _run_cli("--help")
    assert r.returncode == 0
    assert "--external-agent-direct" in r.stdout


def test_external_agent_rejects_unknown_value():
    """``--external-agent notreal`` must still be rejected by argparse."""
    r = _run_cli("--external-agent", "notreal", "hi", timeout=15)
    assert r.returncode != 0
    assert "invalid choice" in r.stderr or "notreal" in r.stderr

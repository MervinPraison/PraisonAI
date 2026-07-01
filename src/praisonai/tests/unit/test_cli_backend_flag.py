"""Unit tests for the ``--cli-backend`` CLI flag and ``backends`` subcommand.

These tests drive the real CLI via subprocess so they exercise the complete
argparse configuration (including the ``PYTEST_CURRENT_TEST`` short-circuit
in ``PraisonAI.parse_args``) rather than internal helpers. Each subprocess
runs with an explicit timeout so a hung process cannot stall the suite.
"""

import os
import subprocess
import sys

import pytest


REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)


def _build_env():
    """Return a child env with PYTEST_* vars stripped so the CLI doesn't
    short-circuit argparse (see ``PraisonAI.parse_args`` in-test-env check).
    """
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("PYTEST_")
    }
    # Build PYTHONPATH without trailing separator
    pythonpath_parts = [
        os.path.join(REPO_ROOT, "src", "praisonai-agents"),
        os.path.join(REPO_ROOT, "src", "praisonai"),
    ]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def _run_cli(*args, timeout=30):
    """Invoke the praisonai CLI with the given argv and return CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "praisonai.cli.main", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=REPO_ROOT,
        env=_build_env(),
    )


def test_cli_backend_flag_in_help():
    """``--cli-backend`` must appear in ``--help`` with registered backend choices."""
    r = _run_cli("--help")
    assert r.returncode == 0
    assert "--cli-backend" in r.stdout
    # ``claude-code`` is a registered backend and must appear as a valid choice
    assert "claude-code" in r.stdout


def test_cli_backend_flag_accepts_registered_backend():
    """``--cli-backend claude-code --help`` must parse without argparse error."""
    # Use --help to short-circuit argparse; we only want to prove the flag+value
    # is accepted (no "invalid choice" / "unrecognized" in stderr).
    r = _run_cli("--cli-backend", "claude-code", "--help", timeout=15)
    assert r.returncode == 0
    assert "invalid choice" not in r.stderr
    assert "unrecognized arguments" not in r.stderr


def test_cli_backend_flag_rejects_unknown_backend():
    """Unknown backend id must be rejected by argparse with non-zero exit."""
    r = _run_cli("--cli-backend", "does-not-exist", "hi", timeout=15)
    assert r.returncode != 0
    assert "invalid choice" in r.stderr or "does-not-exist" in r.stderr


def test_mutual_exclusion_cli_backend_external_agent():
    """``--cli-backend`` and ``--external-agent`` must be mutually exclusive."""
    r = _run_cli(
        "--cli-backend", "claude-code",
        "--external-agent", "claude",
        "hi",
        timeout=15,
    )
    assert r.returncode != 0
    assert "not allowed with" in r.stderr or "mutually exclusive" in r.stderr


def test_backends_list_subcommand():
    """``praisonai backends list`` prints the registered backend ids."""
    r = _run_cli("backends", "list", timeout=15)
    assert r.returncode == 0
    assert "claude-code" in r.stdout


def test_backends_bare_subcommand_lists():
    """``praisonai backends`` (no sub-sub-arg) defaults to listing.

    NOTE: this assertion is coupled to the ``backends`` handler in
    ``praisonai.cli.main`` which treats a missing/None subcommand as ``list``.
    If that default ever changes, this test must be updated in lockstep.
    """
    r = _run_cli("backends", timeout=15)
    assert r.returncode == 0
    assert "claude-code" in r.stdout


def test_backends_unknown_subcommand_reports_error():
    """``praisonai backends bogus`` prints an error message.

    NOTE: the error string comes from the ``backends`` handler in
    ``praisonai.cli.main`` (``[red]Unknown backends subcommand: ...[/red]``),
    so this test is coupled to that handler and will need updating if the
    wording changes.
    """
    r = _run_cli("backends", "bogus", timeout=15)
    # Must not crash, must surface the unknown subcommand in stdout or stderr
    combined = (r.stdout + r.stderr).lower()
    assert "unknown" in combined or "bogus" in combined

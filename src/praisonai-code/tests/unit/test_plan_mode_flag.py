"""Tests for the discoverable ``--plan`` read-only mode flag (issue #3684).

``--plan`` is a first-class surface for the pre-existing read-only planning
permission mode (``PermissionMode.PLAN``). It maps onto the same approval
plumbing as ``--approval plan`` rather than a bespoke deny-set, so the agent may
explore/read but every mutating tool is denied. These tests assert:

* the flag exists on both ``run`` and ``code``;
* it resolves to a backend carrying ``PermissionMode.PLAN``;
* the ``run`` conflict guard fails closed on contradictory permission flags.
"""

import pytest


def _param_names(app):
    """Collect the declared CLI option strings for a Typer callback app."""
    import inspect

    callback = app.registered_callback.callback
    names = set()
    for param in inspect.signature(callback).parameters.values():
        names.update(getattr(param.default, "param_decls", None) or [])
    return names


def test_run_exposes_plan_flag():
    from praisonai_code.cli.commands.run import app

    assert "--plan" in _param_names(app)


def test_code_exposes_plan_flag():
    from praisonai_code.cli.commands.code import app

    assert "--plan" in _param_names(app)


def test_plan_maps_to_permission_mode_plan():
    """`plan` resolves to a backend carrying the read-only PermissionMode."""
    from praisonaiagents.permissions import PermissionMode
    from praisonai_code.cli.features._approval_bridge import (
        resolve_approval_backend,
    )

    backend = resolve_approval_backend("plan", non_interactive=True)
    assert backend is not None
    assert getattr(backend, "permission_mode", None) == PermissionMode.PLAN


def test_plan_conflicts_flags_contradictory_permissions():
    """`--plan` is self-contained; explicit permission flags contradict it."""
    from praisonai_code.cli.commands.run import _plan_permission_conflicts

    assert _plan_permission_conflicts("bypass", None, None, None) == ["--approval"]
    assert _plan_permission_conflicts(None, ["read:*"], None, None) == ["--allow"]
    assert _plan_permission_conflicts(None, None, ["bash:*"], None) == ["--deny"]
    assert _plan_permission_conflicts(None, None, None, "deny") == [
        "--permission-default"
    ]


def test_plan_alone_has_no_conflicts():
    """`--plan` with no other permission flags is allowed to proceed."""
    from praisonai_code.cli.commands.run import _plan_permission_conflicts

    assert _plan_permission_conflicts(None, None, None, None) == []


def test_profiled_prompt_threads_plan_backend(monkeypatch):
    """`run --plan --profile` must NOT drop the PLAN deny policy.

    Regression for the profiled-run gap: the profiling branch previously built
    the Agent without the resolved approval backend, so a run advertised as
    read-only silently permitted mutations. Assert the profiled runner now
    forwards a PermissionMode.PLAN backend into ``Agent(approval=...)``.
    """
    import praisonaiagents
    from praisonaiagents.permissions import PermissionMode
    from praisonai_code.cli.commands import run as run_module

    captured = {}

    class _FakeAgent:
        def __init__(self, *args, **kwargs):
            captured["approval"] = kwargs.get("approval")

        def start(self, *_args, **_kwargs):
            return "ok"

    monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent, raising=False)

    run_module._run_prompt_profiled(
        "read the repo",
        no_save=True,
        approval="plan",
    )

    backend = captured.get("approval")
    assert backend is not None
    assert getattr(backend, "permission_mode", None) == PermissionMode.PLAN


def test_repl_worker_threads_agent_approval():
    """The interactive REPL worker must consume ``args.agent_approval``.

    Regression for the REPL gap: ``code --plan`` sets ``args.agent_approval`` to
    a PLAN backend, but the background worker constructed its Agent without it,
    silently downgrading a read-only session to the legacy approval prompt. The
    worker now threads the resolved backend into ``Agent(**agent_extra_kwargs)``.

    The wrapper module pulls heavy optional deps, so assert against the source
    on disk rather than importing it — this keeps the guard lightweight and
    env-independent while still failing if the wiring is removed.
    """
    from pathlib import Path

    legacy = (
        Path(__file__).resolve().parents[3]
        / "praisonai"
        / "praisonai"
        / "cli"
        / "legacy"
        / "interactive_legacy.py"
    )
    assert legacy.exists(), f"interactive_legacy.py not found at {legacy}"
    src = legacy.read_text(encoding="utf-8")

    # The worker resolves the approval off self.args and unpacks it into Agent().
    assert "agent_extra_kwargs" in src
    assert "**agent_extra_kwargs" in src
    assert "agent_approval" in src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

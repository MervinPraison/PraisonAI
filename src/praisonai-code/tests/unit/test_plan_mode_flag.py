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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

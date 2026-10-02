"""Regression test for issue #4374: ``run <file>.yaml`` must reach the agent
runner, not the async-jobs argparse parser.

The legacy dispatcher routed every ``args.command == 'run'`` to the async-jobs
API (``handle_run_command``), whose argparse only accepts
``{submit,status,result,cancel,list,stream}``. So the documented example
``praisonai run agents.yaml`` (and the unified dispatcher's rewrite of
``praisonai agents.yaml`` -> ``run agents.yaml``) hit the jobs parser and
failed with ``invalid choice`` (exit 2) instead of running the team.

This drives the real router and asserts a YAML file first token is handed to
the modern Typer agent runner while genuine job verbs still reach jobs.
"""

import pytest


def _load_module():
    try:
        import praisonai_code.cli.legacy.praison_ai as pa
    except ImportError as exc:  # pragma: no cover - depends on optional wrapper
        pytest.skip(f"legacy dispatcher unavailable: {exc}")
    return pa


def _require_wrapper_argparse():
    try:
        from praisonai_code._wrapper_bridge import import_wrapper_module
        import_wrapper_module("praisonai.cli.legacy.dispatch.argparse_builder")
    except ImportError as exc:  # pragma: no cover - depends on optional wrapper
        pytest.skip(f"wrapper argparse builder unavailable: {exc}")


def _run_with_argv(monkeypatch, pa, argv):
    """Run the real router with ``argv`` capturing run-vs-jobs dispatch."""
    calls = {"run_app": None, "jobs": None}

    import praisonai_code.cli.commands.run as run_mod
    import praisonai_code.cli.features.jobs as jobs_mod

    def fake_run_app(args=None, *a, **k):
        calls["run_app"] = list(args) if args is not None else []

    def fake_handle_run_command(unknown_args, *a, **k):
        calls["jobs"] = list(unknown_args)

    monkeypatch.setattr(run_mod, "app", fake_run_app)
    monkeypatch.setattr(jobs_mod, "handle_run_command", fake_handle_run_command)

    import sys as _sys
    monkeypatch.setattr(_sys, "argv", argv)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        pa.PraisonAI().main()
    return calls, exc_info.value.code


def test_run_yaml_file_reaches_agent_runner_not_jobs(monkeypatch, tmp_path):
    pa = _load_module()
    _require_wrapper_argparse()

    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text("framework: praisonai\nroles: {}\n")
    monkeypatch.chdir(tmp_path)

    calls, code = _run_with_argv(
        monkeypatch, pa, ["praisonai", "run", str(yaml_path)]
    )

    # The YAML path went to the modern agent runner, not the jobs parser.
    assert calls["jobs"] is None
    assert calls["run_app"] == [str(yaml_path)]
    assert code == 0


def test_run_missing_yaml_reaches_agent_runner_not_jobs(monkeypatch, tmp_path):
    """Issue #5095: ``run <file>.yaml`` must reach the agent runner even when
    the file does not exist (typo/wrong dir), so it is the runner — not the
    async-jobs ``invalid choice`` / missing-``job_id`` parser — that ultimately
    handles the path and can report a clear error, instead of the confusing
    jobs failure that made the documented onboarding path look broken.

    This asserts dispatch only: the runner ``app`` is stubbed by the recorder,
    so the target is not read here. The point is that a YAML-suffixed target is
    routed to the agent runner regardless of whether the file exists on disk."""
    pa = _load_module()
    _require_wrapper_argparse()
    monkeypatch.chdir(tmp_path)

    missing = str(tmp_path / "agents.yaml")  # never created on disk
    calls, code = _run_with_argv(
        monkeypatch, pa, ["praisonai", "run", missing]
    )

    # A YAML-suffixed target routes to the agent runner, not the jobs argparse
    # parser, even when the file is absent.
    assert calls["jobs"] is None
    assert calls["run_app"] == [missing]
    assert code == 0


def test_run_submit_still_reaches_jobs(monkeypatch, tmp_path):
    pa = _load_module()
    _require_wrapper_argparse()
    monkeypatch.chdir(tmp_path)

    calls, code = _run_with_argv(
        monkeypatch, pa, ["praisonai", "run", "submit", "do a thing"]
    )

    # A genuine job verb still reaches the jobs API unchanged.
    assert calls["run_app"] is None
    assert calls["jobs"] == ["submit", "do a thing"]
    assert code == 0


def test_run_submit_wins_over_same_named_path(monkeypatch, tmp_path):
    pa = _load_module()
    _require_wrapper_argparse()

    # A stray file named after a job verb must NOT steal the jobs invocation.
    (tmp_path / "submit").write_text("not yaml")
    monkeypatch.chdir(tmp_path)

    calls, code = _run_with_argv(
        monkeypatch, pa, ["praisonai", "run", "submit", "do a thing"]
    )

    assert calls["run_app"] is None
    assert calls["jobs"] == ["submit", "do a thing"]
    assert code == 0


def test_modern_run_delegation_does_not_reenter_run_app(monkeypatch, tmp_path):
    """Issue #5597: ``python -m praisonai <file>.yaml`` must not recurse.

    The modern Typer ``run`` command delegates YAML execution to the legacy
    ``PraisonAI`` class. That class re-parses ``sys.argv`` (``run <file>.yaml``)
    and, before this fix, dispatched the ``run`` command straight back into the
    modern ``run_app`` — which calls the legacy executor again, looping forever
    until ``maximum recursion depth exceeded``.

    With the ``PRAISONAI_IN_MODERN_RUN`` re-entrancy sentinel set (as the modern
    runner does while delegating), the legacy ``run`` branch must execute the
    YAML directly instead of bouncing back to ``run_app``.
    """
    pa = _load_module()
    _require_wrapper_argparse()

    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text("framework: praisonai\nroles: {}\n")
    monkeypatch.chdir(tmp_path)

    calls = {"run_app": None, "jobs": None}
    ran = {"direct": False}

    import praisonai_code.cli.commands.run as run_mod
    import praisonai_code.cli.features.jobs as jobs_mod

    def fake_run_app(args=None, *a, **k):
        calls["run_app"] = list(args) if args is not None else []

    def fake_handle_run_command(unknown_args, *a, **k):
        calls["jobs"] = list(unknown_args)

    # Stub the agents generator so the direct YAML execution path is observed
    # without spinning up a real team / LLM call.
    class _FakeGenerator:
        def __init__(self, *a, **k):
            ran["direct"] = True

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def generate_crew_and_kickoff(self):
            return "READY"

    monkeypatch.setattr(run_mod, "app", fake_run_app)
    monkeypatch.setattr(jobs_mod, "handle_run_command", fake_handle_run_command)
    monkeypatch.setattr(pa, "_get_agents_generator", lambda: _FakeGenerator)
    monkeypatch.setenv("PRAISONAI_IN_MODERN_RUN", "1")

    import sys as _sys
    monkeypatch.setattr(_sys, "argv", ["praisonai", "run", str(yaml_path)])
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    result = pa.PraisonAI(agent_file=str(yaml_path)).main()

    # No re-entry into the modern runner (which caused the infinite recursion),
    # no mis-routing to jobs, and the YAML was executed directly instead.
    assert calls["run_app"] is None
    assert calls["jobs"] is None
    assert ran["direct"] is True
    assert result == "READY"


def test_modern_run_delegation_preserves_resolved_agent_file(monkeypatch, tmp_path):
    """Greptile #5606: the delegated legacy ``run`` branch must keep the
    constructor-provided (resolved, possibly absolute) ``agent_file`` instead of
    overwriting it with the relative ``sys.argv`` token.

    For ``run <file>.yaml --worktree`` the modern runner resolves the target to
    an absolute path *before* chdir'ing into the isolated worktree, then passes
    that path to ``PraisonAI(agent_file=...)``. If the legacy branch replaced it
    with the relative CLI arg, an untracked/ignored YAML (absent from the fresh
    worktree) would fail to load. This asserts the resolved path survives.
    """
    pa = _load_module()
    _require_wrapper_argparse()

    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text("framework: praisonai\nroles: {}\n")
    resolved = str(yaml_path)  # absolute path, as the worktree runner passes

    seen = {"agent_file": None}

    class _FakeGenerator:
        def __init__(self, agent_file, *a, **k):
            seen["agent_file"] = agent_file

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def generate_crew_and_kickoff(self):
            return "READY"

    monkeypatch.setattr(pa, "_get_agents_generator", lambda: _FakeGenerator)
    monkeypatch.setenv("PRAISONAI_IN_MODERN_RUN", "1")

    import sys as _sys

    # sys.argv carries the *relative* CLI token; a bare "agents.yaml" that is not
    # present in the (simulated) new cwd. The resolved absolute path handed to the
    # constructor must win.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_sys, "argv", ["praisonai", "run", "agents.yaml"])
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    result = pa.PraisonAI(agent_file=resolved).main()

    assert seen["agent_file"] == resolved
    assert result == "READY"


def test_profiled_yaml_run_sets_and_restores_modern_run_sentinel(monkeypatch, tmp_path):
    """The profiled YAML path must guard against legacy re-dispatch recursion.

    ``_run_from_file_profiled`` delegates to the legacy ``PraisonAI.run()`` just
    like the non-profiled ``_run_from_file`` does. Without the
    ``PRAISONAI_IN_MODERN_RUN`` sentinel the legacy dispatcher would re-enter the
    modern Typer ``run`` app and recurse. This asserts the sentinel is set while
    the legacy ``run()`` executes and the prior value is restored afterwards so
    the suppression never leaks into a later in-process invocation.
    """
    import os

    import praisonai_code.cli.commands.run as run_mod

    observed = {"in_run": None}

    class _FakePraisonAI:
        config_list = [{"model": None}]

        def __init__(self, *a, **k):
            pass

        def run(self):
            observed["in_run"] = os.environ.get("PRAISONAI_IN_MODERN_RUN")
            return "DONE"

    import praisonai_code.cli.main as main_mod

    monkeypatch.setattr(main_mod, "PraisonAI", _FakePraisonAI)
    # Ensure a clean baseline so restoration is observable.
    monkeypatch.delenv("PRAISONAI_IN_MODERN_RUN", raising=False)

    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text("framework: praisonai\nroles: {}\n")

    run_mod._run_from_file_profiled(str(yaml_path), no_save=True)

    # The sentinel was active for the duration of the legacy run...
    assert observed["in_run"] == "1"
    # ...and restored (removed) afterwards so it does not leak.
    assert "PRAISONAI_IN_MODERN_RUN" not in os.environ


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

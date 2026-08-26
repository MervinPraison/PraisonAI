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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

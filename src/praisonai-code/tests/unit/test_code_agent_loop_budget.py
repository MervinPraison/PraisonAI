"""Regression tests for the four linked defects that stopped `praisonai code`
completing a coding task, and that stopped anyone noticing (#3932).

(a) The coding agent inherited the *general-purpose* Agent budget
    (``ExecutionConfig.max_iter=20`` / ``max_tool_calls_per_turn=10``). Ten tool
    calls is "list files, read two files, one grep" — it cannot reach a test
    run, and `praisonai code` offered no flag, config key or env var to raise
    it.

(b) A budget-truncated run still returns a non-empty wrap-up summary, and
    ``code -p`` classified any non-empty string as success: ``status: "ok"``,
    exit 0. A truncated run was indistinguishable from a completed one to a
    human or a CI adapter. These tests assert the **exit code**, not the message
    text.

(c) ``--dangerously-skip-approval`` set two env vars that the gate which
    actually prompts (the core ``@require_approval`` decorator, which resolves
    through the approval *registry* backend) never reads. With stdin at
    /dev/null every prompt was auto-denied, so the agent could not run a single
    shell command — while still exiting 0.

(d) The Terminal-Bench smoke gate that would have caught all of this pinned
    Python 3.11; ``harbor`` requires >=3.12, so every scheduled run died in
    ~15s at ``pip install harbor`` and no score was ever produced.
"""

import json
import os
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from praisonai_code.cli.commands import code as code_module
from praisonai_code.cli.commands.code import (
    DEFAULT_CODE_MAX_STEPS,
    app,
    build_code_execution_config,
    resolve_code_max_steps,
)


@pytest.fixture(autouse=True)
def _satisfy_credential_gate(monkeypatch):
    """Seed a credential so the first-run onboarding gate lets the run reach the
    Agent path under test (mirrors ``test_code_print_json.py``)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")


@pytest.fixture(autouse=True)
def _isolate_approval_registry():
    """Restore the process-global approval backend around every test.

    The registry is a singleton; a test that installs a bypass backend must not
    leak it into another test (that leak is precisely the hazard (c)'s cleanup
    branch guards against).
    """
    from praisonaiagents.approval import get_approval_registry

    registry = get_approval_registry()
    saved = registry._global_backend
    try:
        yield registry
    finally:
        registry._global_backend = saved


class _StubAgent:
    """Minimal Agent stand-in that records its construction kwargs.

    ``stop_reason`` drives the truncation contract: the core records
    ``last_stop_reason == "max_steps"`` on the agent when either tool loop runs
    out of budget.
    """

    last_kwargs: dict = {}
    answer = "Here is the finished patch."
    stop_reason = "completed"

    def __init__(self, *_args, **kwargs):
        type(self).last_kwargs = kwargs
        self.last_stop_reason = type(self).stop_reason

    def start(self, *_args, **_kwargs):
        return type(self).answer


def _install_stub_agent(monkeypatch, *, answer=None, stop_reason="completed"):
    import praisonaiagents

    class _Agent(_StubAgent):
        pass

    _Agent.answer = answer if answer is not None else _StubAgent.answer
    _Agent.stop_reason = stop_reason
    monkeypatch.setattr(praisonaiagents, "Agent", _Agent, raising=False)
    return _Agent


# ---------------------------------------------------------------------------
# (b) a truncated run must not report success
# ---------------------------------------------------------------------------

# The real wrap-up text a budget-exhausted LiteLLM turn returns. It is a
# perfectly non-empty string, which is exactly why emptiness alone could not
# tell truncation from completion.
TRUNCATION_SUMMARY = (
    "Tool call limit reached (10 calls). Task may be too complex or there "
    "may be a broken tool causing repeated calls."
)


def test_truncated_headless_run_exits_non_zero(monkeypatch):
    """A budget-truncated `code -p` run must NOT exit 0.

    Asserts the exit code, not the message: a CI adapter branches on the status
    code, and before the fix this run was exit 0 / ``status: "ok"``.
    """
    _install_stub_agent(
        monkeypatch, answer=TRUNCATION_SUMMARY, stop_reason="max_steps"
    )

    runner = CliRunner()
    result = runner.invoke(
        app, ["-p", "--output", "json", "Build the project and make the tests pass"]
    )

    assert result.exit_code != 0, result.output
    # Exit 2 = incomplete run, distinct from a hard failure (1) and success (0),
    # matching `praisonai run`'s existing truncation contract.
    assert result.exit_code == 2, result.output


def test_truncated_headless_run_reports_a_distinguishable_status(monkeypatch):
    """The JSON envelope must let a consumer tell truncation from completion."""
    _install_stub_agent(
        monkeypatch, answer=TRUNCATION_SUMMARY, stop_reason="max_steps"
    )

    runner = CliRunner()
    result = runner.invoke(
        app, ["-p", "--output", "json", "Build the project and make the tests pass"]
    )

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "truncated"
    # The partial wrap-up is still preserved for the caller.
    assert payload["result"] == TRUNCATION_SUMMARY


def test_truncated_text_mode_warns_on_stderr_and_exits_non_zero(monkeypatch):
    _install_stub_agent(
        monkeypatch, answer=TRUNCATION_SUMMARY, stop_reason="max_steps"
    )

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--output", "text", "Fix the build"])

    assert result.exit_code == 2, result.output
    assert "budget" in result.output.lower()


def test_completed_headless_run_still_exits_zero(monkeypatch):
    """Control: the completed/failed contract is unchanged."""
    _install_stub_agent(monkeypatch, answer="All tests pass.", stop_reason="completed")

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--output", "json", "Fix the build"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "ok"


def test_truncation_check_is_shared_with_run(monkeypatch):
    """`code -p` reuses `run`'s terminal-reason check rather than a second one."""
    from praisonai_code.cli.commands.run import _run_was_truncated

    calls = []

    def _spy(agent):
        calls.append(agent)
        return False

    monkeypatch.setattr(
        "praisonai_code.cli.commands.run._run_was_truncated", _spy, raising=True
    )
    _install_stub_agent(monkeypatch, answer="done", stop_reason="completed")

    runner = CliRunner()
    runner.invoke(app, ["-p", "--output", "json", "Fix the build"])

    assert calls, "code -p did not consult run._run_was_truncated"
    # Sanity-check the shared helper's own contract while we are here.
    assert _run_was_truncated(type("A", (), {"last_stop_reason": "max_steps"})()) is True


def test_run_truncation_hint_does_not_name_a_nonexistent_flag():
    """`run`'s truncation remediation told users to use `--max-iter`, which the
    CLI has never had (0 occurrences as an option; control: `--model` = 56)."""
    source = Path(code_module.__file__).with_name("run.py").read_text(encoding="utf-8")
    assert "--max-iter" not in source


# ---------------------------------------------------------------------------
# (c) --dangerously-skip-approval must actually skip approval
# ---------------------------------------------------------------------------


def _global_backend_is_bypass(registry) -> bool:
    from praisonaiagents.approval.backends import AutoApproveBackend

    return isinstance(registry._global_backend, AutoApproveBackend)


def test_dangerously_skip_approval_installs_a_bypass_backend(
    monkeypatch, _isolate_approval_registry
):
    """The flag must reach the gate that actually prompts.

    ``PRAISON_APPROVAL_MODE``/``PRAISONAI_TOOL_SAFETY`` are read by the CLI's
    own tool wiring; the core ``@require_approval`` decorator resolves through
    the approval registry's backend. Before the fix nothing registered a bypass
    there, so every critical tool still prompted — and was auto-denied in a
    non-TTY run.
    """
    registry = _isolate_approval_registry
    registry._global_backend = None
    _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["-p", "--output", "json", "--dangerously-skip-approval", "Fix the build"],
    )

    assert result.exit_code == 0, result.output
    assert _global_backend_is_bypass(registry), (
        "--dangerously-skip-approval left the approval gate in place; a "
        "non-TTY run auto-denies every prompt"
    )


def test_no_safe_also_installs_a_bypass_backend(monkeypatch, _isolate_approval_registry):
    registry = _isolate_approval_registry
    registry._global_backend = None
    _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    runner.invoke(app, ["-p", "--output", "json", "--no-safe", "Fix the build"])

    assert _global_backend_is_bypass(registry)


def test_safe_by_default_never_installs_a_bypass_backend(
    monkeypatch, _isolate_approval_registry
):
    """Safety guard: absent the opt-in flag, behaviour is unchanged."""
    registry = _isolate_approval_registry
    registry._global_backend = None
    _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    runner.invoke(app, ["-p", "--output", "json", "Fix the build"])

    assert not _global_backend_is_bypass(registry)
    assert registry._global_backend is None


def test_safe_mode_clears_a_bypass_left_by_an_earlier_run(
    monkeypatch, _isolate_approval_registry
):
    """A bypass from an earlier --no-safe call in the same process (REPL/worker)
    must not silently keep a later safe-by-default session unguarded."""
    from praisonaiagents.approval.backends import AutoApproveBackend

    registry = _isolate_approval_registry
    registry._global_backend = AutoApproveBackend()
    _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    runner.invoke(app, ["-p", "--output", "json", "Fix the build"])

    assert not _global_backend_is_bypass(registry)


def test_safe_mode_preserves_a_caller_supplied_backend(
    monkeypatch, _isolate_approval_registry
):
    """Cleanup removes only the bypass this module installs."""

    class _CustomBackend:
        def request_approval_sync(self, request):  # pragma: no cover - not called
            raise AssertionError("not expected")

    registry = _isolate_approval_registry
    custom = _CustomBackend()
    registry._global_backend = custom
    _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    runner.invoke(app, ["-p", "--output", "json", "Fix the build"])

    assert registry._global_backend is custom


# ---------------------------------------------------------------------------
# (a) the coding agent needs a coding-sized, configurable budget
# ---------------------------------------------------------------------------

# The general-purpose Agent defaults the code agent used to inherit.
_CORE_DEFAULT_MAX_STEPS = 20
_CORE_DEFAULT_TOOL_CALLS = 10


def test_headless_code_agent_gets_a_coding_sized_budget(monkeypatch):
    agent_cls = _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--output", "json", "Fix the build"])

    assert result.exit_code == 0, result.output
    execution = agent_cls.last_kwargs.get("execution")
    assert execution is not None, "code -p built the agent with no ExecutionConfig"
    assert execution.max_steps == DEFAULT_CODE_MAX_STEPS
    assert execution.max_tool_calls_per_turn == DEFAULT_CODE_MAX_STEPS
    # Both loops must be raised: the OpenAI-native loop is bounded by max_steps,
    # the LiteLLM loop additionally by max_tool_calls_per_turn.
    assert execution.max_steps > _CORE_DEFAULT_MAX_STEPS
    assert execution.max_tool_calls_per_turn > _CORE_DEFAULT_TOOL_CALLS


def test_max_steps_flag_overrides_the_default(monkeypatch):
    agent_cls = _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    result = runner.invoke(
        app, ["-p", "--output", "json", "--max-steps", "42", "Fix the build"]
    )

    assert result.exit_code == 0, result.output
    execution = agent_cls.last_kwargs["execution"]
    assert execution.max_steps == 42
    assert execution.max_tool_calls_per_turn == 42


def test_max_steps_env_override(monkeypatch):
    monkeypatch.setenv("PRAISONAI_CODE_MAX_STEPS", "77")
    agent_cls = _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    runner.invoke(app, ["-p", "--output", "json", "Fix the build"])

    assert agent_cls.last_kwargs["execution"].max_steps == 77


def test_max_steps_flag_beats_env(monkeypatch):
    monkeypatch.setenv("PRAISONAI_CODE_MAX_STEPS", "77")
    agent_cls = _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    runner.invoke(app, ["-p", "--output", "json", "--max-steps", "5", "Fix the build"])

    assert agent_cls.last_kwargs["execution"].max_steps == 5


def test_max_steps_resolution_rejects_junk(monkeypatch):
    monkeypatch.delenv("PRAISONAI_CODE_MAX_STEPS", raising=False)
    assert resolve_code_max_steps(None) == DEFAULT_CODE_MAX_STEPS
    assert resolve_code_max_steps(0) == DEFAULT_CODE_MAX_STEPS
    assert resolve_code_max_steps(-3) == DEFAULT_CODE_MAX_STEPS
    monkeypatch.setenv("PRAISONAI_CODE_MAX_STEPS", "not-a-number")
    assert resolve_code_max_steps(None) == DEFAULT_CODE_MAX_STEPS


def test_max_steps_flag_is_declared_on_the_cli():
    import inspect

    callback = app.registered_callback.callback
    names = set()
    for param in inspect.signature(callback).parameters.values():
        names.update(getattr(param.default, "param_decls", None) or [])
    assert "--max-steps" in names


def test_build_code_execution_config_raises_both_knobs():
    cfg = build_code_execution_config()
    assert cfg.resolved_max_steps() == DEFAULT_CODE_MAX_STEPS
    assert cfg.resolved_max_tool_calls() == DEFAULT_CODE_MAX_STEPS


def test_profiled_run_gets_the_coding_sized_budget(monkeypatch):
    """A profiled single-prompt run must not silently keep the small core
    defaults: `--profile` built its Agent with no ExecutionConfig, so a real
    coding task would still truncate at 20 steps / 10 tool calls per turn."""
    agent_cls = _install_stub_agent(monkeypatch, answer="done")
    # The profiler prints a report and exits 0; we only need the Agent kwargs.
    monkeypatch.setattr(
        "praisonai_code.cli.features.cli_profiler.CLIProfiler",
        lambda *a, **k: _NullProfiler(),
        raising=True,
    )

    runner = CliRunner()
    result = runner.invoke(
        app, ["--profile", "--max-steps", "55", "Fix the build"]
    )

    assert result.exit_code == 0, result.output
    execution = agent_cls.last_kwargs.get("execution")
    assert execution is not None, "--profile built the agent with no ExecutionConfig"
    assert execution.max_steps == 55
    assert execution.max_tool_calls_per_turn == 55


class _NullProfiler:
    """No-op profiler so the --profile path exercises Agent construction only."""

    def start(self): ...
    def stop(self): ...
    def mark_import_start(self): ...
    def mark_import_end(self): ...
    def mark_init_start(self): ...
    def mark_init_end(self): ...
    def mark_exec_start(self): ...
    def mark_exec_end(self): ...
    def print_report(self): ...


def test_interactive_dispatch_threads_the_budget_onto_args(monkeypatch):
    """The interactive/single-prompt dispatch must carry the coding budget on
    ``args.execution`` so the wrapper-legacy and resident TUI paths both apply
    it — otherwise `--max-steps` is silently dropped for the common
    `pip install praisonai` interactive session."""
    captured = {}

    def _fake_resident(prompt, args, *, plan=False, session_id=None):
        captured["execution"] = getattr(args, "execution", None)

    # Force the resident-TUI branch (wrapper absent) and capture the args.
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available",
        lambda: False,
        raising=True,
    )
    monkeypatch.setattr(code_module, "_run_resident_code", _fake_resident, raising=True)

    runner = CliRunner()
    result = runner.invoke(app, ["--max-steps", "63", "Fix the build"])

    assert result.exit_code == 0, result.output
    execution = captured.get("execution")
    assert execution is not None, "interactive dispatch dropped the execution budget"
    assert execution.max_steps == 63
    assert execution.max_tool_calls_per_turn == 63


# ---------------------------------------------------------------------------
# (d) the smoke gate must be able to install its harness
# ---------------------------------------------------------------------------


def _repo_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / ".github" / "workflows").is_dir():
            return parent
    return None


def test_terminal_bench_smoke_gate_can_install_harbor():
    """`harbor` requires Python >=3.12. Pinned at 3.11 the gate died in ~15s at
    `pip install harbor` on every scheduled run since it was added, so no
    Terminal-Bench score has ever been produced (RESULTS.md: _pending first
    run_)."""
    root = _repo_root()
    if root is None:  # pragma: no cover - installed-package test run
        pytest.skip("repository checkout not available")
    workflow = root / ".github" / "workflows" / "terminal-bench-smoke.yml"
    if not workflow.exists():  # pragma: no cover
        pytest.skip("terminal-bench-smoke workflow not present")

    text = workflow.read_text(encoding="utf-8")
    match = re.search(r'python-version:\s*"?([0-9]+)\.([0-9]+)"?', text)
    assert match, "no python-version pin found in the smoke workflow"
    major, minor = int(match.group(1)), int(match.group(2))
    assert (major, minor) >= (3, 12), (
        f"terminal-bench-smoke pins Python {major}.{minor}; harbor requires "
        ">=3.12, so `pip install harbor` resolves to no candidate and the gate "
        "can never run"
    )


# ---------------------------------------------------------------------------
# (c) safety: the bypass must not weaken any tighter policy
# ---------------------------------------------------------------------------


def test_plan_mode_cannot_be_combined_with_the_bypass_flags(
    monkeypatch, _isolate_approval_registry
):
    """--plan (read-only) and the approval opt-outs stay mutually exclusive, so
    a bypass backend can never be installed for a planning session."""
    registry = _isolate_approval_registry
    registry._global_backend = None
    _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    for flags in (["--plan", "--dangerously-skip-approval"], ["--plan", "--no-safe"]):
        result = runner.invoke(app, ["-p", "--output", "json", *flags, "Explore"])
        assert result.exit_code == 1, result.output
        assert not _global_backend_is_bypass(registry)


def test_plan_mode_still_installs_its_read_only_backend_on_the_agent(monkeypatch):
    """A per-agent backend (--plan / --agent scope) is what the core consults
    first, so the bypass path cannot silently unlock a scoped session."""
    agent_cls = _install_stub_agent(monkeypatch, answer="done")

    runner = CliRunner()
    result = runner.invoke(app, ["-p", "--output", "json", "--plan", "Explore"])

    assert result.exit_code == 0, result.output
    assert agent_cls.last_kwargs.get("approval") is not None

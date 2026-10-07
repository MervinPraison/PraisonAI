"""Regression tests for the standalone `run` wrapper gate (issues #5644/#2839).

Structured output modes (actions/json/stream/stream-json) run in-process via the
Agent path and never need the wrapper. Human-readable text modes
(plain/verbose/silent/default) delegate to the wrapper's `handle_direct_prompt`
**when the wrapper is installed**; on a standalone install (no `praisonai`
wrapper) they render in-process instead (issue #5644), so the blanket install
gate no longer fires for them.

The one wrapper-only feature left on the direct-prompt path is ``--image`` (the
vision handling lives in the wrapper's ``handle_direct_prompt``), so an image
run on a standalone install keeps a targeted gate. The module-level C7 import
gate (no wrapper imports in the hot-path files) is unaffected: the in-process
text render imports ``praisonaiagents`` lazily inside the run, exactly like the
structured modes already do.

`_require_wrapper_for_default_run` therefore only fails for genuinely
wrapper-only features (currently `--image`, which routes through the wrapper's
vision ImageHandler). `_direct_prompt_needs_wrapper` still reports that text
modes use the wrapper *path* (so an installed wrapper keeps delegating to its
richer `handle_direct_prompt`).
"""

import pytest

import typer

from praisonai_code.cli.commands import run as run_cmd


@pytest.fixture
def no_wrapper(monkeypatch):
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )


@pytest.fixture
def with_wrapper(monkeypatch):
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: True
    )


@pytest.mark.parametrize("mode", [None, "silent", "plain", "verbose"])
def test_text_modes_delegate_to_wrapper_when_installed(mode):
    """Text modes route to the wrapper text path when it is installed."""
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", agent=None, command=None, output_mode=mode
        )
        is True
    )


@pytest.mark.parametrize("mode", ["actions", "json", "stream", "stream-json"])
def test_structured_modes_never_need_wrapper(mode):
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", agent=None, command=None, output_mode=mode
        )
        is False
    )


@pytest.mark.parametrize("kwargs", [
    {"agent": "reviewer", "command": None},
    {"agent": None, "command": "deploy"},
])
def test_agent_or_command_never_need_wrapper(kwargs):
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            "hi", output_mode=None, **kwargs
        )
        is False
    )


def test_no_target_does_not_need_wrapper():
    assert (
        run_cmd._direct_prompt_needs_wrapper(
            None, agent=None, command=None, output_mode=None
        )
        is False
    )


# --- standalone text runs render in-process (issue #5644) ------------------


@pytest.mark.parametrize("mode", [None, "silent", "plain", "verbose"])
def test_text_runs_render_in_process_without_wrapper(no_wrapper, mode):
    """On a standalone install, text modes render in-process (no gate)."""
    assert (
        run_cmd._text_run_renders_in_process(mode, image=None)
        is True
    )


@pytest.mark.parametrize("mode", [None, "silent", "plain", "verbose"])
def test_text_runs_delegate_when_wrapper_installed(with_wrapper, mode):
    """With the wrapper installed, behaviour is unchanged (delegation)."""
    assert (
        run_cmd._text_run_renders_in_process(mode, image=None)
        is False
    )


@pytest.mark.parametrize("mode", ["actions", "json", "stream", "stream-json"])
def test_structured_modes_are_not_text_runs(no_wrapper, mode):
    """Structured modes are dispatched by their own branch, not this predicate."""
    assert (
        run_cmd._text_run_renders_in_process(mode, image=None)
        is False
    )


def test_image_run_stays_wrapper_only(no_wrapper):
    """--image keeps the wrapper's vision path, so it never renders in-process."""
    assert (
        run_cmd._text_run_renders_in_process(None, image=["bug.png"])
        is False
    )


def test_agent_text_preset_mapping():
    """Text modes map to the core Agent output presets."""
    assert run_cmd._agent_text_preset(None) == "minimal"
    assert run_cmd._agent_text_preset("plain") == "minimal"
    assert run_cmd._agent_text_preset("silent") == "minimal"
    assert run_cmd._agent_text_preset("verbose") == "verbose"


@pytest.mark.parametrize("mode", [None, "plain", "silent"])
def test_silent_style_modes_print_final_text(mode):
    """Silent-style presets print the final answer from the CLI itself."""
    assert run_cmd._prints_final_text(mode) is True


@pytest.mark.parametrize("mode", ["verbose", "actions"])
def test_self_rendering_modes_do_not_print_final_text(mode):
    """Verbose renders via the agent display; actions via the core status module."""
    assert run_cmd._prints_final_text(mode) is False


@pytest.mark.parametrize("mode", [None, "plain", "silent", "json", "stream", "stream-json"])
def test_cli_prints_final_text_for_silent_presets(mode):
    """Silent presets leave the rendering to the CLI, structured ones included."""
    assert run_cmd._prints_final_text(mode) is True


def test_structured_preset_mapping():
    """Only `actions` maps onto a core preset; the rest stay agent-silent.

    The core ``json`` preset writes JSONL to stderr and the core ``stream``
    preset makes ``Agent.start()`` return an unconsumed generator, so the CLI
    owns the output for those modes instead of delegating to a core preset.
    """
    assert run_cmd._structured_agent_preset("actions") == "actions"
    for mode in ("json", "stream", "stream-json"):
        assert run_cmd._structured_agent_preset(mode) == "silent"


# --- the remaining targeted gate: --image -----------------------------------


def test_require_wrapper_noop_when_wrapper_installed(with_wrapper):
    """With the wrapper installed, the gate passes through (delegation happens)."""
    run_cmd._require_wrapper_for_default_run(
        "hi", agent=None, command=None, output_mode="plain"
    )


def test_require_wrapper_noop_for_structured_mode(no_wrapper):
    """Structured modes run in-process, so the gate never trips for them."""
    run_cmd._require_wrapper_for_default_run(
        "hi", agent=None, command=None, output_mode="actions"
    )


@pytest.mark.parametrize("mode", [None, "silent", "plain", "verbose"])
def test_text_runs_do_not_gate_without_wrapper(no_wrapper, mode):
    """Standalone text runs no longer gate: they render in-process (#5644)."""
    run_cmd._require_wrapper_for_default_run(
        "hi", agent=None, command=None, output_mode=mode
    )


def test_image_run_without_wrapper_gates_with_targeted_hint(monkeypatch):
    """A standalone image run gates with a hint that cites praisonai-code."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )

    messages = []

    class _Output:
        def print_error(self, msg):
            messages.append(msg)

    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: _Output())

    with pytest.raises(typer.Exit):
        run_cmd._require_wrapper_for_default_run(
            "hi", agent=None, command=None, output_mode=None, image=["bug.png"]
        )

    assert messages
    assert "--image" in messages[0]
    assert 'praisonai-code run --output actions "your prompt"' in messages[0]
    assert "praisonai run --output actions" not in messages[0]


def test_image_run_with_wrapper_does_not_gate(with_wrapper):
    """With the wrapper installed the image run proceeds to the vision path."""
    run_cmd._require_wrapper_for_default_run(
        "hi", agent=None, command=None, output_mode=None, image=["bug.png"]
    )


@pytest.mark.parametrize("mode", [None, "plain", "verbose", "silent", "json", "stream", "stream-json"])
def test_every_image_output_mode_gates_without_wrapper(no_wrapper, monkeypatch, mode):
    """Any remaining image run must get the targeted hint, not a bare import error.

    The gate used to skip modes `_direct_prompt_needs_wrapper` excludes — the
    structured ones and `--command` — so those runs fell through to the wrapper
    path and failed with "praisonai.cli.legacy.direct_prompt requires the
    praisonai wrapper" instead of the actionable hint.
    """
    messages = []

    class _Output:
        def print_error(self, msg):
            messages.append(msg)

    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: _Output())

    with pytest.raises(typer.Exit):
        run_cmd._require_wrapper_for_default_run(
            "hi", agent=None, command=None, output_mode=mode, image=["bug.png"]
        )

    assert messages
    assert "--image" in messages[0]


def test_image_command_run_gates_without_wrapper(no_wrapper, monkeypatch):
    """`--command` prompts can reach this flow too, and also need the wrapper."""
    messages = []

    class _Output:
        def print_error(self, msg):
            messages.append(msg)

    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: _Output())

    with pytest.raises(typer.Exit):
        run_cmd._require_wrapper_for_default_run(
            "hi", agent=None, command="deploy", output_mode=None, image=["bug.png"]
        )

    assert messages
    assert "--image" in messages[0]


def _patch_agent(monkeypatch, captured, *, stop_reason=None, result="rendered answer"):
    """Install a fake ``praisonaiagents.Agent`` and neutralise the wiring helper.

    The in-process renderer now wires the shared agent surface
    (tools/session/instructions) before building the Agent; stub that helper so
    these unit tests stay focused on the renderer's own contract (return shape,
    stop-reason propagation, single print) without needing a real tool/session
    runtime.
    """
    import sys
    import types

    class _FakeAgent:
        last_stop_reason = stop_reason

        def __init__(self, **cfg):
            captured["cfg"] = cfg

        def start(self, prompt):
            captured["prompt"] = prompt
            return result

    fake_mod = types.ModuleType("praisonaiagents")
    fake_mod.Agent = _FakeAgent
    monkeypatch.setitem(sys.modules, "praisonaiagents", fake_mod)
    # Force the status-output import to fail so the simple path is exercised.
    monkeypatch.setitem(sys.modules, "praisonaiagents.output.status", None)
    monkeypatch.setattr(
        run_cmd, "_wire_run_agent_config", lambda *a, **k: None
    )


class _Args:
    llm = None
    max_tokens = None
    verbose = 0
    quiet = 0
    thinking_budget = None
    tools = None
    toolset = None
    mcp = None
    mcp_env = None
    mcp_servers = None
    approval = None
    no_rules = False
    instructions = None
    resume_session = None
    auto_save = None


class _Output:
    pass


def test_render_default_prompt_in_process(monkeypatch):
    """Default text run renders from an in-process Agent (no wrapper import)."""
    captured = {}
    _patch_agent(monkeypatch, captured)

    result, agent, printed = run_cmd._render_default_prompt_in_process(
        "hello", _Args(), _Output()
    )

    assert result == "rendered answer"
    assert captured["prompt"] == "hello"
    assert captured["cfg"]["name"] == "RunAgent"
    # The renderer must return the live Agent so the caller can consult
    # last_stop_reason for provider/step-limit cutoffs.
    assert getattr(agent, "last_stop_reason", "unset") is None
    # The simple fallback path (status import failed) did not print, so the
    # caller owns the single human-text print — no double output.
    assert printed is False


def test_render_passes_session_identity_to_wiring(monkeypatch):
    """--session/--continue identity reaches the shared wiring (no lost history)."""
    # Import the real session module before the fake praisonaiagents shadow is
    # installed so its ``apply_cli_session_continuity`` resolves, then patch it.
    import praisonai_code.cli.state.project_sessions as ps

    captured = {}
    _patch_agent(monkeypatch, captured)
    seen = {}
    monkeypatch.setattr(
        run_cmd,
        "_wire_run_agent_config",
        lambda cfg, **k: seen.update(k),
    )
    # apply_cli_session_continuity must be invoked with the resolved session id.
    continuity = {}
    monkeypatch.setattr(
        ps,
        "apply_cli_session_continuity",
        lambda agent, sid, auto_save=None: continuity.update(
            sid=sid, auto_save=auto_save
        ),
    )

    args = _Args()
    args.resume_session = "sess-123"
    args.auto_save = "sess-123"
    args.tools = "web"
    args.instructions = ["RULES.md"]

    run_cmd._render_default_prompt_in_process("hi", args, _Output())

    assert seen["session_id"] == "sess-123"
    assert seen["tools"] == "web"
    assert seen["instructions"] == ["RULES.md"]
    assert continuity == {"sid": "sess-123", "auto_save": "sess-123"}


def test_render_reports_stop_reason(monkeypatch):
    """A step-limit/length cutoff is surfaced via the returned agent, not hidden."""
    captured = {}
    _patch_agent(monkeypatch, captured, stop_reason="max_steps")

    result, agent, _printed = run_cmd._render_default_prompt_in_process(
        "hi", _Args(), _Output()
    )

    assert result == "rendered answer"
    # The caller uses _run_was_truncated(agent) -> exit 2; prove the signal
    # reaches it rather than being discarded by the renderer.
    assert run_cmd._run_was_truncated(agent) is True

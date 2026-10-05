"""Regression tests for standalone text-mode in-process rendering (issue #5644).

`pip install praisonai-code` alone used to gate the default human-readable run
(`run "prompt"`, `--output plain/verbose/silent`) with an install hint, because
those modes delegated to the wrapper's `handle_direct_prompt`. These tests pin
the fixed behaviour: on a standalone install the text modes render in-process
from the same Agent loop the structured `--output actions` path already uses,
while a wrapper-installed environment still delegates (unchanged).

The Agent is faked so the tests never touch a provider; the wrapper is faked at
the module boundary the way `test_run_image_attachment.py` does it.
"""

import json
import sys
import types

import pytest

from praisonai_code.cli.commands import run as run_cmd
from praisonai_code.cli.output.console import OutputMode


class _RecordingOutput:
    """Minimal stand-in for the CLI OutputController.

    Mirrors the two behaviours the run path branches on: events are always
    recorded, printed as NDJSON only in STREAM_JSON mode, and `is_json_mode`
    follows the mode. A stub that hard-coded `is_json_mode = False` could not
    observe the bridge, which is how the `stream-json` blind spot survived the
    first cut of this fix.
    """

    def __init__(self, mode=OutputMode.TEXT):
        self.results = []
        self.errors = []
        self.events = []
        self.mode = mode

    @property
    def is_json_mode(self):
        return self.mode in (OutputMode.JSON, OutputMode.STREAM_JSON)

    def emit_event(self, event_type, message=None, data=None, agent_id=None):
        self.events.append((event_type, data))
        if self.mode == OutputMode.STREAM_JSON:
            print(json.dumps({"event": event_type, "data": data}), flush=True)

    def emit_result(self, message=None, data=None):
        self.results.append((message, data))
        self.emit_event("result", message=message, data=data)

    def emit_error(self, message=None, data=None):
        self.errors.append((message, data))
        self.emit_event("error", message=message, data=data)

    def print_info(self, *a, **k):
        pass

    def print_warning(self, *a, **k):
        pass

    def print_error(self, *a, **k):
        pass


def _install_fake_praisonai(monkeypatch):
    """Install a fake PraisonAI that records delegation of a text run."""
    captured = {}

    class _FakePraisonAI:
        def __init__(self, *a, **k):
            self.config_list = [{}]
            self.args = None

        def handle_direct_prompt(self, prompt):
            captured["prompt"] = prompt
            return "wrapper answer"

    fake_main = types.ModuleType("praisonai_code.cli.main")
    fake_main.PraisonAI = _FakePraisonAI
    monkeypatch.setitem(sys.modules, "praisonai_code.cli.main", fake_main)
    return captured


def _install_fake_agent(monkeypatch):
    """Replace praisonaiagents.Agent with a recorder; returns the captured config."""
    captured = {}

    class _FakeAgent:
        def __init__(self, **config):
            captured["config"] = config

        def start(self, prompt):
            captured["prompt"] = prompt
            return "agent answer"

    monkeypatch.setattr("praisonaiagents.Agent", _FakeAgent)
    return captured


@pytest.fixture
def standalone(monkeypatch):
    """A standalone install: wrapper not available, warm runtime not reachable."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    return output


def test_standalone_default_run_renders_in_process(standalone, monkeypatch, capsys):
    """`run "hi"` on a standalone install runs the in-process Agent and prints."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True)

    assert captured["prompt"] == "hi"
    assert captured["config"]["output"] == "minimal"
    assert "agent answer" in capsys.readouterr().out


@pytest.mark.parametrize(
    "mode,preset", [(None, "minimal"), ("plain", "minimal"), ("silent", "minimal"), ("verbose", "verbose")]
)
def test_text_modes_map_to_agent_presets(standalone, monkeypatch, mode, preset):
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode=mode)

    assert captured["config"]["output"] == preset


def test_verbose_run_lets_the_agent_render(standalone, monkeypatch, capsys):
    """The verbose preset renders the response itself; the CLI stays quiet."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="verbose")

    assert captured["config"]["output"] == "verbose"
    assert "agent answer" not in capsys.readouterr().out


def test_memory_flag_is_honoured_in_process(standalone, monkeypatch):
    """--memory must not be silently dropped by the in-process text path."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, memory=True)

    assert captured["config"]["memory"] is True


def test_wrapper_installed_text_run_still_delegates(monkeypatch, capsys):
    """With the wrapper installed, a text run delegates exactly as before."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: True
    )
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    captured = _install_fake_praisonai(monkeypatch)
    agent_started = _install_fake_agent(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True)

    assert captured["prompt"] == "hi"
    assert "prompt" not in agent_started  # the in-process Agent was not used
    assert "wrapper answer" in capsys.readouterr().out


def test_structured_actions_run_unchanged(standalone, monkeypatch):
    """--output actions keeps its structured preset and in-process dispatch."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="actions")

    assert captured["config"]["output"] == "actions"


def test_permission_policy_is_enforced_in_process(standalone, monkeypatch):
    """--allow/--deny/--permissions must gate the run, not be silently dropped."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt(
        "rm -rf build",
        no_save=True,
        permissions_config={"bash:rm *": "deny"},
    )

    approval = captured["config"].get("approval")
    assert approval is not None, "a permission policy must gate the run"
    permissions = getattr(approval, "permissions", approval)
    assert permissions and "bash:rm *" in permissions


def test_plain_standalone_run_install_no_approval(standalone, monkeypatch):
    """A run without permission flags must not gain an approval backend."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True)

    assert captured["config"].get("approval") is None


def test_verbose_flag_selects_the_verbose_preset(standalone, monkeypatch, capsys):
    """`--verbose` folds into the Agent preset, as the wrapper text path does.

    The flag is separate from `--output`, so without this a standalone default
    run would take the silent preset and render differently from the very same
    command on a wrapper-installed install.
    """
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, verbose=True)

    assert captured["config"]["output"] == "verbose"
    # The verbose preset renders the response itself; the CLI must not print it
    # a second time.
    assert "agent answer" not in capsys.readouterr().out


def test_explicit_output_mode_wins_over_verbose_flag(standalone, monkeypatch):
    """An explicit `--output plain` is not overridden by `--verbose`."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, verbose=True, output_mode="plain")

    assert captured["config"]["output"] == "minimal"


# --- structured output modes run in-process too (issue #5665) ---------------


@pytest.mark.parametrize(
    "mode,preset", [
        ("actions", "actions"),
        ("json", "silent"),
        ("stream", "silent"),
        ("stream-json", "silent"),
    ]
)
def test_structured_modes_run_in_process(standalone, monkeypatch, mode, preset):
    """`--output json/stream/stream-json` no longer fall through to the wrapper."""
    captured = _install_fake_agent(monkeypatch)
    delegated = _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode=mode)

    assert captured["prompt"] == "hi"
    assert captured["config"]["output"] == preset
    assert "prompt" not in delegated, "structured modes must not delegate"


def test_structured_modes_print_the_answer(standalone, monkeypatch, capsys):
    """A structured run must leave the answer on stdout, not return nothing.

    The core `json` preset routes its JSONL to stderr and the core `stream`
    preset makes `Agent.start()` return a generator this path would never
    consume, so neither preset can be used here: the CLI owns the output and
    every mode leaves the answer on stdout — as a single-line envelope for
    `json`, and as the answer itself for `stream`. `stream-json` frames it as
    NDJSON events instead (see the controller test below).
    """
    _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    for mode in ("json", "stream"):
        capsys.readouterr()
        run_cmd._run_prompt("hi", no_save=True, output_mode=mode)
        assert "agent answer" in capsys.readouterr().out, mode


def test_structured_json_mode_emits_a_single_line_envelope(standalone, monkeypatch, capsys):
    """`--output json` is a scripting surface: one parseable envelope on stdout.

    Mirrors the envelope `code -p --output json` emits, so a script can read the
    result from stdout instead of scraping interleaved decorations.
    """
    import json

    _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="json")

    out = capsys.readouterr().out
    envelope = json.loads(out)
    assert envelope == {"result": "agent answer", "status": "ok"}
    assert out.count("\n") == 1, "the envelope must be a single line"


def test_structured_json_envelope_yields_to_the_event_bridge(standalone, monkeypatch, capsys):
    """With the bridge active the NDJSON framing already carries the result.

    `--output-format stream-json` makes the OutputController print its own
    result event, so printing a second envelope here would corrupt the stream.
    """
    import json

    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)
    stream_json = _RecordingOutput(mode=OutputMode.STREAM_JSON)
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: stream_json)

    run_cmd._run_prompt("hi", no_save=True, output_mode="json")

    out = capsys.readouterr().out
    events = [json.loads(line)["event"] for line in out.strip().splitlines()]
    # The bridge framed the run; the CLI must not add a second, differently
    # shaped envelope on top of the NDJSON stream.
    assert "run.result" in events
    assert not any(
        json.loads(line).get("data", {}).get("status") == "ok"
        for line in out.strip().splitlines()
    ), out


def test_stream_json_selects_the_ndjson_controller(standalone, monkeypatch, capsys):
    """`--output stream-json` must activate the controller's NDJSON mode.

    The event bridge only writes stdout in STREAM_JSON mode, so without this the
    per-command selector was reachable only through the global
    `--output-format stream-json` and a user who typed it got plain text.
    """
    import json

    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="stream-json")

    assert standalone.mode == OutputMode.STREAM_JSON
    out = capsys.readouterr().out
    # Only framed events: every line must parse as JSON, so no bare answer is
    # mixed into the NDJSON stream.
    lines = [json.loads(line) for line in out.strip().splitlines()]
    assert "agent answer" not in out.split("\n")
    assert any(line["event"] == "run.result" for line in lines), out


def test_global_json_format_wins_over_stream_json(standalone, monkeypatch):
    """An explicit `--output-format json` is not overridden by the run selector."""
    from praisonai_code.cli.output.console import OutputMode

    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)
    json_controller = _RecordingOutput(mode=OutputMode.JSON)
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: json_controller)

    run_cmd._run_prompt("hi", no_save=True, output_mode="stream-json")

    assert json_controller.mode == OutputMode.JSON


def test_structured_mode_with_wrapper_installed_stays_in_process(monkeypatch):
    """Unlike text runs, structured modes never delegate to the wrapper.

    The wrapper's direct-prompt path maps every mode to the same silent Agent
    preset, so `--output json` used to mean "print the raw text answer". Routing
    them in-process unconditionally is what makes the README's structured-output
    row true.
    """
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: True
    )
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    captured = _install_fake_agent(monkeypatch)
    delegated = _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="json")

    assert captured["prompt"] == "hi"
    assert "prompt" not in delegated

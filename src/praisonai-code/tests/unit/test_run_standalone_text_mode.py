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

import typer

from praisonai_code.cli.commands import run as run_cmd
from praisonai_code.cli.output.console import OutputMode


class _RecordingOutput:
    """Minimal stand-in for the CLI OutputController.

    Mirrors the three behaviours the run path branches on: events are always
    recorded and printed as NDJSON only in STREAM_JSON mode; ``is_json_mode``
    follows the mode; and human notices go to **stdout** when the mode is not
    quiet, which is what the real controller does — including ``print_error``,
    whose Rich branch renders a Panel onto stdout rather than stderr. Stubs that
    silently dropped these are how three separate stdout-corruption blind spots
    survived earlier rounds of this fix.
    """

    def __init__(self, mode=OutputMode.TEXT):
        self.results = []
        self.errors = []
        self.events = []
        self.mode = mode

    @property
    def is_json_mode(self):
        return self.mode in (OutputMode.JSON, OutputMode.STREAM_JSON)

    @property
    def is_quiet(self):
        return self.mode == OutputMode.QUIET

    def emit_event(self, event_type, message=None, data=None, agent_id=None):
        self.events.append((event_type, data))
        if self.mode == OutputMode.STREAM_JSON:
            print(json.dumps({"event": event_type, "data": data}), flush=True)

    def emit_start(self, message=None, data=None):
        # Mirror the real controller: the canonical ``run.start`` is framed only
        # in STREAM_JSON mode, alongside the legacy ``start`` event.
        self.emit_event("start", message=message, data=data)
        if self.mode == OutputMode.STREAM_JSON:
            self.emit_event("run.start", message=message, data=data)

    def emit_result(self, message=None, data=None):
        self.results.append((message, data))
        self.emit_event("result", message=message, data=data)

    def emit_error(self, message=None, data=None):
        self.errors.append((message, data))
        self.emit_event("error", message=message, data=data)

    def print_info(self, message):
        if self.is_quiet:
            return
        print(f"INFO: {message}")

    def print_warning(self, message):
        if self.is_quiet:
            return
        print(f"WARNING: {message}")

    def print_error(self, message, code=None, remediation=None):
        # The real controller renders a Rich Panel onto stdout here, not stderr.
        if self.is_quiet:
            return
        print(f"ERROR: {message}")
        if remediation:
            print(f"FIX: {remediation}")


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


def _install_failing_agent(monkeypatch, **traits):
    """Install a fake Agent whose run takes a specific terminal outcome.

    ``stop_reason`` lands on the agent's ``last_stop_reason``, the core signal
    `_run_prompt` reads: a provider block/refusal reason ("refused",
    "content_filtered", "length_truncated"), or "max_steps" for a step-limit
    truncation after a partial answer. ``empty`` yields no result at all, which
    the run treats as a hard failure. Left out, the run completes cleanly.
    """
    captured = {}

    class _FakeAgent:
        def __init__(self, **config):
            captured["config"] = config
            self.last_stop_reason = traits.get("stop_reason")

        def start(self, prompt):
            captured["prompt"] = prompt
            return "" if traits.get("empty") else "partial answer"

    monkeypatch.setattr("praisonaiagents.Agent", _FakeAgent)
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


def test_implicit_console_fails_closed_on_non_tty(standalone, monkeypatch):
    """An implicitly-derived console backend must be non-interactive off a TTY.

    A permission policy with no explicit --approval derives the console
    backend. On a non-TTY (CI/pipeline) an unmatched ``ask`` rule must deny
    rather than block on input() or read piped stdin as operator consent.
    """
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    seen = {}

    def _fake_resolve(backend_name=None, **kwargs):
        seen["backend_name"] = backend_name
        seen["non_interactive"] = kwargs.get("non_interactive")
        return {"backend": backend_name}

    monkeypatch.setattr(
        "praisonai_code.cli.features._approval_bridge.resolve_approval_config",
        _fake_resolve,
    )
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    run_cmd._run_prompt(
        "rm -rf build",
        no_save=True,
        permissions_config={"bash:rm *": "ask"},
    )

    assert seen["backend_name"] == "console"
    assert seen["non_interactive"] is True


def test_explicit_approval_not_forced_non_interactive(standalone, monkeypatch):
    """An explicit --approval console keeps the backend's own interactivity.

    Only the implicitly-derived backend fails closed off a TTY; an explicit
    choice is left to the backend so interactive prompting is preserved.
    """
    _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    seen = {}

    def _fake_resolve(backend_name=None, **kwargs):
        seen["non_interactive"] = kwargs.get("non_interactive")
        return {"backend": backend_name}

    monkeypatch.setattr(
        "praisonai_code.cli.features._approval_bridge.resolve_approval_config",
        _fake_resolve,
    )
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    run_cmd._run_prompt("hi", no_save=True, approval="console")

    assert seen["non_interactive"] is False


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

    out = capsys.readouterr().out
    # Only framed events: every line must parse as JSON, so no bare answer is
    # mixed into the NDJSON stream.
    lines = [json.loads(line) for line in out.strip().splitlines()]
    assert "agent answer" not in out.split("\n")
    assert any(line["event"] == "run.result" for line in lines), out
    # The framing was scoped to this run: the caller's controller is untouched.
    assert standalone.mode == OutputMode.TEXT


@pytest.mark.parametrize("mode", [OutputMode.JSON, OutputMode.QUIET, OutputMode.VERBOSE, OutputMode.SCREEN_READER])
def test_stream_json_yields_to_an_explicit_global_mode(monkeypatch, capsys, mode):
    """`--quiet`/`--verbose`/`--screen-reader` outrank the per-command selector.

    app.py resolves quiet/verbose/screen-reader above output_format, so
    `run --quiet --output stream-json` must not start printing NDJSON events.
    """
    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)
    controller = _RecordingOutput(mode=mode)
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: controller)

    run_cmd._run_prompt("hi", no_save=True, output_mode="stream-json")

    assert controller.mode == mode
    # No NDJSON framing leaked into a run whose global preference was explicit.
    assert '"event"' not in capsys.readouterr().out


def test_ndjson_framing_does_not_leak_into_a_later_run(standalone, monkeypatch, capsys):
    """The controller is process-wide, so the framing must be run-scoped.

    An embedded caller that runs `--output stream-json` and then a plain-text run
    must not have the second one framed as NDJSON.
    """
    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="stream-json")
    capsys.readouterr()
    run_cmd._run_prompt("hi", no_save=True)

    assert standalone.mode == OutputMode.TEXT
    assert capsys.readouterr().out == "agent answer\n"


# --- the JSON envelope covers every terminal outcome, not just success ------


@pytest.mark.parametrize(
    "stop_reason,status,exit_code",
    [
        ("refused", "refused", 2),
        ("content_filtered", "content_filtered", 2),
        ("max_steps", "truncated", 2),
    ],
)
def test_json_envelope_covers_incomplete_terminal_states(
    standalone, monkeypatch, capsys, stop_reason, status, exit_code
):
    """`--output json` must not exit silently on a blocked/truncated run.

    These paths raise before the success-only envelope, so a script parsing
    stdout used to get nothing at all and only a human warning.
    """
    import json

    _install_fake_praisonai(monkeypatch)
    _install_failing_agent(monkeypatch, stop_reason=stop_reason)

    with pytest.raises(typer.Exit) as exc:
        run_cmd._run_prompt("hi", no_save=True, output_mode="json")

    assert exc.value.exit_code == exit_code
    out = capsys.readouterr()
    # The envelope is machine-readable and is the only thing on stdout.
    assert json.loads(out.out) == {"result": "partial answer", "status": status}
    # The human warning goes nowhere near stdout.
    assert "Run" not in out.out


def test_json_envelope_covers_a_failed_run(standalone, monkeypatch, capsys):
    """An empty result is a failure, and it must still carry a status.

    The failure reporter renders a Rich error panel onto **stdout** whenever Rich
    is available (``OutputController.print_error``'s non-stderr branch), so on the
    JSON path that panel has to be moved to stderr — otherwise stdout is an
    envelope followed by a panel and a script can parse neither position.
    """
    import json

    _install_fake_praisonai(monkeypatch)
    _install_failing_agent(monkeypatch, empty=True)

    with pytest.raises(typer.Exit):
        run_cmd._run_prompt("hi", no_save=True, output_mode="json")

    streams = capsys.readouterr()
    assert json.loads(streams.out) == {"result": None, "status": "failed"}
    assert len(streams.out.strip().splitlines()) == 1
    assert "Run failed" in streams.err


def test_quiet_mode_suppresses_the_json_envelope(monkeypatch, capsys):
    """`--quiet` is an explicit request for no machine output on stdout.

    app.py resolves quiet above output_format, and the ``stream-json`` wiring
    already respects that, so the per-command ``--output json`` selector — which
    replaces human TEXT output with machine output — must not override it. The
    bare answer that remains is the pre-existing ``print(result)`` every text
    mode shares (it bypasses the controller), so quiet is no worse here than a
    plain `run`; the point is that no envelope is emitted.
    """
    from praisonai_code.cli.output.console import OutputMode

    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)
    controller = _RecordingOutput(mode=OutputMode.QUIET)
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: controller)
    _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="json")

    out = capsys.readouterr().out
    assert '"status"' not in out, "quiet must suppress the envelope"


def test_json_envelope_covers_an_unexpected_raise(standalone, monkeypatch, capsys):
    """A raise during setup or inside the agent is a terminal outcome too.

    The exception handler used to write only to stderr, so a script reading
    stdout lost `status` for exactly the failures that are hardest to diagnose.
    """
    import json

    _install_fake_praisonai(monkeypatch)

    class _ExplodingAgent:
        def __init__(self, **config):
            pass

        def start(self, prompt):
            raise RuntimeError("provider exploded")

    monkeypatch.setattr("praisonaiagents.Agent", _ExplodingAgent)

    with pytest.raises(typer.Exit) as exc:
        run_cmd._run_prompt("hi", no_save=True, output_mode="json")

    assert exc.value.exit_code == 1
    streams = capsys.readouterr()
    assert json.loads(streams.out) == {"result": None, "status": "failed"}
    assert len(streams.out.strip().splitlines()) == 1
    assert "provider exploded" in streams.err


def test_failed_json_run_keeps_quiet_silent(monkeypatch, capsys):
    """A failing quiet run must not start printing to stdout either."""
    from praisonai_code.cli.output.console import OutputMode

    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)
    controller = _RecordingOutput(mode=OutputMode.QUIET)
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: controller)
    _install_failing_agent(monkeypatch, empty=True)
    _install_fake_praisonai(monkeypatch)

    with pytest.raises(typer.Exit):
        run_cmd._run_prompt("hi", no_save=True, output_mode="json")

    assert capsys.readouterr().out == ""


def test_json_envelope_under_global_json_mode(standalone, monkeypatch, capsys):
    """`--output-format json` + `--output stream-json` must not exit silently.

    The global mode keeps precedence, so the per-command selector's NDJSON
    framing is not installed — but the envelope still has to reach stdout, which
    is the whole point of an ordinary-JSON controller.
    """
    import json

    from praisonai_code.cli.output.console import OutputMode

    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)
    controller = _RecordingOutput(mode=OutputMode.JSON)
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: controller)

    run_cmd._run_prompt("hi", no_save=True, output_mode="stream-json")

    assert controller.mode == OutputMode.JSON
    assert json.loads(capsys.readouterr().out) == {
        "result": "agent answer",
        "status": "ok",
    }


def test_actions_mode_keeps_its_own_rendering_under_json_mode(
    standalone, monkeypatch, capsys
):
    """`actions` renders via the core status module, so no second envelope.

    Adding one here would duplicate the answer on stdout.
    """
    from praisonai_code.cli.output.console import OutputMode

    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)
    controller = _RecordingOutput(mode=OutputMode.JSON)
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: controller)

    run_cmd._run_prompt("hi", no_save=True, output_mode="actions")

    assert "agent answer" not in capsys.readouterr().out
    assert '"status"' not in capsys.readouterr().out


def test_json_envelope_is_stdouts_only_line_with_auto_save(
    standalone, monkeypatch, capsys
):
    """The session usage footer must not land in front of the envelope.

    `--output json` runs with auto-save on by default, and the footer's
    `print_info` reaches stdout because the controller is human-facing — its
    `is_json_mode` is False. A notice in front of the envelope makes stdout
    invalid as a single JSON document, which is the whole contract. The prior
    tests all passed `no_save=True`, so none of them reached this path.
    """
    import json

    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)

    notices = []
    monkeypatch.setattr(
        "praisonai_code.cli.state.project_sessions.accumulate_session_usage",
        lambda *a, **k: {"total_tokens": 42, "input_tokens": 10, "output_tokens": 32},
    )
    monkeypatch.setattr(
        "praisonai_code.cli.state.project_sessions.maybe_auto_title_session",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        standalone, "print_info", lambda msg: notices.append(msg)
    )

    run_cmd._run_prompt("hi", output_mode="json")

    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1, out
    assert json.loads(out) == {"result": "agent answer", "status": "ok"}
    assert notices == []


def test_usage_footer_still_shows_for_a_default_run(standalone, monkeypatch, capsys):
    """The suppression is scoped to the JSON run; a human run keeps its footer."""
    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)

    monkeypatch.setattr(
        "praisonai_code.cli.state.project_sessions.accumulate_session_usage",
        lambda *a, **k: {"total_tokens": 42, "input_tokens": 10, "output_tokens": 32},
    )
    monkeypatch.setattr(
        "praisonai_code.cli.state.project_sessions.maybe_auto_title_session",
        lambda *a, **k: None,
    )
    printed = []
    monkeypatch.setattr(
        standalone, "print_info", lambda msg: printed.append(msg)
    )

    run_cmd._run_prompt("hi")

    assert printed, "a human run must still see the usage footer"
    assert "agent answer" in capsys.readouterr().out


def test_default_run_is_untouched_by_global_json_mode(monkeypatch, capsys):
    """A plain run under `--output-format json` keeps its pre-existing behaviour.

    The controller's JSON-mode finalisation is a gap shared by every command;
    quietly redefining it here would widen a routing fix into a cross-command
    output change.
    """
    from praisonai_code.cli.output.console import OutputMode

    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)
    controller = _RecordingOutput(mode=OutputMode.JSON)
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: controller)
    _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True)

    assert capsys.readouterr().out == ""


def test_structured_mode_with_wrapper_installed_stays_in_process(monkeypatch):
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


def test_stream_json_run_frames_the_start_event(standalone, monkeypatch):
    """`run --output stream-json "hi"` must frame ``run.start`` on stdout.

    ``run_main`` emits the start event before ``_run_prompt`` switches the
    controller into STREAM_JSON mode, so a direct-prompt run selected purely via
    the per-command selector used to record ``start``/``run.start`` without
    printing them — the NDJSON stream lost its documented first event and its
    target metadata. Driven through the real Typer app so every option default
    resolves normally; pins that the start event is framed and that the
    run-scoped framing is torn down afterwards.
    """
    from typer.testing import CliRunner

    _install_fake_praisonai(monkeypatch)
    _install_fake_agent(monkeypatch)
    # Keep run_main's credential/config preamble inert so the test drives only
    # the start-event framing, not provider or filesystem resolution.
    monkeypatch.setattr(
        "praisonai_code.llm.credentials.ensure_configured_or_onboard",
        lambda *a, **k: "gpt-4o",
    )
    monkeypatch.setattr(
        run_cmd, "resolve_config", lambda: (_ for _ in ()).throw(ValueError())
    )

    result = CliRunner().invoke(
        run_cmd.app, ["--output", "stream-json", "--no-save", "hi"]
    )

    out = result.output
    events = [
        json.loads(line)["event"]
        for line in out.strip().splitlines()
        if line.startswith("{")
    ]
    assert "run.start" in events, out
    # The framing was scoped to the run: the controller is back to TEXT.
    assert standalone.mode == OutputMode.TEXT

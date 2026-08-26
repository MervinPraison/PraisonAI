"""Tests for `--image` attachment on one-shot `praisonai run` (issue #4381).

The core Agent already accepts image input and the wrapper's
`handle_direct_prompt` routes `self.args.image` to the vision path. The only gap
was the CLI surface: `run` had no `--image` option and hardcoded
`args.image = None`. These tests pin that a `--image` attachment reaches the
agent via `args.image`, that a text-only run is unaffected (image stays None and
the warm-runtime fast path still applies), and that an image run bypasses the
warm runtime (which can't carry an attachment).
"""

import sys
import types

import pytest

from praisonai_code.cli.commands import run as run_cmd


class _RecordingOutput:
    def __init__(self):
        self.results = []
        self.is_json_mode = False

    def emit_result(self, message=None, data=None):
        self.results.append((message, data))

    def print_info(self, *a, **k):
        pass

    def print_warning(self, *a, **k):
        pass


def _install_fake_praisonai(monkeypatch):
    """Install a fake PraisonAI that records the args it receives and returns."""
    captured = {}

    class _FakePraisonAI:
        def __init__(self, *a, **k):
            self.config_list = [{}]
            self.args = None

        def handle_direct_prompt(self, prompt):
            captured["args"] = self.args
            captured["prompt"] = prompt
            return "done"

    fake_main = types.ModuleType("praisonai_code.cli.main")
    fake_main.PraisonAI = _FakePraisonAI
    monkeypatch.setitem(sys.modules, "praisonai_code.cli.main", fake_main)
    return captured


def test_image_reaches_agent_via_args(monkeypatch):
    """A single `--image` attachment is passed through as `args.image`."""
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)

    captured = _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt(
        "describe this",
        no_save=True,
        image=["bug.png"],
    )

    assert captured["args"].image == "bug.png"


def test_multiple_images_are_comma_joined(monkeypatch):
    """Repeated `--image` flags are joined for the multi-image vision path."""
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)

    captured = _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt(
        "compare these",
        no_save=True,
        image=["a.png", "b.png"],
    )

    assert captured["args"].image == "a.png,b.png"


def test_text_only_run_leaves_image_none(monkeypatch):
    """A run without `--image` keeps `args.image` None (unchanged behaviour)."""
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)

    captured = _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("just text", no_save=True)

    assert captured["args"].image is None


def test_image_run_bypasses_warm_runtime(monkeypatch):
    """An image attachment must run in-process, never via the warm runtime.

    The warm runtime is a separate process that can't carry the CLI's
    per-invocation attachment, so forwarding an image run would silently drop
    it. The run must stay in-process when an image is set.
    """
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)

    attach_calls = []

    def _fake_attach(*args, **kwargs):
        attach_calls.append((args, kwargs))
        return True

    monkeypatch.setattr(run_cmd, "_try_attach_runtime", _fake_attach)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("describe this", no_save=True, image=["bug.png"])

    assert not attach_calls, "image run must not forward to warm runtime"


def test_text_only_run_still_allows_warm_runtime(monkeypatch):
    """Without an image, an eligible no-save run still attaches warm."""
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)

    attach_calls = []

    def _fake_attach(*args, **kwargs):
        attach_calls.append((args, kwargs))
        return True

    monkeypatch.setattr(run_cmd, "_try_attach_runtime", _fake_attach)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("just text", no_save=True)

    assert attach_calls, "an eligible no-save run should attach to the warm runtime"


def _invoke_run(monkeypatch, args):
    """Invoke the `run` command function, stubbing credential onboarding.

    ``run_main`` is the callback of a Typer group; mounting it as a plain
    command on a throwaway Typer app lets ``CliRunner`` parse the options the
    same way the real CLI does. The guards under test raise ``typer.Exit``
    before any agent runs, so the only side effect that must be neutralised is
    the pre-run credential check.
    """
    import typer
    from typer.testing import CliRunner

    import praisonai_code.llm.credentials as _creds
    import praisonai_code._wrapper_bridge as _bridge

    monkeypatch.setattr(
        _creds, "ensure_configured_or_onboard", lambda *a, **k: "gpt-4o"
    )
    # Plain-text direct-prompt runs gate on the wrapper being installed; in the
    # test env it is absent, so pretend it's available to reach the guards.
    monkeypatch.setattr(_bridge, "wrapper_available", lambda *a, **k: True)
    test_app = typer.Typer()
    test_app.command()(run_cmd.run_main)
    return CliRunner().invoke(test_app, args)


def test_image_with_agent_is_rejected(monkeypatch):
    """`--image` with `--agent` fails before running (no silent drop)."""
    result = _invoke_run(
        monkeypatch, ["describe this", "--agent", "researcher", "--image", "a.png"]
    )
    assert result.exit_code == 1
    assert "--image is only supported for direct prompt runs" in result.output


def test_image_with_profile_is_rejected(monkeypatch):
    """`--image` with `--profile` fails before running (no silent drop)."""
    result = _invoke_run(
        monkeypatch, ["describe this", "--profile", "--image", "a.png"]
    )
    assert result.exit_code == 1
    assert "--image is only supported for direct prompt runs" in result.output


def test_image_with_yaml_file_is_rejected(monkeypatch, tmp_path):
    """`--image` with a YAML-file target fails before running (no silent drop)."""
    yaml_file = tmp_path / "agents.yaml"
    yaml_file.write_text("framework: praisonai\n")
    result = _invoke_run(
        monkeypatch, [str(yaml_file), "--image", "a.png"]
    )
    assert result.exit_code == 1
    assert "--image is only supported for direct prompt runs" in result.output


def test_image_with_actions_output_is_rejected(monkeypatch):
    """`--image` with `--output actions` fails (actions contract can't be met)."""
    result = _invoke_run(
        monkeypatch, ["describe this", "--output", "actions", "--image", "a.png"]
    )
    assert result.exit_code == 1
    assert "--image cannot be combined with --output actions" in result.output


def test_image_value_with_comma_is_rejected(monkeypatch):
    """A single `--image` value containing a comma is rejected, not corrupted.

    ImageHandler splits on commas for the multi-image path, so a comma inside a
    single path/URL would be fragmented. Users pass multiple images with
    repeated `--image` flags instead.
    """
    result = _invoke_run(
        monkeypatch, ["describe this", "--image", "a,b.png"]
    )
    assert result.exit_code == 1
    assert "must not contain a comma" in result.output

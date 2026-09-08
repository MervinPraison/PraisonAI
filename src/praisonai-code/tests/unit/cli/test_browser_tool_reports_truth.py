"""`praisonai browser-tool` must not report success for work it did not do.

Six of eight subcommands exited 0 regardless of outcome, because
``BrowserBaseTool.run`` reports failure by *returning* a value
(``{"error": "Unknown action: click"}``) rather than raising -- so the command
printed that dict as "Result:" and fell off the end.

Worse, ``screenshot --output shot.png`` printed "Screenshot saved to:
shot.png" without ever opening the file, and ``snapshot --output`` wrote the
error dict to disk as though it were page text.

These tests inject a fake BrowserBaseTool so the failure modes are exercised
without a browser, a network, or the optional praisonai-tools package.
"""

import sys
import types

import pytest
import typer
from typer.testing import CliRunner

import praisonai_code.cli.commands.browser_tool as bt

runner = CliRunner()


def _install_fake_tool(monkeypatch, run_impl):
    """Provide a praisonai_tools module whose BrowserBaseTool.run is run_impl."""

    class FakeBrowser:
        calls = []

        def run(self, **kwargs):
            FakeBrowser.calls.append(kwargs)
            return run_impl(**kwargs)

    FakeBrowser.calls = []
    module = types.ModuleType("praisonai_tools")
    module.BrowserBaseTool = FakeBrowser
    monkeypatch.setitem(sys.modules, "praisonai_tools", module)
    return FakeBrowser


# --------------------------------------------------------------------------
# In-band errors must become non-zero exits
# --------------------------------------------------------------------------

@pytest.mark.parametrize("args", [
    ["click", "#submit"],
    ["type", "#search", "hello"],
    ["navigate", "https://example.com"],
    ["open", "https://example.com"],
    ["snapshot"],
    ["screenshot"],
])
def test_an_unknown_action_exits_non_zero(monkeypatch, args):
    _install_fake_tool(
        monkeypatch, lambda **kw: {"error": f"Unknown action: {kw.get('action')}"}
    )
    result = runner.invoke(bt.app, args)
    assert result.exit_code != 0, (
        f"browser-tool {' '.join(args)} exited 0 while the browser reported "
        f"an error:\n{result.output}"
    )


def test_a_string_error_is_also_caught(monkeypatch):
    _install_fake_tool(monkeypatch, lambda **kw: "Error: no page is open")
    result = runner.invoke(bt.app, ["click", "#submit"])
    assert result.exit_code != 0


def test_a_raising_tool_exits_non_zero(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("browser crashed")

    _install_fake_tool(monkeypatch, _boom)
    result = runner.invoke(bt.app, ["click", "#submit"])
    assert result.exit_code != 0
    assert "browser crashed" in result.output


def test_a_genuine_success_still_exits_zero(monkeypatch):
    _install_fake_tool(monkeypatch, lambda **kw: {"ok": True, "title": "Example"})
    result = runner.invoke(bt.app, ["navigate", "https://example.com"])
    assert result.exit_code == 0, result.output


# --------------------------------------------------------------------------
# screenshot --output must produce a file
# --------------------------------------------------------------------------

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_screenshot_output_writes_the_file(monkeypatch, tmp_path):
    _install_fake_tool(monkeypatch, lambda **kw: {"bytes": _PNG})
    target = tmp_path / "shot.png"

    result = runner.invoke(bt.app, ["screenshot", "--output", str(target)])

    assert result.exit_code == 0, result.output
    assert target.exists(), (
        "reported 'Screenshot saved to' but wrote nothing:\n" + result.output
    )
    assert target.read_bytes() == _PNG


def test_screenshot_accepts_a_base64_payload(monkeypatch, tmp_path):
    import base64

    encoded = base64.b64encode(_PNG).decode()
    _install_fake_tool(monkeypatch, lambda **kw: {"image": encoded})
    target = tmp_path / "shot.png"

    assert runner.invoke(bt.app, ["screenshot", "-o", str(target)]).exit_code == 0
    assert target.read_bytes() == _PNG


def test_screenshot_with_no_image_data_fails_instead_of_claiming_success(
    monkeypatch, tmp_path
):
    _install_fake_tool(monkeypatch, lambda **kw: {"ok": True})
    target = tmp_path / "shot.png"

    result = runner.invoke(bt.app, ["screenshot", "--output", str(target)])

    assert result.exit_code != 0
    assert not target.exists()
    assert "Screenshot saved to" not in result.output


# --------------------------------------------------------------------------
# snapshot --output must not write an error as page text
# --------------------------------------------------------------------------

def test_snapshot_output_writes_the_page_text(monkeypatch, tmp_path):
    _install_fake_tool(monkeypatch, lambda **kw: "heading: Example Domain")
    target = tmp_path / "snap.txt"

    assert runner.invoke(bt.app, ["snapshot", "-o", str(target)]).exit_code == 0
    assert target.read_text() == "heading: Example Domain"


def test_snapshot_never_writes_an_error_dict_as_page_text(monkeypatch, tmp_path):
    _install_fake_tool(monkeypatch, lambda **kw: {"error": "Unknown action: snapshot"})
    target = tmp_path / "snap.txt"

    result = runner.invoke(bt.app, ["snapshot", "--output", str(target)])

    assert result.exit_code != 0
    assert not target.exists(), (
        "wrote the browser's error dict to disk as though it were page content"
    )


# --------------------------------------------------------------------------
# Declared flags must reach the tool
# --------------------------------------------------------------------------

def test_headless_double_and_submit_reach_the_tool(monkeypatch):
    fake = _install_fake_tool(monkeypatch, lambda **kw: {"ok": True})

    runner.invoke(bt.app, ["open", "https://example.com", "--headless"])
    assert fake.calls[-1].get("headless") is True

    runner.invoke(bt.app, ["click", "#x", "--double"])
    assert fake.calls[-1].get("double") is True

    runner.invoke(bt.app, ["type", "#x", "hi", "--submit"])
    assert fake.calls[-1].get("submit") is True


def test_a_non_default_profile_and_format_reach_the_tool(monkeypatch):
    fake = _install_fake_tool(monkeypatch, lambda **kw: "text")

    runner.invoke(bt.app, ["snapshot", "--profile", "chrome", "--format", "ai"])
    assert fake.calls[-1].get("profile") == "chrome"
    assert fake.calls[-1].get("format") == "ai"


def test_untouched_defaults_are_not_forwarded(monkeypatch):
    """A build of praisonai-tools with a narrow run() must keep working."""
    fake = _install_fake_tool(monkeypatch, lambda **kw: "text")

    runner.invoke(bt.app, ["snapshot"])
    assert set(fake.calls[-1]) == {"action"}, fake.calls[-1]


def test_a_flag_the_tool_cannot_honour_is_reported_not_dropped(monkeypatch):
    def _narrow(**kw):
        if set(kw) - {"action", "selector"}:
            raise TypeError(f"run() got unexpected kwargs: {sorted(set(kw) - {'action', 'selector'})}")
        return {"ok": True}

    _install_fake_tool(monkeypatch, _narrow)

    assert runner.invoke(bt.app, ["click", "#x"]).exit_code == 0
    result = runner.invoke(bt.app, ["click", "#x", "--double"])
    assert result.exit_code != 0
    assert "does not support" in result.output


# --------------------------------------------------------------------------
# status --json
# --------------------------------------------------------------------------

def test_status_json_emits_json(monkeypatch):
    import json

    _install_fake_tool(monkeypatch, lambda **kw: None)
    result = runner.invoke(bt.app, ["status", "--json", "--profile", "chrome"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["profile"] == "chrome"
    assert payload["available"] is True


def test_missing_praisonai_tools_still_exits_non_zero(monkeypatch):
    monkeypatch.setitem(sys.modules, "praisonai_tools", None)
    result = runner.invoke(bt.app, ["click", "#x"])
    assert result.exit_code != 0

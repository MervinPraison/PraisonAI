"""~/.praisonai/<ui>/app.py follows the bundled default unless the user edited it."""

import importlib.util
import subprocess

import pytest

from praisonai_code.cli.commands import ui as ui_mod

OLD = '"""Chat app."""\nVERSION = 1\n'


@pytest.fixture
def bundled(tmp_path):
    path = tmp_path / "default_app.py"
    path.write_text('"""Chat app."""\nVERSION = 2\n', encoding="utf-8")
    return path


def test_create_then_current(bundled, tmp_path):
    target = tmp_path / "home" / "app.py"
    assert ui_mod._sync_default_app(bundled, target) == "created"
    assert target.read_text(encoding="utf-8").partition("\n")[2] == bundled.read_text(encoding="utf-8")
    assert ui_mod._sync_default_app(bundled, target) == "current"


@pytest.mark.parametrize("stamped", [True, False])
def test_untouched_copy_is_refreshed(bundled, tmp_path, monkeypatch, stamped):
    monkeypatch.setattr(ui_mod, "_SHIPPED", frozenset({ui_mod._sha(OLD)[:16]}))
    target = tmp_path / "app.py"
    target.write_text(f"{ui_mod._STAMP}{ui_mod._sha(OLD)}\n{OLD}" if stamped else OLD, encoding="utf-8")
    assert ui_mod._sync_default_app(bundled, target) == "updated"
    assert target.read_text(encoding="utf-8").endswith("VERSION = 2\n")


def test_edited_copy_is_kept(bundled, tmp_path):
    target = tmp_path / "app.py"
    text = OLD + "MINE = True\n"
    target.write_text(text, encoding="utf-8")
    assert ui_mod._sync_default_app(bundled, target) == "edited"
    assert target.read_text(encoding="utf-8") == text


def test_the_march_2026_shipped_chat_copy_counts_as_untouched():
    assert "8dcb4c9ab3c89d9c" in ui_mod._SHIPPED


def test_launch_refreshes_a_stale_home_copy(bundled, tmp_path, monkeypatch):
    monkeypatch.setattr(ui_mod.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ui_mod, "_resolve_bundled_default_app", lambda name: bundled)
    monkeypatch.setattr(ui_mod, "_SHIPPED", frozenset({ui_mod._sha(OLD)[:16]}))
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda n, *a, **k: object() if n == "praisonaiui" else real_find_spec(n, *a, **k))
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    home_app = tmp_path / ".praisonai" / "ui" / "app.py"
    home_app.parent.mkdir(parents=True)
    home_app.write_text(OLD, encoding="utf-8")

    ui_mod._launch_aiui_app("ui", "ui_chat", 9003, "127.0.0.1", None, False, "Chat")

    assert home_app.read_text(encoding="utf-8").endswith("VERSION = 2\n")
    assert str(home_app) in calls[0]

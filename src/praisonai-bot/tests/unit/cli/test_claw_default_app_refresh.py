"""~/.praisonai/claw/app.py follows the bundled default unless the user edited it."""

import ast

import pytest

from praisonai_bot.cli.commands import claw as claw_mod


@pytest.fixture
def files(tmp_path):
    bundled = tmp_path / "default_app.py"
    bundled.write_text('"""Dashboard app."""\nVERSION = 2\n', encoding="utf-8")
    return bundled, tmp_path / "home" / "app.py"


def test_first_launch_writes_a_stamped_copy(files):
    bundled, target = files
    assert claw_mod._sync_default_app(bundled, target) == "created"
    text = target.read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    assert first.startswith(claw_mod._STAMP) and body == bundled.read_text(encoding="utf-8")
    assert ast.get_docstring(ast.parse(text)) == "Dashboard app."  # still the module docstring
    assert claw_mod._sync_default_app(bundled, target) == "current"


def test_untouched_stamped_copy_is_refreshed(files):
    bundled, target = files
    old = '"""Dashboard app."""\nVERSION = 1\n'
    target.parent.mkdir()
    target.write_text(f"{claw_mod._STAMP}{claw_mod._sha(old)}\n{old}", encoding="utf-8")
    assert claw_mod._sync_default_app(bundled, target) == "updated"
    assert target.read_text(encoding="utf-8").endswith("VERSION = 2\n")


def test_unstamped_copy_of_a_shipped_version_is_refreshed(files, monkeypatch):
    bundled, target = files
    old = '"""Dashboard app."""\nVERSION = 1\n'
    monkeypatch.setattr(claw_mod, "_SHIPPED", frozenset({claw_mod._sha(old)[:16]}))
    target.parent.mkdir()
    target.write_text(old, encoding="utf-8")
    assert claw_mod._sync_default_app(bundled, target) == "updated"
    assert target.read_text(encoding="utf-8").endswith("VERSION = 2\n")


@pytest.mark.parametrize("stamped", [True, False])
def test_edited_copy_is_kept(files, stamped):
    bundled, target = files
    old = '"""Dashboard app."""\nVERSION = 1\n'
    text = f"{claw_mod._STAMP}{claw_mod._sha(old)}\n{old}" if stamped else old
    text += "MY_AGENT = 'mine'\n"
    target.parent.mkdir()
    target.write_text(text, encoding="utf-8")
    assert claw_mod._sync_default_app(bundled, target) == "edited"
    assert target.read_text(encoding="utf-8") == text


def test_the_march_2026_shipped_copy_counts_as_untouched():
    # 75adcfed68, the claw default_app.py copied into ~/.praisonai/claw/app.py on
    # 2026-03-12; users who launched then still have it byte for byte.
    assert "1bf3cf65bdea6869" in claw_mod._SHIPPED


def test_ensure_default_app_uses_the_bundled_dashboard(monkeypatch, tmp_path):
    target = tmp_path / "claw" / "app.py"
    monkeypatch.setattr(claw_mod, "DEFAULT_APP", target)
    assert claw_mod._ensure_default_app() == target
    bundled = claw_mod.Path(claw_mod.__file__).parent.parent.parent / "claw" / "default_app.py"
    assert target.read_text(encoding="utf-8").partition("\n")[2] == bundled.read_text(encoding="utf-8")

"""The Windows autostart installer must not write into the working tree.

`_startup_folder()` uses `os.path.expandvars(r"%APPDATA%\\...")`. `%VAR%` syntax
is only expanded on Windows, so off Windows the string stays literal and
`os.makedirs()` created a `%APPDATA%\\Microsoft\\...` directory relative to the
current directory -- inside the repo when tests run there.

That path is invalid on Windows, so once committed it broke `actions/checkout`
for the whole repository before any test could run.
"""
import os

import pytest

pytest.importorskip("praisonai_bot")


def _has_unexpanded_var(path: str) -> bool:
    return "%" in path


@pytest.mark.skipif(os.name == "nt", reason="off-Windows behaviour under test")
def test_startup_entry_refuses_when_path_is_unexpanded(tmp_path, monkeypatch):
    from praisonai_bot.daemon.windows import _create_startup_folder_entry

    monkeypatch.chdir(tmp_path)
    result = _create_startup_folder_entry(str(tmp_path / "config.yaml"))

    assert result["ok"] is False, (
        f"installer claimed success off Windows: {result!r}"
    )

    stray = [p for p in tmp_path.rglob("*") if _has_unexpanded_var(p.name)]
    assert not stray, f"wrote a directory with an unexpanded variable: {stray}"


@pytest.mark.skipif(os.name == "nt", reason="off-Windows behaviour under test")
def test_running_the_daemon_tests_leaves_no_percent_paths(tmp_path, monkeypatch):
    """Control: the whole install path, not just the one helper."""
    from praisonai_bot.daemon.windows import install

    monkeypatch.chdir(tmp_path)
    try:
        install(str(tmp_path / "config.yaml"))
    except Exception:
        pass  # failing is fine off Windows; writing junk is not

    stray = [p for p in tmp_path.rglob("*") if _has_unexpanded_var(p.name)]
    assert not stray, f"install path wrote unexpanded-variable dirs: {stray}"


def test_control_detector_matches_a_known_bad_name():
    """Control probe: without this, the scans above could pass vacuously."""
    assert _has_unexpanded_var("%APPDATA%")
    assert not _has_unexpanded_var("Startup")

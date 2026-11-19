"""The config path cannot add lines or arguments to a generated service file.

systemd, launchd and the Windows startup script embed the config path; each
generator gets it from ``daemon.service_config_path``. The guard lists every
generator so a new one must use the helper.
"""
import ast
import plistlib
from pathlib import Path
from unittest import mock

import pytest

from praisonai_bot import daemon
from praisonai_bot.daemon import launchd, systemd, windows

GENERATORS = {
    "systemd": systemd._generate_unit,
    "launchd": launchd._generate_plist,
    "windows": windows._generate_startup_script,
}

BAD_PATHS = [
    "/tmp/bot.yaml\nExecStartPre=/bin/sh -c id",
    "/tmp/bot.yaml\r\n[Service]",
    '/tmp/bot.yaml" --rogue "x',
    "/tmp/%h/bot.yaml",
    "/tmp/bot\x00.yaml",
]


@pytest.fixture(autouse=True)
def _no_config_read(monkeypatch):
    monkeypatch.setattr(daemon, "stop_timeout_seconds", lambda path: 60)


@pytest.mark.parametrize("kind", GENERATORS)
@pytest.mark.parametrize("path", BAD_PATHS)
def test_generators_refuse_paths_that_break_out(kind, path):
    with pytest.raises(ValueError, match="service file"):
        GENERATORS[kind](path)


@pytest.mark.parametrize("path", BAD_PATHS)
def test_install_daemon_reports_bad_path_without_writing(path):
    with mock.patch.object(daemon, "_detect_platform", side_effect=AssertionError("not reached")):
        result = daemon.install_daemon(path)
    assert result["ok"] is False and "service file" in result["error"]


def test_systemd_unit_quotes_config_path_with_spaces():
    unit = systemd._generate_unit("/srv/my bots/bot.yaml")
    exec_line = next(l for l in unit.splitlines() if l.startswith("ExecStart="))
    assert exec_line.endswith('--config "/srv/my bots/bot.yaml"')
    assert sum(l.startswith("ExecStart") for l in unit.splitlines()) == 1


def test_launchd_plist_stays_valid_xml_with_markup_in_path():
    path = "/srv/a&b/<x>/bot.yaml"
    plist = plistlib.loads(launchd._generate_plist(path).encode())
    assert plist["ProgramArguments"][-1] == path
    assert plist["WorkingDirectory"] == "/srv/a&b/<x>"


def test_windows_script_keeps_config_path_in_one_quoted_argument():
    script = windows._generate_startup_script("/srv/a&b/bot.yaml")
    assert '--config "/srv/a&b/bot.yaml"' in script


def test_guard_every_generator_uses_service_config_path():
    pkg = Path(daemon.__file__).parent
    found = {}
    for path in pkg.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_generate"):
                found[path.stem] = node
    assert set(found) == set(GENERATORS)
    for stem, func in found.items():
        src = ast.unparse(func)
        assert "service_config_path(config_path)" in src, stem
        assert "os.path.abspath(config_path)" not in src, stem

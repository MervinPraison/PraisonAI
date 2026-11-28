"""Exercise the doctor CLI entry point and diagnostic routing."""

import json
import os
import subprocess
import sys

import pytest
from rich.text import Text
from typer.testing import CliRunner


def run_doctor(*args):
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(sys.path),
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "1",
    }
    env.pop("FORCE_COLOR", None)
    return subprocess.run(
        [sys.executable, "-m", "praisonai", "doctor", *args],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        env=env,
    )


def test_doctor_help():
    result = run_doctor("--help")
    assert result.returncode == 0, result.stderr
    help_text = Text.from_ansi(result.stdout).plain
    assert "--quick" in help_text
    assert "--json" in help_text


@pytest.mark.parametrize("args", [("env", "--json"), ("--quick", "--json")])
def test_doctor_environment_json(args):
    result = run_doctor(*args)
    report = json.loads(result.stdout)
    assert result.returncode == report["exit_code"]
    assert result.returncode in (0, 1)
    assert report["version"] and report["summary"]
    assert report["mode"] == "fast"
    assert {check["category"] for check in report["results"]} == {"environment"}


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], []),
        (["--deep", "--strict", "--json"], ["--deep", "--strict", "--json"]),
        (["mcp"], ["mcp"]),
        (["network"], ["network"]),
        (["selftest"], ["selftest"]),
    ],
)
def test_doctor_dispatch(args, expected, monkeypatch):
    from praisonai.cli.commands import doctor

    calls = []

    def run_diagnostics(options):
        calls.append(options)
        return 1

    monkeypatch.setattr(doctor, "_run_doctor", run_diagnostics)
    result = CliRunner().invoke(doctor.app, args)
    assert result.exit_code == 1, result.output
    assert calls == [expected]

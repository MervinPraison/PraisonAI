"""`praisonai[dashboard]` is the install extra; `praisonai[claw]` stays as its alias."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _extras():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["optional-dependencies"]


def test_dashboard_extra_installs_the_dashboard():
    deps = " ".join(_extras()["dashboard"])
    assert "aiui[all]" in deps
    assert "praisonai-bot[gateway,bot]" in deps


def test_claw_extra_is_an_alias_for_dashboard():
    assert _extras()["claw"] == ["praisonai[dashboard]"]

"""config.toml must be readable on Python 3.10, which has no tomllib (D-15)."""

from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


@pytest.mark.skipif(not PYPROJECT.exists(), reason="source checkout only")
def test_tomli_is_a_dependency_below_python_311():
    try:
        import tomllib
    except ImportError:  # Python 3.10: the very case this test guards
        tomllib = pytest.importorskip("tomli")
    deps = tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]
    tomli = [d for d in deps if d.split(";")[0].strip().startswith("tomli") and not d.startswith("tomli-w")]
    assert tomli, "tomli is not declared; config.toml is silently ignored on Python 3.10"
    assert "python_version < '3.11'" in tomli[0]

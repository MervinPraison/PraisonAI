"""``.env`` is discovered from the CWD, not the package location (#5820)."""

import os
import shutil

import pytest

from praisonai_code.cli.legacy import env_security

_KEY = "PRAISONAI_TEST_DOTENV_5820"


@pytest.fixture
def module_copy(tmp_path, monkeypatch):
    """Run a copy of env_security from a "checkout" dir that has its own .env."""
    import importlib.util

    checkout = tmp_path / "checkout"
    pkg = checkout / "pkg"
    pkg.mkdir(parents=True)
    (checkout / ".env").write_text(f"{_KEY}=from-package-dir\n")
    shutil.copy(env_security.__file__, pkg / "env_security_copy.py")
    spec = importlib.util.spec_from_file_location(
        "env_security_copy", pkg / "env_security_copy.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cwd = tmp_path / "work"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.delenv(_KEY, raising=False)
    yield mod, cwd
    os.environ.pop(_KEY, None)


def test_package_dir_env_not_loaded(module_copy):
    mod, _ = module_copy
    mod._load_env_once()
    assert _KEY not in os.environ


def test_cwd_env_loaded(module_copy):
    mod, cwd = module_copy
    (cwd / ".env").write_text(f"{_KEY}=from-cwd\n")
    mod._load_env_once()
    assert os.environ.get(_KEY) == "from-cwd"


def test_existing_env_not_overridden(module_copy, monkeypatch):
    mod, cwd = module_copy
    (cwd / ".env").write_text(f"{_KEY}=from-cwd\n")
    monkeypatch.setenv(_KEY, "preset")
    mod._load_env_once()
    assert os.environ[_KEY] == "preset"

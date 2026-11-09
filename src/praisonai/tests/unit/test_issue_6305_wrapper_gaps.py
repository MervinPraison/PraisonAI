"""Regression tests for issue #6305 wrapper security gaps."""

from pathlib import Path

import pytest


def test_checksum_covers_dotfiles(tmp_path: Path):
    from praisonai.templates.security import SecurityConfig, TemplateSecurity

    sec = TemplateSecurity(SecurityConfig())
    (tmp_path / "agents.yaml").write_text("a: 1")
    (tmp_path / ".env").write_text("X=1")
    before = sec.calculate_checksum(tmp_path)
    (tmp_path / ".env").write_text("X=2")
    assert sec.calculate_checksum(tmp_path) != before


def test_checksum_ignores_vcs_dirs(tmp_path: Path):
    from praisonai.templates.security import SecurityConfig, TemplateSecurity

    sec = TemplateSecurity(SecurityConfig())
    (tmp_path / "agents.yaml").write_text("a: 1")
    before = sec.calculate_checksum(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref")
    assert sec.calculate_checksum(tmp_path) == before


@pytest.mark.parametrize("name", ["uv.lock", "poetry.lock"])
def test_malformed_toml_lock_fails_closed(tmp_path: Path, name: str):
    from praisonai.recipe.security import (
        LockfileError,
        _parse_poetry_lock,
        _parse_uv_lock,
        audit_dependencies,
        validate_lockfile,
    )

    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    lock = lock_dir / name
    lock.write_text("this is [[ not toml")

    parser = _parse_uv_lock if name == "uv.lock" else _parse_poetry_lock
    with pytest.raises(LockfileError):
        parser(lock)

    report = audit_dependencies(tmp_path, check_vulnerabilities=False)
    assert report["passed"] is False
    assert any("scan failed" in w for w in report["warnings"])

    assert validate_lockfile(tmp_path)["valid"] is False


def test_valid_uv_lock_still_parses(tmp_path: Path):
    from praisonai.recipe.security import _parse_uv_lock

    lock = tmp_path / "uv.lock"
    lock.write_text('[[package]]\nname = "requests"\nversion = "2.31.0"\n')
    assert _parse_uv_lock(lock) == [{"name": "requests", "version": "2.31.0"}]


def test_template_tools_sources_local_paths_gated(tmp_path: Path, monkeypatch):
    from praisonai.cli.features.templates import _gate_template_tools_sources

    evil = tmp_path / "evil.py"
    evil.write_text("def tool(): pass\n")
    sources = [str(evil), "some_installed.module"]

    monkeypatch.delenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", raising=False)
    assert _gate_template_tools_sources(sources) == ["some_installed.module"]

    monkeypatch.setenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", "true")
    assert _gate_template_tools_sources(sources) == sources


def test_recipe_serve_cors_wildcard_disables_credentials():
    pytest.importorskip("starlette")
    from praisonai.recipe.serve import create_app

    app = create_app(config={"cors_origins": "*", "cors_credentials": True})
    cors = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert cors
    opts = getattr(cors[0], "kwargs", None) or getattr(cors[0], "options", {})
    assert opts["allow_credentials"] is False


@pytest.mark.parametrize("name", ["uv.lock", "poetry.lock"])
def test_root_level_malformed_lock_fails_closed(tmp_path: Path, name: str):
    from praisonai.recipe.security import audit_dependencies

    (tmp_path / name).write_text("this is [[ not toml")
    report = audit_dependencies(tmp_path, check_vulnerabilities=False)
    assert report["lockfile"].endswith(name)
    assert report["passed"] is False


@pytest.mark.parametrize("body", ["package = 42\n", 'package = "bad"\n', "package = [1, 2]\n"])
def test_malformed_package_shape_raises(tmp_path: Path, body: str):
    from praisonai.recipe.security import LockfileError, _parse_uv_lock

    lock = tmp_path / "uv.lock"
    lock.write_text(body)
    with pytest.raises(LockfileError):
        _parse_uv_lock(lock)


def test_registry_checksum_matches_security_checksum(tmp_path: Path):
    from praisonai.templates.registry import TemplateRegistry
    from praisonai.templates.security import SecurityConfig, TemplateSecurity

    (tmp_path / "agents.yaml").write_text("a: 1")
    (tmp_path / ".env").write_text("X=1")
    expected = TemplateSecurity(SecurityConfig()).calculate_checksum(tmp_path)
    assert TemplateRegistry._calculate_dir_checksum(None, tmp_path) == expected

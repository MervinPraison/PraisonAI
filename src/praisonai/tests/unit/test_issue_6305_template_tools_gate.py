"""Regression test for issue #6305: template tools_sources gate."""

from pathlib import Path


def test_template_tools_sources_local_paths_gated(tmp_path: Path, monkeypatch):
    from praisonai.cli.features.templates import _gate_template_tools_sources

    evil = tmp_path / "evil.py"
    evil.write_text("def tool(): pass\n")
    sources = [str(evil), "some_installed.module"]

    monkeypatch.delenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", raising=False)
    assert _gate_template_tools_sources(sources) == ["some_installed.module"]

    monkeypatch.setenv("PRAISONAI_ALLOW_TEMPLATE_TOOLS", "true")
    assert _gate_template_tools_sources(sources) == sources

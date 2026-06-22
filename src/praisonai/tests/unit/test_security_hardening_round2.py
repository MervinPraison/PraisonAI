"""Wrapper security hardening tests (round 2)."""

import pytest
from pathlib import Path


def test_run_stream_enforces_tool_policy(monkeypatch):
    from praisonai.recipe import core as recipe_core

    recipe_config = recipe_core.RecipeConfig(
        name="test",
        requires={"tools": ["shell.exec"]},
        tools={"deny": [], "allow": []},
    )

    monkeypatch.setattr(recipe_core, "_load_recipe", lambda *a, **k: recipe_config)
    monkeypatch.setattr(
        recipe_core,
        "_check_dependencies",
        lambda *a, **k: {"all_satisfied": True},
    )

    events = list(recipe_core.run_stream("demo", options={}))
    assert events[-1].event_type == "error"
    assert events[-1].data.get("code") == "policy_denied"


def test_artifact_store_rejects_outside_base(tmp_path):
    from praisonai.context.artifact_store import FileSystemArtifactStore
    from praisonaiagents.context.artifacts import ArtifactRef

    store = FileSystemArtifactStore(base_dir=str(tmp_path / "runs"))
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    ref = ArtifactRef(path=str(outside), summary="", size_bytes=0)
    with pytest.raises(FileNotFoundError, match="outside storage"):
        store.load(ref)


def test_storage_id_rejects_traversal():
    from praisonai.context._storage_path import safe_storage_id

    with pytest.raises(ValueError):
        safe_storage_id("../etc", "run_id")


def test_template_cache_rejects_traversal():
    from praisonai.templates.cache import TemplateCache

    with pytest.raises(ValueError):
        TemplateCache._safe_segment("../evil")

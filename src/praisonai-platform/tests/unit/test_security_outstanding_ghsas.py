"""Platform GHSA regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_project_patch_has_owner_guard():
    """GHSA-c78w: project PATCH must call require_delete_permission."""
    source = Path(__file__).resolve().parents[2] / "praisonai_platform/api/routes/projects.py"
    text = source.read_text()
    patch_block = text.split("async def update_project", 1)[1].split("async def delete_project", 1)[0]
    assert "require_delete_permission" in patch_block


def test_label_patch_requires_admin_guard():
    """GHSA-xxgv: label PATCH must require workspace admin."""
    source = Path(__file__).resolve().parents[2] / "praisonai_platform/api/routes/labels.py"
    text = source.read_text()
    patch_block = text.split("async def update_label", 1)[1].split("async def delete_label", 1)[0]
    assert "require_workspace_admin" in patch_block


def test_dependency_delete_checks_both_issues():
    """GHSA-mxmx: dependency delete must authorise both linked issues."""
    source = Path(__file__).resolve().parents[2] / "praisonai_platform/api/routes/dependencies.py"
    text = source.read_text()
    delete_block = text.split("async def delete_dependency", 1)[1]
    assert delete_block.count("require_delete_permission") >= 2
    assert "other_issue" in delete_block


@pytest.mark.asyncio
async def test_project_patch_requires_owner_or_admin():
    """GHSA-c78w: project PATCH must match DELETE permission model."""
    pytest.importorskip("fastapi")
    from unittest.mock import AsyncMock, MagicMock, patch

    from praisonai_platform.api.routes import projects as routes

    user = MagicMock()
    user.id = "member-1"
    session = AsyncMock()
    project = MagicMock()
    project.lead_id = "owner-1"

    with patch.object(routes.ProjectService, "get", AsyncMock(return_value=project)):
        with patch.object(routes, "require_delete_permission", AsyncMock(side_effect=Exception("403"))) as guard:
            with pytest.raises(Exception, match="403"):
                await routes.update_project(
                    "ws-1",
                    "proj-1",
                    MagicMock(),
                    user=user,
                    session=session,
                )
            guard.assert_awaited_once()


@pytest.mark.asyncio
async def test_label_patch_requires_admin():
    """GHSA-xxgv: shared label PATCH requires admin/owner."""
    pytest.importorskip("fastapi")
    from unittest.mock import AsyncMock, MagicMock, patch

    from praisonai_platform.api.routes import labels as routes

    label = MagicMock()
    label.workspace_id = "ws-1"

    with patch.object(routes.LabelService, "get", AsyncMock(return_value=label)):
        with patch.object(routes, "require_workspace_admin", AsyncMock(side_effect=Exception("403"))) as guard:
            with pytest.raises(Exception, match="403"):
                await routes.update_label(
                    "ws-1",
                    "label-1",
                    MagicMock(),
                    user=MagicMock(),
                    session=AsyncMock(),
                )
            guard.assert_awaited_once()

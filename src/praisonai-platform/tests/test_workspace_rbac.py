"""Workspace member RBAC and cross-workspace IDOR guards."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from praisonai_platform.api.deps import ensure_resource_in_workspace


def test_ensure_resource_in_workspace_rejects_mismatch():
    with pytest.raises(HTTPException) as exc:
        ensure_resource_in_workspace("ws-a", "ws-b", label="Issue")
    assert exc.value.status_code == 404


def test_ensure_resource_in_workspace_allows_match():
    ensure_resource_in_workspace("ws-a", "ws-a", label="Issue")

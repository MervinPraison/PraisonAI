"""Cross-workspace IDOR guards for platform resources."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from praisonai_platform.api.deps import ensure_resource_in_workspace


def test_project_workspace_mismatch():
    with pytest.raises(HTTPException) as exc:
        ensure_resource_in_workspace("ws-other", "ws-mine", label="Project")
    assert exc.value.status_code == 404


def test_label_workspace_mismatch():
    with pytest.raises(HTTPException) as exc:
        ensure_resource_in_workspace("ws-other", "ws-mine", label="Label")
    assert exc.value.status_code == 404

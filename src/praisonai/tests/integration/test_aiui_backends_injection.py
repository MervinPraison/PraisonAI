"""Cross-repo test — wrapper build_host_app + aiui backend injection."""

from __future__ import annotations

import pytest

pytest.importorskip("praisonaiui")


def test_build_host_injects_backends():
    import praisonaiui.backends as backends
    from praisonai.integration.host_app import build_host_app

    backends.clear_backends()
    app = build_host_app(pages=["chat"])
    assert app is not None
    registered = backends.list_backends()
    assert "hooks" in registered
    assert "workflows" in registered

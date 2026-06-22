"""Pattern C gateway parity — datastore + backends after bootstrap."""

from __future__ import annotations

import pytest

pytest.importorskip("praisonaiui")


def test_gateway_start_wires_datastore(monkeypatch):
    monkeypatch.delenv("PRAISONAI_HOST_LEGACY", raising=False)
    import praisonaiui.backends as backends
    import praisonaiui.server as srv
    from praisonai.integration import host_app

    host_app.reset_configuration()
    backends.clear_backends()
    srv._provider = None

    host_app.configure_host(pages=["chat"])
    assert srv.get_datastore() is not None
    assert "hooks" in backends.list_backends() or host_app.is_configured()

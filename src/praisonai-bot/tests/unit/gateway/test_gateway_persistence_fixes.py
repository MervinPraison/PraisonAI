"""Regression tests for gateway session persistence correctness."""

import tempfile
from pathlib import Path

import pytest

from praisonai_bot.gateway.server import GatewayMessage, GatewaySession, WebSocketGateway
from praisonaiagents.gateway import GatewayConfig, SessionConfig
from praisonaiagents.session.store import DefaultSessionStore


def _make_gateway(tmp_path: Path) -> WebSocketGateway:
    store = DefaultSessionStore(session_dir=str(tmp_path))
    config = GatewayConfig(
        session_config=SessionConfig(persist=True, persist_path=str(tmp_path)),
    )
    return WebSocketGateway(config=config, session_store=store)


class TestGatewaySessionResume:
    """Resume must restore the latest persisted snapshot, not the initial empty one."""

    def test_resume_uses_latest_session_data_snapshot(self, tmp_path):
        gw = _make_gateway(tmp_path)
        session_id = "sess-resume-1"

        session = gw.create_session("agent-1", "client-1", session_id)
        session.add_message(
            GatewayMessage(
                content="Hello from user",
                sender_id="user",
                session_id=session_id,
            )
        )
        gw.close_session(session_id)

        resumed = gw.create_session("agent-1", "client-2", session_id)
        messages = resumed.get_messages()

        assert len(messages) == 1
        assert messages[0].content == "Hello from user"


class TestGatewayStopPersistence:
    """Graceful shutdown must persist active sessions."""

    @pytest.mark.asyncio
    async def test_stop_persists_active_sessions(self, tmp_path):
        gw = _make_gateway(tmp_path)
        session_id = "sess-stop-1"

        session = gw.create_session("agent-1", "client-1", session_id)
        session.add_message(
            GatewayMessage(
                content="Shutdown test message",
                sender_id="user",
                session_id=session_id,
            )
        )

        # Mark gateway as running so stop() will execute session persistence
        gw._is_running = True
        await gw.stop()

        store = gw._session_store
        assert store is not None
        assert store.session_exists(session_id)

        # Create a new gateway instance to verify persistence
        gw2 = _make_gateway(tmp_path)
        resumed = gw2.create_session("agent-1", "client-2", session_id)
        messages = resumed.get_messages()

        assert len(messages) == 1
        assert messages[0].content == "Shutdown test message"


class TestDurableDeliveryImport:
    """_delivery.py must be importable after accidental removal."""

    def test_durable_delivery_import(self):
        from praisonai_bot.bots import DurableDelivery, deliver_chunked

        assert DurableDelivery is not None
        assert deliver_chunked is not None

    def test_durable_adapter_mixin_import(self):
        from praisonai_bot.bots import DurableAdapterMixin

        assert DurableAdapterMixin is not None

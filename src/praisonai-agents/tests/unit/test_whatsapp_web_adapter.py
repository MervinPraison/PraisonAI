"""
Unit tests for WhatsApp Web adapter (_whatsapp_web_adapter.py).

Tests the neonize adapter isolation layer with mocked neonize client.
All tests are deterministic — no external WhatsApp calls.
"""

import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the wrapper package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "praisonai"))


# ── Adapter import ────────────────────────────────────────────────

class TestAdapterImport:
    """Test that the adapter module can be imported without neonize."""

    def test_import_adapter_module(self):
        """Adapter module imports without neonize installed."""
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        assert WhatsAppWebAdapter is not None

    def test_default_creds_dir(self):
        """Default creds dir is ~/.praisonai/whatsapp."""
        from praisonai.bots._whatsapp_web_adapter import DEFAULT_CREDS_DIR
        assert ".praisonai" in DEFAULT_CREDS_DIR
        assert "whatsapp" in DEFAULT_CREDS_DIR


# ── Adapter construction ──────────────────────────────────────────

class TestAdapterConstruction:
    """Test WhatsAppWebAdapter initialization."""

    def test_default_construction(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        assert adapter.is_connected is False
        assert adapter.self_jid is None
        assert ".praisonai" in adapter.creds_dir

    def test_custom_creds_dir(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter(creds_dir="/tmp/test-wa-creds")
        assert adapter.creds_dir == "/tmp/test-wa-creds"

    def test_custom_bot_name(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter(bot_name="my_bot")
        assert adapter._bot_name == "my_bot"

    def test_env_var_creds_dir(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        with patch.dict(os.environ, {"WHATSAPP_CREDS_DIR": "/tmp/env-creds"}):
            adapter = WhatsAppWebAdapter()
            assert adapter.creds_dir == "/tmp/env-creds"

    def test_callbacks_stored(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        on_msg = MagicMock()
        on_qr = MagicMock()
        on_conn = MagicMock()
        on_disc = MagicMock()
        adapter = WhatsAppWebAdapter(
            on_message=on_msg,
            on_qr=on_qr,
            on_connected=on_conn,
            on_disconnected=on_disc,
        )
        assert adapter._on_message is on_msg
        assert adapter._on_qr is on_qr
        assert adapter._on_connected is on_conn
        assert adapter._on_disconnected is on_disc


# ── Credential management ─────────────────────────────────────────

class TestCredentialManagement:
    """Test credential path and session detection."""

    def test_ensure_creds_dir_creates_directory(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        with tempfile.TemporaryDirectory() as tmpdir:
            creds_path = os.path.join(tmpdir, "subdir", "wa")
            adapter = WhatsAppWebAdapter(creds_dir=creds_path)
            adapter._ensure_creds_dir()
            assert os.path.isdir(creds_path)

    def test_get_db_path(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = WhatsAppWebAdapter(creds_dir=tmpdir, bot_name="testbot")
            db_path = adapter._get_db_path()
            assert db_path.endswith("testbot.db")
            assert tmpdir in db_path

    def test_has_saved_session_false_when_no_db(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = WhatsAppWebAdapter(creds_dir=tmpdir)
            assert adapter.has_saved_session() is False

    def test_has_saved_session_true_when_db_exists(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = WhatsAppWebAdapter(creds_dir=tmpdir, bot_name="test")
            # Create a fake db file
            db_path = os.path.join(tmpdir, "test.db")
            with open(db_path, "w") as f:
                f.write("fake-db-content")
            assert adapter.has_saved_session() is True

    @pytest.mark.asyncio
    async def test_logout_removes_db_files(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = WhatsAppWebAdapter(creds_dir=tmpdir, bot_name="test")
            # Create fake db files
            for suffix in [".db", ".db-wal", ".db-shm"]:
                path = os.path.join(tmpdir, f"test{suffix}")
                with open(path, "w") as f:
                    f.write("x")
            assert adapter.has_saved_session() is True
            await adapter.logout()
            assert adapter.has_saved_session() is False
            assert not os.path.exists(os.path.join(tmpdir, "test.db-wal"))
            assert not os.path.exists(os.path.join(tmpdir, "test.db-shm"))


# ── JID normalization ─────────────────────────────────────────────

class TestJIDNormalization:
    """Test phone number to JID conversion."""

    def test_already_jid(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        assert WhatsAppWebAdapter._normalize_jid("1234@s.whatsapp.net") == "1234@s.whatsapp.net"

    def test_phone_number(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        assert WhatsAppWebAdapter._normalize_jid("15551234567") == "15551234567@s.whatsapp.net"

    def test_phone_with_plus(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        assert WhatsAppWebAdapter._normalize_jid("+15551234567") == "15551234567@s.whatsapp.net"

    def test_group_jid_passthrough(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        assert WhatsAppWebAdapter._normalize_jid("123456@g.us") == "123456@g.us"

    def test_phone_with_spaces_and_dashes(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        assert WhatsAppWebAdapter._normalize_jid("+1 555-123-4567") == "15551234567@s.whatsapp.net"


# ── Connect / Disconnect ──────────────────────────────────────────

class TestConnectDisconnect:
    """Test connect and disconnect lifecycle (mocked neonize)."""

    @pytest.mark.asyncio
    async def test_connect_raises_without_neonize(self):
        """connect() raises ImportError when neonize is not installed."""
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter(creds_dir="/tmp/test-no-neonize")
        
        with patch.dict(sys.modules, {
            "neonize": None,
            "neonize.aioze": None,
            "neonize.aioze.client": None,
            "neonize.aioze.events": None,
        }):
            with pytest.raises(ImportError, match="neonize"):
                await adapter.connect()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """disconnect() is safe to call when not connected."""
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        await adapter.disconnect()
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_calls_client_disconnect(self):
        """disconnect() calls client.disconnect() if client exists."""
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        mock_client = AsyncMock()
        adapter._client = mock_client
        adapter._is_connected = True

        await adapter.disconnect()
        mock_client.disconnect.assert_called_once()
        assert adapter.is_connected is False
        assert adapter._client is None


# ── Send message ──────────────────────────────────────────────────

class TestSendMessage:
    """Test send_message with mocked client."""

    @pytest.mark.asyncio
    async def test_send_when_not_connected_returns_none(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        result = await adapter.send_message("1234@s.whatsapp.net", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_reaction_when_not_connected(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        # Should not raise
        await adapter.send_reaction("1234@s.whatsapp.net", "msg123", "👍")

    @pytest.mark.asyncio
    async def test_mark_as_read_when_not_connected(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        # Should not raise
        await adapter.mark_as_read("1234@s.whatsapp.net", "msg123")


# ── QR code display ───────────────────────────────────────────────

class TestQRCodeDisplay:
    """Test QR code terminal display."""

    def test_print_qr_with_qrcode_lib(self):
        """Uses qrcode library when available."""
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        mock_qr = MagicMock()
        mock_qr_module = MagicMock()
        mock_qr_module.QRCode.return_value = mock_qr

        with patch.dict(sys.modules, {"qrcode": mock_qr_module}):
            WhatsAppWebAdapter._print_qr_terminal("test-qr-data")
            mock_qr_module.QRCode.assert_called_once()
            mock_qr.add_data.assert_called_once_with("test-qr-data")

    def test_print_qr_fallback_without_lib(self, capsys):
        """Falls back to text output when qrcode not installed."""
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        with patch.dict(sys.modules, {"qrcode": None}):
            # Force ImportError
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
            def mock_import(name, *args, **kwargs):
                if name == "qrcode":
                    raise ImportError("No module named 'qrcode'")
                return original_import(name, *args, **kwargs)
            
            with patch("builtins.__import__", side_effect=mock_import):
                WhatsAppWebAdapter._print_qr_terminal("test-qr-data-fallback")
                captured = capsys.readouterr()
                assert "QR" in captured.out or "qrcode" in captured.out.lower()


# ── Safe callback ─────────────────────────────────────────────────

class TestSafeCallback:
    """Test the _safe_callback helper."""

    @pytest.mark.asyncio
    async def test_sync_callback(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        called = []
        def cb(x):
            called.append(x)
        await adapter._safe_callback(cb, "test")
        assert called == ["test"]

    @pytest.mark.asyncio
    async def test_async_callback(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        called = []
        async def cb(x):
            called.append(x)
        await adapter._safe_callback(cb, "async-test")
        assert called == ["async-test"]

    @pytest.mark.asyncio
    async def test_callback_error_does_not_raise(self):
        from praisonai.bots._whatsapp_web_adapter import WhatsAppWebAdapter
        adapter = WhatsAppWebAdapter()
        def cb():
            raise ValueError("boom")
        # Should not raise
        await adapter._safe_callback(cb)

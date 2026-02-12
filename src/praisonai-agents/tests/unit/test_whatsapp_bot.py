"""Unit tests for WhatsApp Bot implementation."""

import sys
import os
import asyncio
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai'))

import pytest


class MockAgent:
    def __init__(self, name="test-agent", llm="gpt-4o-mini"):
        self.name = name
        self.llm = llm
        self.chat_history = []

    def chat(self, prompt):
        return f"Reply: {prompt}"


# ── Bot Creation ────────────────────────────────────────────────

class TestWhatsAppBotCreation:
    """Test WhatsAppBot instantiation and configuration."""

    def _make_bot(self, **kwargs):
        from praisonai.bots.whatsapp import WhatsAppBot
        defaults = dict(
            token="fake-access-token",
            phone_number_id="123456789",
            agent=MockAgent(),
            verify_token="test-verify",
        )
        defaults.update(kwargs)
        return WhatsAppBot(**defaults)

    def test_create_basic(self):
        bot = self._make_bot()
        assert bot._token == "fake-access-token"
        assert bot._phone_number_id == "123456789"
        assert bot._verify_token == "test-verify"
        assert bot._webhook_port == 8080

    def test_create_custom_port(self):
        bot = self._make_bot(webhook_port=9090)
        assert bot._webhook_port == 9090

    def test_create_custom_webhook_path(self):
        bot = self._make_bot(webhook_path="/custom/webhook")
        assert bot._webhook_path == "/custom/webhook"

    def test_platform_property(self):
        bot = self._make_bot()
        assert bot.platform == "whatsapp"

    def test_is_running_initial(self):
        bot = self._make_bot()
        assert bot.is_running is False

    def test_bot_user_initial(self):
        bot = self._make_bot()
        assert bot.bot_user is None

    def test_set_agent(self):
        bot = self._make_bot()
        new_agent = MockAgent(name="new-agent")
        bot.set_agent(new_agent)
        assert bot.get_agent().name == "new-agent"

    def test_get_agent(self):
        agent = MockAgent(name="my-agent")
        bot = self._make_bot(agent=agent)
        assert bot.get_agent() is agent

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "env-phone-id")
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "env-verify")
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(token="test-token", agent=MockAgent())
        assert bot._phone_number_id == "env-phone-id"
        assert bot._verify_token == "env-verify"


# ── Commands ────────────────────────────────────────────────────

class TestWhatsAppBotCommands:
    """Test built-in command registration."""

    def _make_bot(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        return WhatsAppBot(
            token="fake-token",
            phone_number_id="123",
            agent=MockAgent(),
            verify_token="test",
        )

    def test_builtin_commands_registered(self):
        bot = self._make_bot()
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "status" in names
        assert "new" in names
        assert "help" in names

    def test_register_custom_command(self):
        bot = self._make_bot()
        bot.register_command("ping", lambda m: "pong", description="Ping test")
        commands = bot.list_commands()
        names = [c.name for c in commands]
        assert "ping" in names

    def test_on_command_decorator(self):
        bot = self._make_bot()

        @bot.on_command("test")
        async def test_cmd(msg):
            return "test response"

        assert "test" in bot._command_handlers

    def test_on_message_handler(self):
        bot = self._make_bot()

        @bot.on_message
        async def handle(msg):
            pass

        assert len(bot._message_handlers) == 1


# ── Webhook Verification ────────────────────────────────────────

class TestWebhookVerification:
    """Test Meta webhook verification endpoint."""

    def _make_bot(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        return WhatsAppBot(
            token="fake-token",
            phone_number_id="123",
            agent=MockAgent(),
            verify_token="my-secret-token",
        )

    @pytest.mark.asyncio
    async def test_verification_success(self):
        bot = self._make_bot()

        class FakeRequest:
            query = {
                "hub.mode": "subscribe",
                "hub.verify_token": "my-secret-token",
                "hub.challenge": "challenge123",
            }

        resp = await bot._handle_verification(FakeRequest())
        assert resp.status == 200
        assert resp.text == "challenge123"

    @pytest.mark.asyncio
    async def test_verification_wrong_token(self):
        bot = self._make_bot()

        class FakeRequest:
            query = {
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "challenge123",
            }

        resp = await bot._handle_verification(FakeRequest())
        assert resp.status == 403

    @pytest.mark.asyncio
    async def test_verification_wrong_mode(self):
        bot = self._make_bot()

        class FakeRequest:
            query = {
                "hub.mode": "unsubscribe",
                "hub.verify_token": "my-secret-token",
                "hub.challenge": "challenge123",
            }

        resp = await bot._handle_verification(FakeRequest())
        assert resp.status == 403


# ── Health Endpoint ─────────────────────────────────────────────

class TestHealthEndpoint:
    """Test health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_not_running(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(
            token="t", phone_number_id="p", agent=MockAgent(), verify_token="v"
        )
        resp = await bot._handle_health(None)
        data = json.loads(resp.body)
        assert data["platform"] == "whatsapp"
        assert data["is_running"] is False

    @pytest.mark.asyncio
    async def test_health_running(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(
            token="t", phone_number_id="p", agent=MockAgent(), verify_token="v"
        )
        bot._is_running = True
        bot._started_at = time.time() - 60
        resp = await bot._handle_health(None)
        data = json.loads(resp.body)
        assert data["is_running"] is True
        assert data["uptime"] >= 59


# ── Signature Verification ──────────────────────────────────────

class TestSignatureVerification:
    """Test webhook signature verification."""

    def _make_bot(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        return WhatsAppBot(
            token="t",
            phone_number_id="p",
            agent=MockAgent(),
            verify_token="v",
            app_secret="my-app-secret",
        )

    def test_valid_signature(self):
        import hmac
        import hashlib
        bot = self._make_bot()
        body = b'{"test": "data"}'
        sig = "sha256=" + hmac.new(
            b"my-app-secret", body, hashlib.sha256
        ).hexdigest()
        assert bot._verify_signature(body, sig) is True

    def test_invalid_signature(self):
        bot = self._make_bot()
        assert bot._verify_signature(b"body", "sha256=invalid") is False

    def test_missing_prefix(self):
        bot = self._make_bot()
        assert bot._verify_signature(b"body", "invalid") is False


# ── Message Processing ──────────────────────────────────────────

class TestMessageProcessing:
    """Test incoming message processing."""

    def _make_bot(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        return WhatsAppBot(
            token="t", phone_number_id="p", agent=MockAgent(), verify_token="v"
        )

    @pytest.mark.asyncio
    async def test_process_text_message(self):
        bot = self._make_bot()
        sent_messages = []

        async def mock_send(to, content, **kwargs):
            sent_messages.append((to, content))
            from praisonaiagents.bots import BotMessage
            return BotMessage(content=content)
        bot.send_message = mock_send

        data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Test User"}}],
                        "messages": [{
                            "from": "1234567890",
                            "id": "msg-1",
                            "type": "text",
                            "text": {"body": "Hello bot"},
                            "timestamp": str(int(time.time())),
                        }],
                    }
                }]
            }]
        }

        await bot._process_webhook_data(data)
        # Give async task time to complete
        await asyncio.sleep(0.1)
        assert len(sent_messages) == 1
        assert sent_messages[0][0] == "1234567890"
        assert "Reply:" in sent_messages[0][1]

    @pytest.mark.asyncio
    async def test_process_command_message(self):
        bot = self._make_bot()
        sent_messages = []

        async def mock_send(to, content, **kwargs):
            sent_messages.append((to, content))
            from praisonaiagents.bots import BotMessage
            return BotMessage(content=content)
        bot.send_message = mock_send

        data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Test User"}}],
                        "messages": [{
                            "from": "1234567890",
                            "id": "msg-2",
                            "type": "text",
                            "text": {"body": "/help"},
                            "timestamp": str(int(time.time())),
                        }],
                    }
                }]
            }]
        }

        await bot._process_webhook_data(data)
        await asyncio.sleep(0.1)
        assert len(sent_messages) == 1
        assert "Available Commands" in sent_messages[0][1]

    @pytest.mark.asyncio
    async def test_process_location_message(self):
        bot = self._make_bot()
        sent_messages = []

        async def mock_send(to, content, **kwargs):
            sent_messages.append((to, content))
            from praisonaiagents.bots import BotMessage
            return BotMessage(content=content)
        bot.send_message = mock_send

        data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Test"}}],
                        "messages": [{
                            "from": "111",
                            "id": "msg-3",
                            "type": "location",
                            "location": {"latitude": 37.7749, "longitude": -122.4194},
                            "timestamp": str(int(time.time())),
                        }],
                    }
                }]
            }]
        }

        await bot._process_webhook_data(data)
        await asyncio.sleep(0.1)
        assert len(sent_messages) == 1
        assert "Location:" in sent_messages[0][1] or "Reply:" in sent_messages[0][1]

    @pytest.mark.asyncio
    async def test_process_empty_entry(self):
        """Empty entry should not crash."""
        bot = self._make_bot()
        await bot._process_webhook_data({"entry": []})

    @pytest.mark.asyncio
    async def test_process_no_messages(self):
        """Entry with no messages should not crash."""
        bot = self._make_bot()
        await bot._process_webhook_data({
            "entry": [{"changes": [{"value": {}}]}]
        })


# ── Session Management ──────────────────────────────────────────

class TestWhatsAppSession:
    """Test session isolation."""

    @pytest.mark.asyncio
    async def test_new_command_resets_session(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(
            token="t", phone_number_id="p", agent=MockAgent(), verify_token="v"
        )
        # Manually add a session entry
        bot._session_mgr._histories["user1"] = [{"role": "user", "content": "hi"}]
        assert bot._session_mgr.active_sessions == 1

        # Invoke /new handler
        handler = bot._command_handlers["new"]
        from praisonaiagents.bots import BotMessage, BotUser
        msg = BotMessage(
            sender=BotUser(user_id="user1"),
            content="/new",
        )
        result = await handler(msg)
        assert "reset" in result.lower()
        assert bot._session_mgr.active_sessions == 0


# ── Convenience Methods ─────────────────────────────────────────

class TestConvenienceMethods:
    """Test edit_message, delete_message, send_typing, etc."""

    def _make_bot(self):
        from praisonai.bots.whatsapp import WhatsAppBot
        return WhatsAppBot(
            token="t", phone_number_id="p", agent=MockAgent(), verify_token="v"
        )

    @pytest.mark.asyncio
    async def test_delete_returns_false(self):
        bot = self._make_bot()
        assert await bot.delete_message("ch", "msg") is False

    @pytest.mark.asyncio
    async def test_send_typing_noop(self):
        bot = self._make_bot()
        await bot.send_typing("ch")  # should not raise

    @pytest.mark.asyncio
    async def test_get_user(self):
        bot = self._make_bot()
        user = await bot.get_user("12345")
        assert user.user_id == "12345"

    @pytest.mark.asyncio
    async def test_get_channel(self):
        bot = self._make_bot()
        ch = await bot.get_channel("12345")
        assert ch.channel_id == "12345"
        assert ch.channel_type == "dm"

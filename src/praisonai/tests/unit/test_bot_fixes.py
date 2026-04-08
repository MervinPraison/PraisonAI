"""
Tests for bot framework fixes.

Tests cover:
1. WhatsApp health() uses correct session manager attribute
2. asyncio.get_running_loop() usage (not deprecated get_event_loop)
3. Rate limiter functionality
4. Background task tracking
5. Deprecation warning for legacy approval
"""

import pytest
import time


class TestRateLimiter:
    """Tests for the RateLimiter utility."""

    def test_rate_limiter_import(self):
        """Test that RateLimiter can be imported."""
        from praisonai.bots._rate_limit import RateLimiter, RateLimitConfig
        assert RateLimiter is not None
        assert RateLimitConfig is not None

    def test_rate_limiter_for_platform(self):
        """Test platform-specific rate limiter creation."""
        from praisonai.bots._rate_limit import RateLimiter, PLATFORM_LIMITS
        
        for platform in ["telegram", "discord", "slack", "whatsapp"]:
            limiter = RateLimiter.for_platform(platform)
            assert limiter is not None
            assert limiter._config == PLATFORM_LIMITS[platform]

    def test_rate_limiter_unknown_platform_uses_defaults(self):
        """Test that unknown platform uses default config."""
        from praisonai.bots._rate_limit import RateLimiter, RateLimitConfig
        
        limiter = RateLimiter.for_platform("unknown_platform")
        default = RateLimitConfig()
        assert limiter._config.messages_per_second == default.messages_per_second

    @pytest.mark.asyncio
    async def test_rate_limiter_acquire_no_wait_with_tokens(self):
        """Test that acquire doesn't wait when tokens available."""
        from praisonai.bots._rate_limit import RateLimiter, RateLimitConfig
        
        config = RateLimitConfig(messages_per_second=100, burst_size=10)
        limiter = RateLimiter(config)
        
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        
        # Should be nearly instant
        assert elapsed < 0.1

    @pytest.mark.asyncio
    @pytest.mark.allow_sleep
    async def test_rate_limiter_acquire_waits_when_exhausted(self):
        """Test that acquire waits when tokens exhausted."""
        from praisonai.bots._rate_limit import RateLimiter, RateLimitConfig
        
        config = RateLimitConfig(messages_per_second=10, burst_size=1)
        limiter = RateLimiter(config)
        
        # Exhaust the single token
        await limiter.acquire()
        
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        
        # Should wait ~0.1s for token refill (1/10 = 0.1s)
        assert elapsed >= 0.05  # Allow some tolerance

    @pytest.mark.asyncio
    @pytest.mark.allow_sleep
    async def test_rate_limiter_per_channel_delay(self):
        """Test per-channel delay enforcement."""
        from praisonai.bots._rate_limit import RateLimiter, RateLimitConfig
        
        config = RateLimitConfig(
            messages_per_second=100,
            per_channel_delay=0.1,
            burst_size=10
        )
        limiter = RateLimiter(config)
        
        channel = "test_channel"
        
        # First message - no delay
        await limiter.acquire(channel)
        
        # Second message to same channel - should delay
        start = time.monotonic()
        await limiter.acquire(channel)
        elapsed = time.monotonic() - start
        
        assert elapsed >= 0.05  # Allow tolerance

    def test_rate_limiter_reset(self):
        """Test rate limiter reset."""
        from praisonai.bots._rate_limit import RateLimiter, RateLimitConfig
        
        config = RateLimitConfig(burst_size=5)
        limiter = RateLimiter(config)
        limiter._tokens = 0
        limiter._channel_last_send["test"] = time.monotonic()
        
        limiter.reset()
        
        assert limiter._tokens == 5.0
        assert len(limiter._channel_last_send) == 0


class TestAsyncioGetRunningLoop:
    """Tests to verify get_running_loop is used instead of deprecated get_event_loop."""

    def test_session_manager_uses_get_running_loop(self):
        """Verify _session.py uses get_running_loop."""
        import inspect
        from praisonai.bots._session import BotSessionManager
        
        source = inspect.getsource(BotSessionManager)
        assert "get_running_loop" in source
        assert "get_event_loop()" not in source

    def test_approval_uses_get_running_loop(self):
        """Verify _approval.py uses get_running_loop."""
        # Import will trigger deprecation warning, that's expected
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from praisonai.bots._approval import BotApprovalBackend
        
        import inspect
        source = inspect.getsource(BotApprovalBackend)
        assert "get_running_loop" in source


class TestWhatsAppSessionManagerAttribute:
    """Tests for WhatsApp bot session manager attribute fix."""

    def test_whatsapp_health_uses_session_mgr(self):
        """Verify WhatsApp health() uses _session_mgr not _session."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.health)
        # Should use _session_mgr
        assert "_session_mgr" in source
        # Should NOT use bare _session (except as part of _session_mgr)
        # Count occurrences
        session_mgr_count = source.count("_session_mgr")
        bare_session_count = source.count("self._session") - source.count("self._session_mgr")
        assert bare_session_count == 0, "health() should not use self._session"
        assert session_mgr_count > 0, "health() should use self._session_mgr"


class TestWhatsAppHttpSession:
    """Tests for WhatsApp shared HTTP session."""

    def test_whatsapp_has_http_session_attribute(self):
        """Verify WhatsApp bot has _http_session attribute."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.__init__)
        assert "_http_session" in source

    def test_whatsapp_creates_session_on_start(self):
        """Verify WhatsApp creates ClientSession on start."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot._start_cloud_mode)
        assert "self._http_session = aiohttp.ClientSession" in source

    def test_whatsapp_closes_session_on_stop(self):
        """Verify WhatsApp closes ClientSession on stop."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.stop)
        assert "_http_session.close()" in source


class TestWhatsAppBackgroundTasks:
    """Tests for WhatsApp background task tracking."""

    def test_whatsapp_has_background_tasks_set(self):
        """Verify WhatsApp bot has _background_tasks set."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.__init__)
        assert "_background_tasks" in source

    def test_whatsapp_tracks_webhook_tasks(self):
        """Verify webhook processing tasks are tracked."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot._handle_webhook)
        assert "self._background_tasks.add(task)" in source
        assert "add_done_callback" in source

    def test_whatsapp_cancels_tasks_on_stop(self):
        """Verify background tasks are cancelled on stop."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.stop)
        assert "task.cancel()" in source or "for task in self._background_tasks" in source


class TestLegacyApprovalDeprecation:
    """Tests for legacy approval deprecation warning."""

    def test_legacy_approval_emits_deprecation_warning(self):
        """Verify importing _approval.py emits DeprecationWarning."""
        import warnings
        import sys
        import importlib
        
        # Remove from cache to force re-import
        if 'praisonai.bots._approval' in sys.modules:
            del sys.modules['praisonai.bots._approval']
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Use importlib to avoid lint warning about unused import
            importlib.import_module('praisonai.bots._approval')
            
            # Check that a DeprecationWarning was raised
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1
            assert "deprecated" in str(deprecation_warnings[0].message).lower()


class TestAckReactorIntegration:
    """Tests for AckReactor integration across adapters."""

    def test_discord_has_ack_reactor(self):
        """Verify Discord adapter has AckReactor."""
        import inspect
        from praisonai.bots.discord import DiscordBot
        
        source = inspect.getsource(DiscordBot.__init__)
        assert "_ack" in source
        assert "AckReactor" in source

    def test_discord_uses_ack_in_message_handling(self):
        """Verify Discord uses AckReactor in message handling."""
        import inspect
        from praisonai.bots.discord import DiscordBot
        
        # Get the start method source which contains on_message
        source = inspect.getsource(DiscordBot.start)
        assert "self._ack.enabled" in source
        assert "add_reaction" in source
        assert "self._ack.done" in source

    def test_slack_has_ack_reactor(self):
        """Verify Slack adapter has AckReactor."""
        import inspect
        from praisonai.bots.slack import SlackBot
        
        source = inspect.getsource(SlackBot.__init__)
        assert "_ack" in source
        assert "AckReactor" in source

    def test_slack_uses_ack_in_message_handling(self):
        """Verify Slack uses AckReactor in message handling."""
        import inspect
        from praisonai.bots.slack import SlackBot
        
        source = inspect.getsource(SlackBot.start)
        assert "self._ack.enabled" in source
        assert "reactions_add" in source
        assert "self._ack.done" in source

    def test_whatsapp_has_ack_reactor(self):
        """Verify WhatsApp adapter has AckReactor."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.__init__)
        assert "_ack" in source
        assert "AckReactor" in source

    def test_whatsapp_uses_ack_in_message_handling(self):
        """Verify WhatsApp uses AckReactor in message handling."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot._handle_incoming_message)
        assert "self._ack.enabled" in source
        assert "send_reaction" in source
        assert "self._ack.done" in source


class TestWhatsAppRateLimiterIntegration:
    """Tests for WhatsApp rate limiter integration."""

    def test_whatsapp_has_rate_limiter(self):
        """Verify WhatsApp adapter has rate limiter."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.__init__)
        assert "_rate_limiter" in source
        assert "RateLimiter.for_platform" in source

    def test_whatsapp_send_message_uses_rate_limiter(self):
        """Verify WhatsApp send_message uses rate limiter."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.send_message)
        assert "self._rate_limiter.acquire" in source

    def test_whatsapp_send_template_uses_rate_limiter(self):
        """Verify WhatsApp send_template uses rate limiter."""
        import inspect
        from praisonai.bots.whatsapp import WhatsAppBot
        
        source = inspect.getsource(WhatsAppBot.send_template)
        assert "self._rate_limiter.acquire" in source


class TestPlatformLimits:
    """Tests for platform rate limit configurations."""

    def test_telegram_limits(self):
        """Test Telegram rate limits are configured correctly."""
        from praisonai.bots._rate_limit import PLATFORM_LIMITS
        
        telegram = PLATFORM_LIMITS["telegram"]
        assert telegram.messages_per_second >= 20  # ~30 per Telegram docs
        assert telegram.burst_size >= 20

    def test_discord_limits(self):
        """Test Discord rate limits are configured correctly."""
        from praisonai.bots._rate_limit import PLATFORM_LIMITS
        
        discord = PLATFORM_LIMITS["discord"]
        assert discord.messages_per_second <= 2  # 5 per 5 seconds = 1/sec
        assert discord.per_channel_delay >= 0.5

    def test_slack_limits(self):
        """Test Slack rate limits are configured correctly."""
        from praisonai.bots._rate_limit import PLATFORM_LIMITS
        
        slack = PLATFORM_LIMITS["slack"]
        assert slack.messages_per_second <= 2  # 1 per second per channel
        assert slack.per_channel_delay >= 0.5

    def test_whatsapp_limits(self):
        """Test WhatsApp rate limits are configured correctly."""
        from praisonai.bots._rate_limit import PLATFORM_LIMITS
        
        whatsapp = PLATFORM_LIMITS["whatsapp"]
        assert whatsapp.messages_per_second >= 30  # ~80 per Cloud API docs

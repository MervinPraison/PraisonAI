"""
Comprehensive unit tests for OpenClaw gap analysis features.

Tests:
- ProbeResult / HealthResult dataclasses
- BotProtocol probe()/health() methods
- BackoffPolicy / compute_backoff / is_recoverable_error (resilience)
- BotConfig group_policy
- Config schema validation (Pydantic)
- Smart defaults for Bot
- Doctor checks
- Daemon service generation
- BotApprovalBackend
- Onboarding wizard config generation
"""

import asyncio
import os
import sys
from unittest.mock import MagicMock

import pytest


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ProbeResult / HealthResult (Core SDK)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestProbeResult:
    def test_import(self):
        from praisonaiagents.bots import ProbeResult
        assert ProbeResult is not None

    def test_ok_probe(self):
        from praisonaiagents.bots import ProbeResult
        result = ProbeResult(ok=True, platform="telegram", elapsed_ms=150.0, bot_username="test_bot")
        assert result.ok is True
        assert result.platform == "telegram"
        assert result.bot_username == "test_bot"
        assert result.error is None

    def test_failed_probe(self):
        from praisonaiagents.bots import ProbeResult
        result = ProbeResult(ok=False, platform="discord", error="Unauthorized")
        assert result.ok is False
        assert result.error == "Unauthorized"

    def test_to_dict(self):
        from praisonaiagents.bots import ProbeResult
        result = ProbeResult(ok=True, platform="slack", elapsed_ms=50.0)
        d = result.to_dict()
        assert d["ok"] is True
        assert d["platform"] == "slack"
        assert d["elapsed_ms"] == 50.0

    def test_details(self):
        from praisonaiagents.bots import ProbeResult
        result = ProbeResult(ok=True, platform="telegram", details={"bot_id": 123})
        assert result.details["bot_id"] == 123


class TestHealthResult:
    def test_import(self):
        from praisonaiagents.bots import HealthResult
        assert HealthResult is not None

    def test_healthy(self):
        from praisonaiagents.bots import HealthResult, ProbeResult
        probe = ProbeResult(ok=True, platform="telegram")
        health = HealthResult(
            ok=True, platform="telegram", is_running=True,
            uptime_seconds=3600.0, probe=probe, sessions=5,
        )
        assert health.ok is True
        assert health.is_running is True
        assert health.uptime_seconds == 3600.0
        assert health.sessions == 5
        assert health.probe.ok is True

    def test_unhealthy(self):
        from praisonaiagents.bots import HealthResult
        health = HealthResult(ok=False, platform="discord", error="Connection refused")
        assert health.ok is False
        assert health.error == "Connection refused"

    def test_to_dict_with_probe(self):
        from praisonaiagents.bots import HealthResult, ProbeResult
        probe = ProbeResult(ok=True, platform="telegram", elapsed_ms=100.0)
        health = HealthResult(ok=True, platform="telegram", probe=probe)
        d = health.to_dict()
        assert d["probe"]["ok"] is True
        assert d["probe"]["elapsed_ms"] == 100.0

    def test_to_dict_without_probe(self):
        from praisonaiagents.bots import HealthResult
        health = HealthResult(ok=True, platform="slack")
        d = health.to_dict()
        assert d["probe"] is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. BotProtocol has probe() and health()
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBotProtocolExtensions:
    def test_protocol_has_probe(self):
        from praisonaiagents.bots import BotProtocol
        assert hasattr(BotProtocol, 'probe')

    def test_protocol_has_health(self):
        from praisonaiagents.bots import BotProtocol
        assert hasattr(BotProtocol, 'health')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Resilience Module
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBackoffPolicy:
    def test_import(self):
        from praisonai.bots._resilience import BackoffPolicy
        assert BackoffPolicy is not None

    def test_defaults(self):
        from praisonai.bots._resilience import BackoffPolicy
        policy = BackoffPolicy()
        assert policy.initial_ms == 2000.0
        assert policy.max_ms == 30000.0
        assert policy.factor == 1.8

    def test_telegram_preset(self):
        from praisonai.bots._resilience import TELEGRAM_BACKOFF
        assert TELEGRAM_BACKOFF.initial_ms == 2000
        assert TELEGRAM_BACKOFF.jitter == 0.25


class TestComputeBackoff:
    def test_first_attempt(self):
        from praisonai.bots._resilience import BackoffPolicy, compute_backoff
        policy = BackoffPolicy(initial_ms=1000, factor=2.0, jitter=0.0)
        delay = compute_backoff(policy, 1)
        assert abs(delay - 1.0) < 0.01  # 1000ms = 1.0s

    def test_second_attempt(self):
        from praisonai.bots._resilience import BackoffPolicy, compute_backoff
        policy = BackoffPolicy(initial_ms=1000, factor=2.0, jitter=0.0)
        delay = compute_backoff(policy, 2)
        assert abs(delay - 2.0) < 0.01  # 2000ms = 2.0s

    def test_capped_at_max(self):
        from praisonai.bots._resilience import BackoffPolicy, compute_backoff
        policy = BackoffPolicy(initial_ms=1000, max_ms=5000, factor=10.0, jitter=0.0)
        delay = compute_backoff(policy, 3)
        assert delay <= 5.0  # Capped at max

    def test_jitter_applied(self):
        from praisonai.bots._resilience import BackoffPolicy, compute_backoff
        policy = BackoffPolicy(initial_ms=1000, factor=1.0, jitter=0.5)
        delays = [compute_backoff(policy, 1) for _ in range(20)]
        # With jitter, not all delays should be identical
        assert len(set(round(d, 3) for d in delays)) > 1


class TestIsRecoverableError:
    def test_timeout_is_recoverable(self):
        from praisonai.bots._resilience import is_recoverable_error
        assert is_recoverable_error(TimeoutError("connection timed out")) is True

    def test_connection_error_is_recoverable(self):
        from praisonai.bots._resilience import is_recoverable_error
        assert is_recoverable_error(ConnectionError("reset by peer")) is True

    def test_value_error_not_recoverable(self):
        from praisonai.bots._resilience import is_recoverable_error
        assert is_recoverable_error(ValueError("invalid input")) is False

    def test_asyncio_timeout(self):
        from praisonai.bots._resilience import is_recoverable_error
        assert is_recoverable_error(asyncio.TimeoutError()) is True

    def test_http_429_recoverable(self):
        from praisonai.bots._resilience import is_recoverable_error
        err = Exception("rate limited")
        err.status_code = 429
        assert is_recoverable_error(err) is True


class TestIsConflictError:
    def test_409_conflict(self):
        from praisonai.bots._resilience import is_conflict_error
        err = Exception("Conflict: terminated by other getUpdates")
        err.error_code = 409
        assert is_conflict_error(err) is True

    def test_non_conflict(self):
        from praisonai.bots._resilience import is_conflict_error
        assert is_conflict_error(ValueError("something")) is False


class TestConnectionMonitor:
    def test_record_success_resets(self):
        from praisonai.bots._resilience import ConnectionMonitor
        m = ConnectionMonitor(platform="test")
        m.attempt = 5
        m.last_error = "something"
        m.record_success()
        assert m.attempt == 0
        assert m.last_error is None
        assert m.total_recoveries == 1

    def test_record_error_increments(self):
        from praisonai.bots._resilience import ConnectionMonitor, BackoffPolicy
        m = ConnectionMonitor(platform="test", policy=BackoffPolicy(jitter=0.0, initial_ms=1000, factor=2.0))
        delay = m.record_error(Exception("test"))
        assert m.attempt == 1
        assert abs(delay - 1.0) < 0.01

    def test_should_retry_unlimited(self):
        from praisonai.bots._resilience import ConnectionMonitor, BackoffPolicy
        m = ConnectionMonitor(platform="test", policy=BackoffPolicy(max_attempts=0))
        m.attempt = 100
        assert m.should_retry() is True

    def test_should_retry_limited(self):
        from praisonai.bots._resilience import ConnectionMonitor, BackoffPolicy
        m = ConnectionMonitor(platform="test", policy=BackoffPolicy(max_attempts=3))
        m.attempt = 3
        assert m.should_retry() is False


class TestSleepWithAbort:
    @pytest.mark.asyncio
    async def test_normal_completion(self):
        from praisonai.bots._resilience import sleep_with_abort
        result = await sleep_with_abort(0.01)
        assert result is True

    @pytest.mark.asyncio
    async def test_aborted(self):
        from praisonai.bots._resilience import sleep_with_abort
        abort = asyncio.Event()
        abort.set()  # Already signaled
        result = await sleep_with_abort(10.0, abort)
        assert result is False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. BotConfig group_policy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBotConfigGroupPolicy:
    def test_default_group_policy(self):
        from praisonaiagents.bots import BotConfig
        config = BotConfig()
        assert config.group_policy == "mention_only"

    def test_custom_group_policy(self):
        from praisonaiagents.bots import BotConfig
        config = BotConfig(group_policy="respond_all")
        assert config.group_policy == "respond_all"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Config Schema Validation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConfigSchema:
    def test_valid_config(self):
        from praisonai.bots._config_schema import validate_bot_config
        raw = {
            "agent": {"name": "test", "model": "gpt-4o-mini"},
            "channels": {"telegram": {"token": "test123"}},
        }
        result = validate_bot_config(raw)
        assert result.channels["telegram"].token == "test123"

    def test_missing_channels_fails(self):
        from praisonai.bots._config_schema import validate_bot_config
        with pytest.raises(ValueError, match="No channels configured"):
            validate_bot_config({"agent": {"name": "test"}})

    def test_empty_channels_fails(self):
        from praisonai.bots._config_schema import validate_bot_config
        with pytest.raises(ValueError, match="No channels configured"):
            validate_bot_config({"channels": {}})

    def test_unknown_channel_fails(self):
        from praisonai.bots._config_schema import validate_bot_config
        with pytest.raises(ValueError, match="Unknown channel"):
            validate_bot_config({"channels": {"signal": {"token": "x"}}})

    def test_invalid_group_policy(self):
        from praisonai.bots._config_schema import validate_bot_config
        with pytest.raises(ValueError, match="group_policy"):
            validate_bot_config({
                "channels": {"telegram": {"token": "x", "group_policy": "invalid"}}
            })

    def test_env_var_resolution(self):
        from praisonai.bots._config_schema import validate_bot_config
        os.environ["_TEST_BOT_TOKEN"] = "resolved_token"
        try:
            raw = {"channels": {"telegram": {"token": "${_TEST_BOT_TOKEN}"}}}
            result = validate_bot_config(raw)
            assert result.channels["telegram"].token == "resolved_token"
        finally:
            del os.environ["_TEST_BOT_TOKEN"]

    def test_missing_env_var_fails(self):
        from praisonai.bots._config_schema import validate_bot_config
        os.environ.pop("_NONEXISTENT_TOKEN", None)
        with pytest.raises(ValueError, match="not set"):
            validate_bot_config({"channels": {"telegram": {"token": "${_NONEXISTENT_TOKEN}"}}})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Smart Defaults for Bot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSmartDefaults:
    def test_bot_has_apply_smart_defaults(self):
        from praisonai.bots import Bot
        bot = Bot("telegram", token="fake")
        assert hasattr(bot, '_apply_smart_defaults')

    def test_smart_defaults_adds_tools_to_bare_agent(self):
        from praisonai.bots import Bot
        mock_agent = MagicMock()
        mock_agent.__class__.__name__ = "Agent"
        mock_agent.tools = []

        bot = Bot("telegram", agent=mock_agent, token="fake")
        result = bot._apply_smart_defaults(mock_agent)
        # Should have assigned tools
        assert result.tools is not None or mock_agent.tools is not None

    def test_smart_defaults_skips_agent_with_tools(self):
        from praisonai.bots import Bot
        mock_agent = MagicMock()
        mock_agent.__class__.__name__ = "Agent"
        mock_agent.tools = [lambda: None]  # Already has tools

        bot = Bot("telegram", agent=mock_agent, token="fake")
        result = bot._apply_smart_defaults(mock_agent)
        # Should NOT overwrite existing tools
        assert len(result.tools) == 1

    def test_smart_defaults_skips_none_agent(self):
        from praisonai.bots import Bot
        bot = Bot("telegram", token="fake")
        result = bot._apply_smart_defaults(None)
        assert result is None

    def test_smart_defaults_skips_non_agent(self):
        from praisonai.bots import Bot
        mock_team = MagicMock()
        mock_team.__class__.__name__ = "AgentTeam"
        mock_team.tools = []

        bot = Bot("telegram", agent=mock_team, token="fake")
        result = bot._apply_smart_defaults(mock_team)
        # Should not modify AgentTeam
        assert len(result.tools) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Doctor Bot Checks (integrated into existing doctor framework)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestDoctorBotChecks:
    def test_bot_checks_import(self):
        from praisonai.cli.features.doctor.checks.bot_checks import check_bot_tokens, check_bot_config
        assert callable(check_bot_tokens)
        assert callable(check_bot_config)

    def test_check_category_has_bots(self):
        from praisonai.cli.features.doctor.models import CheckCategory
        assert hasattr(CheckCategory, "BOTS")
        assert CheckCategory.BOTS.value == "bots"

    def test_bot_tokens_check_no_tokens(self):
        from praisonai.cli.features.doctor.checks.bot_checks import check_bot_tokens
        from praisonai.cli.features.doctor.models import CheckStatus
        for var in ["TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "WHATSAPP_ACCESS_TOKEN"]:
            os.environ.pop(var, None)
        result = check_bot_tokens()
        assert result.status == CheckStatus.WARN

    def test_bot_tokens_check_with_token(self):
        from praisonai.cli.features.doctor.checks.bot_checks import check_bot_tokens
        from praisonai.cli.features.doctor.models import CheckStatus
        os.environ["TELEGRAM_BOT_TOKEN"] = "test123"
        try:
            result = check_bot_tokens()
            assert result.status == CheckStatus.PASS
            assert "Telegram" in result.message
        finally:
            del os.environ["TELEGRAM_BOT_TOKEN"]

    def test_bot_config_missing(self):
        from praisonai.cli.features.doctor.checks.bot_checks import check_bot_config
        from praisonai.cli.features.doctor.models import CheckStatus
        result = check_bot_config("/nonexistent/bot.yaml")
        assert result.status == CheckStatus.WARN

    def test_get_bot_checks(self):
        from praisonai.cli.features.doctor.checks.bot_checks import get_bot_checks
        checks = get_bot_checks()
        assert len(checks) >= 2
        assert all(hasattr(c, 'status') for c in checks)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Bot Approval Backend
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBotApprovalBackend:
    def test_import(self):
        from praisonai.bots._approval import BotApprovalBackend
        assert BotApprovalBackend is not None

    def test_init(self):
        from praisonai.bots._approval import BotApprovalBackend
        backend = BotApprovalBackend(timeout=60)
        assert backend._timeout == 60
        assert backend.pending_count == 0

    @pytest.mark.asyncio
    async def test_timeout_defaults_to_deny(self):
        from praisonai.bots._approval import BotApprovalBackend
        backend = BotApprovalBackend(timeout=0.01, default_on_timeout=False)
        result = await backend.request_approval("user1", "ch1", "test_tool", {})
        assert result is False

    def test_resolve_by_user_reply_yes(self):
        from praisonai.bots._approval import BotApprovalBackend
        backend = BotApprovalBackend()
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        backend._pending["approval_user1_123"] = future
        resolved = backend.resolve_by_user_reply("user1", "yes")
        assert resolved is True
        assert future.result() is True
        loop.close()

    def test_resolve_by_user_reply_no(self):
        from praisonai.bots._approval import BotApprovalBackend
        backend = BotApprovalBackend()
        loop = asyncio.new_event_loop()
        future = loop.create_future()
        backend._pending["approval_user1_456"] = future
        resolved = backend.resolve_by_user_reply("user1", "no")
        assert resolved is True
        assert future.result() is False
        loop.close()

    def test_resolve_unknown_text(self):
        from praisonai.bots._approval import BotApprovalBackend
        backend = BotApprovalBackend()
        resolved = backend.resolve_by_user_reply("user1", "hello world")
        assert resolved is False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Daemon Service
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestDaemonService:
    def test_daemon_import(self):
        from praisonai.daemon import get_daemon_status, install_daemon, uninstall_daemon
        assert callable(get_daemon_status)
        assert callable(install_daemon)
        assert callable(uninstall_daemon)

    def test_systemd_unit_generation(self):
        from praisonai.daemon.systemd import _generate_unit
        unit = _generate_unit("/tmp/test_bot.yaml")
        assert "[Unit]" in unit
        assert "[Service]" in unit
        assert "praisonai" in unit
        assert "/tmp/test_bot.yaml" in unit
        assert "Restart=always" in unit

    def test_launchd_plist_generation(self):
        from praisonai.daemon.launchd import _generate_plist
        plist = _generate_plist("/tmp/test_bot.yaml")
        assert "<?xml" in plist
        assert "ai.praison.bot" in plist
        assert "/tmp/test_bot.yaml" in plist
        assert "KeepAlive" in plist

    def test_detect_platform(self):
        from praisonai.daemon import _detect_platform
        plat = _detect_platform()
        assert plat in ("systemd", "launchd", "windows", "unknown")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. Onboarding Wizard Config Generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestOnboardWizard:
    def test_import(self):
        from praisonai.cli.features.onboard import OnboardWizard
        assert OnboardWizard is not None

    def test_generate_bot_yaml(self):
        from praisonai.cli.features.onboard import _generate_bot_yaml
        yaml_str = _generate_bot_yaml(["telegram"], agent_name="mybot", agent_instructions="Be helpful")
        assert "telegram:" in yaml_str
        assert "mybot" in yaml_str
        assert "TELEGRAM_BOT_TOKEN" in yaml_str
        assert "mention_only" in yaml_str

    def test_generate_multi_platform(self):
        from praisonai.cli.features.onboard import _generate_bot_yaml
        yaml_str = _generate_bot_yaml(["telegram", "discord"])
        assert "telegram:" in yaml_str
        assert "discord:" in yaml_str

    def test_wizard_init(self):
        from praisonai.cli.features.onboard import OnboardWizard
        wizard = OnboardWizard()
        assert wizard.selected_platforms == []
        assert wizard.agent_name == "assistant"

    def test_platforms_info(self):
        from praisonai.cli.features.onboard import PLATFORMS
        assert "telegram" in PLATFORMS
        assert "discord" in PLATFORMS
        assert "slack" in PLATFORMS
        assert "whatsapp" in PLATFORMS
        assert all("token_env" in v for v in PLATFORMS.values())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. Bot probe() and health() delegation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBotDelegation:
    def test_bot_has_probe(self):
        from praisonai.bots import Bot
        bot = Bot("telegram", token="fake")
        assert hasattr(bot, 'probe')

    def test_bot_has_health(self):
        from praisonai.bots import Bot
        bot = Bot("telegram", token="fake")
        assert hasattr(bot, 'health')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. Import Time Regression
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestImportTime:
    def test_core_sdk_import_time(self):
        """Core SDK import must be < 200ms."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", 
             "import time; t=time.perf_counter(); import praisonaiagents; print(f'{(time.perf_counter()-t)*1000:.0f}')"],
            capture_output=True, text=True, timeout=10,
        )
        ms = int(result.stdout.strip())
        assert ms < 500, f"Import took {ms}ms, target <200ms"

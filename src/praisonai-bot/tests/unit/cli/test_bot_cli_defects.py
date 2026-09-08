"""Regression tests for four silent ``praisonai bot`` defects.

Each test here fails on the code as it stood before the accompanying fix:

1. ``bot start`` started a *different* bot than ``platform:`` declared, because
   the single-bot migration required an inline ``token:``. With the token in
   the environment (the documented way) the declared platform was dropped and
   credential autofill invented channels from unrelated env vars — a
   ``platform: telegram`` config logged into Discord.
2. ``bot slack`` could not start at all: ``BotConfig(app_token=...)`` is not a
   field, so every Slack start raised ``TypeError``.
3. ``bot linear`` returned from ``start()`` the instant the webhook socket was
   armed, so ``asyncio.run`` tore it down and the command exited 0 without
   ever serving.
4. Twenty failure paths printed ``Error: ...`` and exited **0**.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from typer.testing import CliRunner

from praisonai_bot.bots._config_schema import GatewayConfigSchema
from praisonai_bot.cli.commands.bot import app as bot_app
from praisonai_bot.cli.features.bots_cli import (
    BotHandler,
    BotStartupError,
    _serve_bot,
)

# Every platform credential the registry knows about, so a test can start from
# a known-clean environment instead of inheriting the developer's shell.
_CREDENTIAL_ENV = (
    "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "LINEAR_OAUTH_TOKEN",
    "LINEAR_API_KEY",
    "LINEAR_WEBHOOK_SECRET",
    "EMAIL_APP_PASSWORD",
    "EMAIL_ADDRESS",
    "AGENTMAIL_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Drop every platform credential and stop ``.env`` re-seeding them."""
    for name in _CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(BotHandler, "_load_dotenv", staticmethod(lambda: None))
    return monkeypatch


# ── Defect 1: the declared platform must win ────────────────────────────


class TestDeclaredPlatformWins:
    """Assert the *resolved platform*, never the log text."""

    def test_platform_declared_without_inline_token_is_kept(self, clean_env):
        """``platform: telegram`` + token in env resolves to a telegram channel."""
        clean_env.setenv("TELEGRAM_BOT_TOKEN", "tg-token-from-env")

        config = GatewayConfigSchema(
            platform="telegram",
            agent={"name": "assistant", "instructions": "Be helpful."},
        )

        assert list(config.channels) == ["telegram"]
        assert config.channels["telegram"].platform == "telegram"

    def test_unrelated_credential_cannot_replace_declared_platform(self, clean_env):
        """A stray ``DISCORD_BOT_TOKEN`` must not turn a telegram bot into a discord one."""
        clean_env.setenv("TELEGRAM_BOT_TOKEN", "tg-token-from-env")
        clean_env.setenv("DISCORD_BOT_TOKEN", "discord-token-that-is-none-of-our-business")

        config = GatewayConfigSchema(
            platform="telegram",
            agent={"name": "assistant", "instructions": "Be helpful."},
        )

        resolved = [
            (channel.platform or name).lower()
            for name, channel in config.channels.items()
        ]
        assert resolved == ["telegram"]
        assert "discord" not in config.channels

    def test_declared_platform_wins_even_with_no_matching_credential(self, clean_env):
        """The exact reproduction: only DISCORD_BOT_TOKEN is exported."""
        clean_env.setenv("DISCORD_BOT_TOKEN", "discord-token-that-is-none-of-our-business")

        config = GatewayConfigSchema(
            platform="telegram",
            agent={"name": "assistant", "instructions": "Be helpful."},
        )

        first = next(iter(config.channels))
        assert (config.channels[first].platform or first).lower() == "telegram"

    def test_bot_start_dispatches_to_the_declared_platform(self, clean_env, tmp_path):
        """End to end through the CLI handler: which ``start_*`` actually runs."""
        clean_env.setenv("TELEGRAM_BOT_TOKEN", "tg-token-from-env")
        clean_env.setenv("DISCORD_BOT_TOKEN", "discord-token-that-is-none-of-our-business")

        config_file = tmp_path / "bot.yaml"
        config_file.write_text(
            "platform: telegram\n"
            "agent:\n"
            "  name: My Assistant\n"
            "  instructions: Be helpful.\n"
        )

        dispatched: list[str] = []
        for platform in ("telegram", "discord", "slack", "whatsapp", "email", "agentmail"):
            clean_env.setattr(
                BotHandler,
                f"start_{platform}",
                lambda self, *a, _p=platform, **kw: dispatched.append(_p),
            )
        clean_env.setattr(
            BotHandler,
            "start_generic",
            lambda self, platform, *a, **kw: dispatched.append(f"generic:{platform}"),
        )

        BotHandler().start_from_config(str(config_file))

        assert dispatched == ["telegram"]

    def test_explicit_channels_block_still_autofills(self, clean_env):
        """No regression: a gateway config without ``platform:`` keeps autofill."""
        clean_env.setenv("DISCORD_BOT_TOKEN", "discord-token")

        config = GatewayConfigSchema(
            agent={"name": "assistant", "instructions": "Be helpful."},
        )

        assert "discord" in config.channels


# ── Defect 2: bot slack must be able to start ───────────────────────────


class _StubSlackBot:
    instances: list["_StubSlackBot"] = []

    def __init__(self, token=None, app_token=None, agent=None, config=None, **kwargs):
        self.token = token
        self.app_token = app_token
        self.config = config
        self.is_running = False
        _StubSlackBot.instances.append(self)

    async def start(self):
        self.is_running = False  # return immediately; nothing to serve

    async def stop(self):
        self.is_running = False


class TestSlackStarts:
    def test_start_slack_builds_a_valid_bot_config(self, clean_env, monkeypatch):
        """``BotConfig(app_token=...)`` raised TypeError — Slack could never start."""
        clean_env.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        clean_env.setenv("SLACK_APP_TOKEN", "xapp-test")

        _StubSlackBot.instances.clear()
        import praisonai_bot.bots as bots_pkg

        monkeypatch.setattr(bots_pkg, "SlackBot", _StubSlackBot, raising=False)
        monkeypatch.setattr(
            BotHandler, "_load_agent", lambda self, *a, **kw: object()
        )

        BotHandler().start_slack()

        assert len(_StubSlackBot.instances) == 1
        bot = _StubSlackBot.instances[0]
        # Socket Mode reads the adapter's own attribute, not a BotConfig field.
        assert bot.app_token == "xapp-test"
        assert not hasattr(bot.config, "app_token")

    def test_missing_app_token_fails_loudly(self, clean_env):
        """Socket Mode without an app token subscribed to nothing and 'ran'."""
        clean_env.setenv("SLACK_BOT_TOKEN", "xoxb-test")

        with pytest.raises(BotStartupError) as excinfo:
            BotHandler().start_slack()
        assert excinfo.value.code == 1


# ── Defect 3: a started bot must stay up ────────────────────────────────


class _StubWebhookBot:
    """Mimics LinearBot: ``start()`` arms a server and returns."""

    instances: list["_StubWebhookBot"] = []

    def __init__(self, *args, **kwargs):
        self.is_running = False
        self.served = False
        self.stopped = False
        _StubWebhookBot.instances.append(self)

    async def start(self):
        self.is_running = True

        async def _inbound():
            # Stands in for a webhook arriving shortly after startup.
            await asyncio.sleep(0.2)
            self.served = True
            self.is_running = False

        self._inbound_task = asyncio.ensure_future(_inbound())

    async def stop(self):
        self.stopped = True
        self.is_running = False


class TestBotStaysUp:
    def test_serve_bot_blocks_until_the_bot_stops(self):
        """``_serve_bot`` must not return while the adapter is still running."""
        bot = _StubWebhookBot()
        started = time.monotonic()
        asyncio.run(_serve_bot(bot))
        assert bot.served is True
        assert time.monotonic() - started >= 0.15

    def test_start_linear_serves_instead_of_exiting_immediately(
        self, clean_env, monkeypatch
    ):
        """``bot linear`` returned in under a second having served nothing."""
        clean_env.setenv("LINEAR_OAUTH_TOKEN", "lin_oauth_test")
        clean_env.setenv("LINEAR_WEBHOOK_SECRET", "secret")

        _StubWebhookBot.instances.clear()
        import praisonai_bot.bots as bots_pkg

        monkeypatch.setattr(bots_pkg, "LinearBot", _StubWebhookBot, raising=False)
        monkeypatch.setattr(
            BotHandler, "_load_agent", lambda self, *a, **kw: object()
        )

        BotHandler().start_linear(webhook_port=18999)

        assert len(_StubWebhookBot.instances) == 1
        assert _StubWebhookBot.instances[0].served is True

    def test_start_email_serves_instead_of_exiting_immediately(
        self, clean_env, monkeypatch
    ):
        """Same shape: EmailBot spawns a poll task and returns from start()."""
        clean_env.setenv("EMAIL_APP_PASSWORD", "app-password")

        _StubWebhookBot.instances.clear()
        import praisonai_bot.bots as bots_pkg

        monkeypatch.setattr(bots_pkg, "EmailBot", _StubWebhookBot, raising=False)
        monkeypatch.setattr(
            BotHandler, "_load_agent", lambda self, *a, **kw: object()
        )

        BotHandler().start_email(email_address="a@b.c")

        assert _StubWebhookBot.instances[0].served is True


# ── Defect 4: failure paths must exit non-zero ──────────────────────────


class TestExitCodes:
    """Assert exit codes, not messages."""

    runner = CliRunner()

    def test_start_with_missing_config_exits_nonzero(self, clean_env):
        result = self.runner.invoke(bot_app, ["start", "--config", "/nope/nope.yaml"])
        assert result.exit_code != 0

    def test_start_with_invalid_config_exits_nonzero(self, clean_env, tmp_path):
        bad = tmp_path / "bot.yaml"
        bad.write_text("channels:\n  nonsense:\n    platform: not-a-real-platform\n")
        result = self.runner.invoke(bot_app, ["start", "--config", str(bad)])
        assert result.exit_code != 0

    def test_email_without_password_exits_nonzero(self, clean_env):
        result = self.runner.invoke(bot_app, ["email"])
        assert result.exit_code != 0

    def test_telegram_without_token_exits_nonzero(self, clean_env):
        result = self.runner.invoke(bot_app, ["telegram"])
        assert result.exit_code != 0

    def test_discord_without_token_exits_nonzero(self, clean_env):
        result = self.runner.invoke(bot_app, ["discord"])
        assert result.exit_code != 0

    def test_slack_without_token_exits_nonzero(self, clean_env):
        result = self.runner.invoke(bot_app, ["slack"])
        assert result.exit_code != 0

    def test_linear_without_token_exits_nonzero(self, clean_env):
        result = self.runner.invoke(bot_app, ["linear"])
        assert result.exit_code != 0

    def test_agentmail_without_key_exits_nonzero(self, clean_env):
        result = self.runner.invoke(bot_app, ["agentmail"])
        assert result.exit_code != 0

    def test_whatsapp_without_token_exits_nonzero(self, clean_env):
        result = self.runner.invoke(bot_app, ["whatsapp"])
        assert result.exit_code != 0

    def test_run_with_unknown_platform_exits_nonzero(self, clean_env, monkeypatch):
        """Rejected up front, by name — not as an incidental crash deeper in."""

        def _never(*a, **kw):  # pragma: no cover - must not be reached
            raise AssertionError("agent was built for an unknown platform")

        monkeypatch.setattr(BotHandler, "_load_agent", _never)
        result = self.runner.invoke(bot_app, ["run", "--platform", "not-a-platform"])
        assert result.exit_code == 1
        assert isinstance(result.exception, BotStartupError)


# ── Reachability: platforms with adapters but no CLI verb ───────────────


class TestGenericRun:
    def test_signal_webhook_and_local_are_reachable(self, clean_env, monkeypatch):
        """``signal``/``webhook``/``local`` ship adapters; they now have a verb."""
        from praisonai_bot.bots._registry import list_platforms

        registered = {p.lower() for p in list_platforms()}
        assert {"signal", "webhook", "local"} <= registered

        seen: list[str] = []
        monkeypatch.setattr(
            BotHandler,
            "start_generic",
            lambda self, platform, *a, **kw: seen.append(platform),
        )
        result = CliRunner().invoke(bot_app, ["run", "--platform", "local"])
        assert result.exit_code == 0
        assert seen == ["local"]

    def test_bot_start_does_not_silently_no_op_on_a_verbless_platform(
        self, clean_env, tmp_path
    ):
        """``bot start`` used to fall off its if/elif chain and exit 0."""
        config_file = tmp_path / "bot.yaml"
        config_file.write_text(
            "platform: local\n"
            "agent:\n"
            "  name: My Assistant\n"
            "  instructions: Be helpful.\n"
        )

        seen: list[str] = []
        clean_env.setattr(
            BotHandler,
            "start_generic",
            lambda self, platform, *a, **kw: seen.append(platform),
        )

        BotHandler().start_from_config(str(config_file))

        assert seen == ["local"]

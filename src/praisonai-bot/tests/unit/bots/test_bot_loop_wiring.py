"""Tests for bot-to-bot loop guard wiring on the inbound path (#5062).

The core ``BotLoopGuard`` primitive is tested in praisonai-agents; these tests
cover the *wrapper* wiring: the ``MessageHookMixin.bot_loop_allows`` helper and
the gateway ``_apply_bot_loop_config`` config surface.
"""

from __future__ import annotations

from praisonaiagents.bots import BotConfig, BotUser
from praisonai_bot.bots._protocol_mixin import MessageHookMixin
from praisonai_bot.gateway.server import _apply_bot_loop_config


class _FakeAdapter(MessageHookMixin):
    def __init__(self, config: BotConfig) -> None:
        self.config = config


def test_human_sender_always_allowed():
    adapter = _FakeAdapter(BotConfig())
    human = BotUser(user_id="u1", is_bot=False)
    assert adapter.bot_loop_allows(human, self_bot_id="me") is True


def test_missing_sender_allowed():
    adapter = _FakeAdapter(BotConfig())
    assert adapter.bot_loop_allows(None, self_bot_id="me") is True


def test_bot_sender_dropped_by_default():
    # Default allow_bots=False preserves today's "drop bot messages" behaviour.
    adapter = _FakeAdapter(BotConfig())
    bot = BotUser(user_id="otherbot", is_bot=True)
    assert adapter.bot_loop_allows(bot, self_bot_id="me") is False


def test_bot_sender_allowed_until_budget_exceeded():
    adapter = _FakeAdapter(
        BotConfig(allow_bots=True, bot_loop_protection={"max_events_per_window": 2})
    )
    bot = BotUser(user_id="otherbot", is_bot=True)
    verdicts = [adapter.bot_loop_allows(bot, self_bot_id="me") for _ in range(4)]
    # First two exchanges pass, then the pair is suppressed for cooldown.
    assert verdicts == [True, True, False, False]


def test_distinct_pairs_tracked_independently():
    adapter = _FakeAdapter(
        BotConfig(allow_bots=True, bot_loop_protection={"max_events_per_window": 1})
    )
    a = BotUser(user_id="botA", is_bot=True)
    b = BotUser(user_id="botB", is_bot=True)
    assert adapter.bot_loop_allows(a, self_bot_id="me") is True
    # A different pair has its own budget; first exchange still allowed.
    assert adapter.bot_loop_allows(b, self_bot_id="me") is True
    # Second exchange on pair A exceeds its budget.
    assert adapter.bot_loop_allows(a, self_bot_id="me") is False


def test_disabled_policy_never_suppresses():
    adapter = _FakeAdapter(
        BotConfig(allow_bots=True, bot_loop_protection={"enabled": False})
    )
    bot = BotUser(user_id="otherbot", is_bot=True)
    assert all(
        adapter.bot_loop_allows(bot, self_bot_id="me") for _ in range(50)
    )


def test_gateway_config_parse_bool_and_dict():
    kwargs: dict = {}
    _apply_bot_loop_config(
        kwargs,
        {"allow_bots": "true", "bot_loop_protection": {"max_events_per_window": 5}},
    )
    assert kwargs["allow_bots"] is True
    assert kwargs["bot_loop_protection"] == {"max_events_per_window": 5}


def test_gateway_config_parse_empty_is_noop():
    kwargs: dict = {}
    _apply_bot_loop_config(kwargs, {})
    assert kwargs == {}


def test_gateway_config_parse_falsey_string():
    kwargs: dict = {}
    _apply_bot_loop_config(kwargs, {"allow_bots": "false"})
    assert kwargs["allow_bots"] is False


def test_malformed_policy_does_not_crash_inbound():
    # A config typo (non-numeric max_events_per_window) must not raise on the
    # first opted-in bot message; the guard falls back to safe defaults (#5062).
    adapter = _FakeAdapter(
        BotConfig(allow_bots=True, bot_loop_protection={"max_events_per_window": "oops"})
    )
    bot = BotUser(user_id="otherbot", is_bot=True)
    # Default budget is 20; a single exchange is well within it → allowed.
    assert adapter.bot_loop_allows(bot, self_bot_id="me") is True


def test_non_dict_policy_tolerated():
    # A misdeclared scalar for bot_loop_protection is ignored, not fatal.
    adapter = _FakeAdapter(BotConfig(allow_bots=True, bot_loop_protection="nonsense"))
    bot = BotUser(user_id="otherbot", is_bot=True)
    assert adapter.bot_loop_allows(bot, self_bot_id="me") is True


def test_cli_policy_kwargs_forwards_bot_fields():
    # The `praisonai bot start` path must fold allow_bots / bot_loop_protection
    # into BotConfig, mirroring the gateway (#5062).
    from praisonai_bot.cli.features.bots_cli import BotCapabilities, BotHandler

    caps = BotCapabilities(
        allow_bots=True, bot_loop_protection={"max_events_per_window": 7}
    )
    kwargs = BotHandler._policy_kwargs(caps)
    assert kwargs["allow_bots"] is True
    assert kwargs["bot_loop_protection"] == {"max_events_per_window": 7}


def test_cli_policy_kwargs_defaults_omit_bot_fields():
    from praisonai_bot.cli.features.bots_cli import BotCapabilities, BotHandler

    kwargs = BotHandler._policy_kwargs(BotCapabilities())
    assert "allow_bots" not in kwargs
    assert "bot_loop_protection" not in kwargs

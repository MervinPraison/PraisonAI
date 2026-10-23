"""Issue #5962: one ``group_policy`` behaves identically on every channel."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from praisonaiagents.bots import BotConfig
from praisonaiagents.bots.admission import MentionFacts

from praisonai_bot.bots._group_policy import (
    decide_group_admission,
    effective_group_policy,
    record_passive_group_message,
)


def _cfg(**kw):
    return BotConfig(token="t", **kw)


@pytest.mark.parametrize(
    "policy,required,expected",
    [
        ("mention_only", True, "mention_only"),
        ("mention_only", False, "respond_all"),  # legacy mention_required=False
        ("observe", False, "observe"),  # gateway derives mention_required=False
        ("command_only", False, "command_only"),
        ("bogus", True, "mention_only"),
        ("bogus", False, "respond_all"),
    ],
)
def test_effective_group_policy(policy, required, expected):
    cfg = _cfg(mention_required=required)
    cfg.group_policy = policy
    assert effective_group_policy(cfg) == expected


def test_observe_records_unmentioned_and_runs_on_reply():
    cfg = _cfg(group_policy="observe", mention_required=False)
    d = decide_group_admission(cfg, chat_type="group", mention=MentionFacts())
    assert not d.admit and d.observe
    d = decide_group_admission(cfg, chat_type="group", mention=MentionFacts(reply_to_bot=True))
    assert d.admit


def test_command_only_and_dm():
    cfg = _cfg(group_policy="command_only")
    assert not decide_group_admission(cfg, chat_type="group", mention=MentionFacts(explicit=True)).admit
    assert decide_group_admission(cfg, chat_type="group", mention=MentionFacts(), is_command=True).admit
    assert decide_group_admission(cfg, chat_type="dm", mention=MentionFacts()).admit


def test_record_passive_group_message_routes_fields():
    bot = SimpleNamespace(_session=MagicMock(), config=_cfg())
    msg = SimpleNamespace(
        content="hi",
        sender=SimpleNamespace(user_id="u1", display_name="Ann"),
        channel=SimpleNamespace(channel_id="c1"),
        thread_id="t1",
    )
    record_passive_group_message(bot, msg)
    args, kwargs = bot._session.record_passive.call_args
    assert args == ("u1", "hi")
    assert kwargs["chat_id"] == "c1" and kwargs["thread_id"] == "t1"


def test_discord_is_reply_to_bot():
    from praisonai_bot.bots.discord import DiscordBot

    bot = DiscordBot.__new__(DiscordBot)
    bot._client = SimpleNamespace(user=SimpleNamespace(id=42))
    reply = SimpleNamespace(reference=SimpleNamespace(resolved=SimpleNamespace(author=SimpleNamespace(id=42))))
    other = SimpleNamespace(reference=SimpleNamespace(resolved=SimpleNamespace(author=SimpleNamespace(id=7))))
    assert bot._is_reply_to_bot(reply) is True
    assert bot._is_reply_to_bot(other) is False
    assert bot._is_reply_to_bot(SimpleNamespace(reference=None)) is False

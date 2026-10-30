"""Tests for ``MessageHookMixin.mention_user`` (Issue #6119)."""

from praisonaiagents.session.identity import InMemoryIdentityResolver

from praisonai_bot.bots._protocol_mixin import MessageHookMixin


class _Bot(MessageHookMixin):
    _mention_template = "<@{}>"
    platform = "discord"

    def __init__(self, resolver=None):
        self._identity_resolver = resolver


class _PlainBot(MessageHookMixin):
    platform = "telegram"
    _identity_resolver = None


def test_linked_identity_renders_native_mention():
    resolver = InMemoryIdentityResolver()
    resolver.link("telegram", "111", "alice")
    resolver.link("discord", "222", "alice")
    assert _Bot(resolver).mention_user("alice") == "<@222>"


def test_unlinked_platform_prefixed_id_renders_mention():
    assert _Bot().mention_user("discord:333") == "<@333>"


def test_not_linked_on_this_platform_falls_back_to_text():
    resolver = InMemoryIdentityResolver()
    resolver.link("telegram", "111", "alice")
    assert _Bot(resolver).mention_user("alice") == "alice"
    assert _Bot().mention_user("slack:U1") == "slack:U1"


def test_platform_without_mention_support_falls_back_to_text():
    assert _PlainBot().mention_user("telegram:111") == "telegram:111"


def test_slack_and_discord_declare_mention_template():
    from praisonai_bot.bots.discord import DiscordBot
    from praisonai_bot.bots.slack import SlackBot

    assert DiscordBot._mention_template == "<@{}>"
    assert SlackBot._mention_template == "<@{}>"


def test_resolver_stamped_on_session_is_used():
    """Bot/BotOS/gateway stamp the resolver on ``adapter._session``."""
    from praisonai_bot.bots.discord import DiscordBot

    resolver = InMemoryIdentityResolver()
    resolver.link("discord", "222", "alice")
    bot = DiscordBot(token="test-token")
    bot._session._identity_resolver = resolver
    assert bot.mention_user("alice") == "<@222>"

"""Tests for adapter ``list_channels()`` enumeration (issue #2833).

Discord/Slack adapters must expose ``list_channels()`` so the already-wired
``ChannelDirectory.refresh_from_adapters`` can populate the durable directory
with reachable channels the bot has never received a message from.

The adapters carry heavy optional dependencies and rich construction, so these
tests invoke the enumeration methods against lightweight fakes via the unbound
function objects rather than constructing full adapters.
"""

from types import SimpleNamespace

from praisonai_bot.bots.delivery import ChannelDirectory, ChannelRef
from praisonai_bot.bots.discord import DiscordBot
from praisonai_bot.bots.slack import SlackBot


# --- Discord -----------------------------------------------------------------


def _discord_stub(guilds):
    stub = SimpleNamespace(_client=SimpleNamespace(guilds=guilds))
    stub.list_channels = lambda: DiscordBot.list_channels(stub)
    return stub


def test_discord_list_channels_walks_guilds():
    guild = SimpleNamespace(
        name="Acme",
        text_channels=[
            SimpleNamespace(id=100, name="general"),
            SimpleNamespace(id=200, name="announcements"),
        ],
    )
    self = _discord_stub([guild])

    channels = DiscordBot.list_channels(self)

    assert {c.id for c in channels} == {"100", "200"}
    names = {c.name for c in channels}
    assert "Acme/general" in names
    assert "Acme/announcements" in names
    assert all(isinstance(c, ChannelRef) for c in channels)


def test_discord_list_channels_no_client_returns_empty():
    self = SimpleNamespace(_client=None)
    assert DiscordBot.list_channels(self) == []


def test_discord_list_channels_feeds_directory(tmp_path):
    guild = SimpleNamespace(
        name="Acme", text_channels=[SimpleNamespace(id=555, name="ops")]
    )
    adapter = _discord_stub([guild])

    d = ChannelDirectory(
        persist_path=tmp_path / "dir.json",
        aliases_path=tmp_path / "aliases.json",
    )
    d.refresh_from_adapters({"discord": adapter})

    assert d.has_channel("discord", "555")


# --- Slack -------------------------------------------------------------------


class _FakeSlackClient:
    """Minimal async Web client emulating cursor pagination."""

    def __init__(self, pages):
        self._pages = pages
        self._i = 0

    async def conversations_list(self, **kwargs):
        page = self._pages[self._i]
        self._i += 1
        return page


def _slack_stub(client):
    stub = SimpleNamespace(_client=client)
    stub._list_channels_async = lambda: SlackBot._list_channels_async(stub)
    stub.list_channels = lambda: SlackBot.list_channels(stub)
    return stub


def test_slack_list_channels_paginates():
    client = _FakeSlackClient(
        [
            {
                "channels": [{"id": "C1", "name": "general"}],
                "response_metadata": {"next_cursor": "abc"},
            },
            {
                "channels": [{"id": "C2", "name": "random"}],
                "response_metadata": {"next_cursor": ""},
            },
        ]
    )
    self = _slack_stub(client)

    channels = SlackBot.list_channels(self)

    assert {c.id for c in channels} == {"C1", "C2"}
    assert all(isinstance(c, ChannelRef) for c in channels)


def test_slack_list_channels_no_client_returns_empty():
    self = _slack_stub(None)
    assert SlackBot.list_channels(self) == []


def test_slack_list_channels_pagination_is_bounded():
    from praisonai_bot.bots import slack as slack_mod

    class _NeverEndingClient:
        """Emulates a misbehaving API that always returns a next_cursor."""

        def __init__(self):
            self.calls = 0

        async def conversations_list(self, **kwargs):
            self.calls += 1
            return {
                "channels": [{"id": f"C{self.calls}", "name": "loop"}],
                "response_metadata": {"next_cursor": "always"},
            }

    client = _NeverEndingClient()
    self = _slack_stub(client)

    channels = SlackBot.list_channels(self)

    assert client.calls == slack_mod._MAX_LIST_CHANNELS_PAGES
    assert len(channels) == slack_mod._MAX_LIST_CHANNELS_PAGES


def test_slack_list_channels_feeds_directory(tmp_path):
    client = _FakeSlackClient(
        [
            {
                "channels": [{"id": "C9", "name": "eng"}],
                "response_metadata": {"next_cursor": ""},
            }
        ]
    )
    adapter = _slack_stub(client)

    d = ChannelDirectory(
        persist_path=tmp_path / "dir.json",
        aliases_path=tmp_path / "aliases.json",
    )
    d.refresh_from_adapters({"slack": adapter})

    assert d.has_channel("slack", "C9")

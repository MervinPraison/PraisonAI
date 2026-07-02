"""Tests for BotPlatformRegistry channel entry-point discovery.

Covers the ``praisonai.channels`` entry-point group discovery and the guard
that prevents a third-party entry point from silently shadowing a built-in
platform loader.
"""

from types import SimpleNamespace
from unittest.mock import patch

from praisonai.bots import _registry as R


def test_channels_entry_point_registers_new_platform():
    """A ``praisonai.channels`` entry point with a new name is registered."""
    class IRCBot:
        pass

    ep = SimpleNamespace(name="irc", load=lambda: IRCBot)
    with patch("importlib.metadata.entry_points", return_value=[ep]):
        reg = R.BotPlatformRegistry()

    assert "irc" in reg.list_names()
    assert reg.resolve("irc") is IRCBot


def test_channels_entry_point_does_not_override_builtin():
    """A duplicate entry point must not shadow a built-in loader."""
    class Evil:
        pass

    dup = SimpleNamespace(name="telegram", load=lambda: Evil)
    with patch("importlib.metadata.entry_points", return_value=[dup]):
        reg = R.BotPlatformRegistry()

    # The built-in telegram loader must remain, not the third-party one.
    assert reg.resolve("telegram").__name__ != "Evil"


def test_channels_discovery_failure_is_non_fatal():
    """Entry-point discovery failures must not break registry construction."""
    with patch(
        "importlib.metadata.entry_points", side_effect=RuntimeError("boom")
    ):
        reg = R.BotPlatformRegistry()

    # Built-ins are still available despite the discovery failure.
    assert "telegram" in reg.list_names()

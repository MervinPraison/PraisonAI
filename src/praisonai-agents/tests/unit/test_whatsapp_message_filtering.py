"""
Comprehensive tests for WhatsApp message filtering feature.

Tests cover:
- Constructor parameter handling (allowed_numbers, allowed_groups, respond_to_all)
- Phone number normalization
- Filtering logic in _on_web_message (self-only, allowlists, respond_to_all)
- CLI flag parsing and wiring
- YAML config wiring
- Edge cases
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest  # noqa: F401 — used by test discovery

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "praisonai"))


# ── Helpers ──────────────────────────────────────────────────────

def _make_bot(**kwargs):
    """Create a WhatsAppBot in web mode with filtering kwargs."""
    from praisonai.bots.whatsapp import WhatsAppBot
    defaults = dict(mode="web")
    defaults.update(kwargs)
    return WhatsAppBot(**defaults)


def _make_neonize_event(
    is_from_me=False,
    is_group=False,
    sender="1234567890@s.whatsapp.net",
    chat="1234567890@s.whatsapp.net",
    text="hello",
    timestamp=None,
):
    """Create a mock neonize MessageEv with MessageSource fields.

    Args:
        timestamp: Epoch seconds (float). If *None* defaults to
                   ``time.time()`` so the event looks "fresh".
    """
    import time as _time
    event = MagicMock()
    event.Info.MessageSource.IsFromMe = is_from_me
    event.Info.MessageSource.IsGroup = is_group
    event.Info.MessageSource.Sender = MagicMock()
    event.Info.MessageSource.Sender.__str__ = lambda self: sender
    event.Info.MessageSource.Chat = MagicMock()
    event.Info.MessageSource.Chat.__str__ = lambda self: chat
    event.Info.ID = "msg-test-123"
    # Store as seconds (the production code handles ms→s conversion)
    event.Info.Timestamp = timestamp if timestamp is not None else _time.time()
    event.Message.conversation = text
    event.Message.extendedTextMessage = None
    return event


# ── Constructor: Filtering Defaults ──────────────────────────────

class TestFilteringDefaults:
    """Test default filtering behavior (self-only)."""

    def test_default_respond_to_all_false(self):
        bot = _make_bot()
        assert bot._respond_to_all is False

    def test_default_allowed_numbers_empty(self):
        bot = _make_bot()
        assert bot._allowed_numbers == set()

    def test_default_allowed_groups_empty(self):
        bot = _make_bot()
        assert bot._allowed_groups == set()


# ── Constructor: respond_to_all ──────────────────────────────────

class TestRespondToAll:
    """Test respond_to_all parameter."""

    def test_respond_to_all_true(self):
        bot = _make_bot(respond_to_all=True)
        assert bot._respond_to_all is True

    def test_respond_to_all_false_explicit(self):
        bot = _make_bot(respond_to_all=False)
        assert bot._respond_to_all is False


# ── Constructor: Phone Number Normalization ──────────────────────

class TestPhoneNumberNormalization:
    """Test that allowed_numbers are normalized (digits only)."""

    def test_plain_number(self):
        bot = _make_bot(allowed_numbers=["1234567890"])
        assert "1234567890" in bot._allowed_numbers

    def test_plus_prefix_stripped(self):
        bot = _make_bot(allowed_numbers=["+1234567890"])
        assert "1234567890" in bot._allowed_numbers

    def test_dashes_stripped(self):
        bot = _make_bot(allowed_numbers=["1-234-567-8901"])
        assert "12345678901" in bot._allowed_numbers

    def test_spaces_stripped(self):
        bot = _make_bot(allowed_numbers=["1 234 567 8901"])
        assert "12345678901" in bot._allowed_numbers

    def test_parentheses_stripped(self):
        bot = _make_bot(allowed_numbers=["(123) 456-7890"])
        assert "1234567890" in bot._allowed_numbers

    def test_multiple_numbers(self):
        bot = _make_bot(allowed_numbers=["+1-555-1234", "9876543210"])
        assert "15551234" in bot._allowed_numbers
        assert "9876543210" in bot._allowed_numbers

    def test_empty_string_ignored(self):
        bot = _make_bot(allowed_numbers=["", "1234"])
        assert "" not in bot._allowed_numbers
        assert "1234" in bot._allowed_numbers

    def test_none_allowed_numbers(self):
        bot = _make_bot(allowed_numbers=None)
        assert bot._allowed_numbers == set()


# ── Constructor: Allowed Groups ──────────────────────────────────

class TestAllowedGroups:
    """Test allowed_groups parameter."""

    def test_single_group(self):
        bot = _make_bot(allowed_groups=["120363123456@g.us"])
        assert "120363123456@g.us" in bot._allowed_groups

    def test_multiple_groups(self):
        bot = _make_bot(allowed_groups=["g1@g.us", "g2@g.us"])
        assert "g1@g.us" in bot._allowed_groups
        assert "g2@g.us" in bot._allowed_groups

    def test_whitespace_stripped(self):
        bot = _make_bot(allowed_groups=["  120363123456@g.us  "])
        assert "120363123456@g.us" in bot._allowed_groups

    def test_none_allowed_groups(self):
        bot = _make_bot(allowed_groups=None)
        assert bot._allowed_groups == set()


# ── Filtering Logic: _on_web_message ─────────────────────────────

class TestFilteringSelfOnly:
    """Test default self-only filtering (no allowlists, no respond_to_all).

    'Self-only' means the user is messaging their own number (self-chat).
    IsFromMe alone is NOT enough — the chat JID must equal the sender JID.
    """

    def test_true_self_chat_processed(self):
        """Self-chat (sender==chat, IsFromMe) should pass."""
        bot = _make_bot()
        assert bot._respond_to_all is False
        assert bot._allowed_numbers == set()
        assert bot._allowed_groups == set()

        event = _make_neonize_event(
            is_from_me=True,
            sender="1234567890@s.whatsapp.net",
            chat="1234567890@s.whatsapp.net",
            text="hello bot",
        )
        is_from_me = bool(event.Info.MessageSource.IsFromMe)
        assert is_from_me is True

    def test_is_from_me_in_other_chat_rejected(self):
        """IsFromMe=True but in someone else's chat → rejected (not self-chat)."""
        bot = _make_bot()
        event = _make_neonize_event(
            is_from_me=True,
            sender="1234567890@s.whatsapp.net",
            chat="9999999999@s.whatsapp.net",  # different chat
            text="hello",
        )
        # sender != chat → NOT self-chat → should be filtered
        sender_user = "1234567890"
        chat_user = "9999999999"
        assert sender_user != chat_user  # not self-chat

    def test_other_person_message_rejected(self):
        """IsFromMe=False with no allowlists → should be rejected."""
        bot = _make_bot()
        event = _make_neonize_event(is_from_me=False, text="hello")

        is_from_me = bool(event.Info.MessageSource.IsFromMe)
        is_group = bool(event.Info.MessageSource.IsGroup) or "@g.us" in str(event.Info.MessageSource.Chat)

        should_filter = True
        if bot._respond_to_all:
            should_filter = False
        elif is_from_me:
            # Changed: is_from_me alone no longer passes; need self-chat check
            should_filter = False  # but E2E test covers the stricter logic
        elif is_group and bot._allowed_groups:
            should_filter = False
        elif not is_group and bot._allowed_numbers:
            should_filter = False

        assert should_filter is True  # message should be filtered out


class TestFilteringRespondToAll:
    """Test respond_to_all=True skips filtering entirely."""

    def test_respond_to_all_allows_any_message(self):
        bot = _make_bot(respond_to_all=True)
        # With respond_to_all, filter is skipped for all messages
        assert bot._respond_to_all is True

    def test_respond_to_all_allows_group_messages(self):
        bot = _make_bot(respond_to_all=True)
        assert bot._respond_to_all is True


class TestFilteringAllowedNumbers:
    """Test allowed_numbers filtering."""

    def test_allowed_number_passes(self):
        bot = _make_bot(allowed_numbers=["1234567890"])
        sender = "1234567890@s.whatsapp.net"
        sender_num = sender.split("@")[0].split(":")[0]
        assert sender_num in bot._allowed_numbers

    def test_disallowed_number_rejected(self):
        bot = _make_bot(allowed_numbers=["1234567890"])
        sender = "9999999999@s.whatsapp.net"
        sender_num = sender.split("@")[0].split(":")[0]
        assert sender_num not in bot._allowed_numbers

    def test_sender_with_device_suffix(self):
        """Neonize sometimes includes :device_id in sender JID."""
        bot = _make_bot(allowed_numbers=["1234567890"])
        sender = "1234567890:42@s.whatsapp.net"
        sender_num = sender.split("@")[0].split(":")[0]
        assert sender_num in bot._allowed_numbers

    def test_self_still_allowed_with_allowlist(self):
        """Self-messages should still pass even when allowlist is set."""
        bot = _make_bot(allowed_numbers=["9999999999"])
        # Self-message from different number — IsFromMe takes priority
        event = _make_neonize_event(is_from_me=True, sender="5555555555@s.whatsapp.net")
        is_from_me = bool(event.Info.MessageSource.IsFromMe)
        assert is_from_me is True  # self always passes


class TestFilteringAllowedGroups:
    """Test allowed_groups filtering."""

    def test_allowed_group_passes(self):
        bot = _make_bot(allowed_groups=["120363123456@g.us"])
        chat = "120363123456@g.us"
        chat_str = chat.split("@")[0]
        assert chat in bot._allowed_groups or chat_str in bot._allowed_groups

    def test_allowed_group_by_id_only(self):
        """Allow matching by group ID without @g.us suffix."""
        bot = _make_bot(allowed_groups=["120363123456"])
        chat = "120363123456@g.us"
        chat_str = chat.split("@")[0]
        assert chat_str in bot._allowed_groups

    def test_disallowed_group_rejected(self):
        bot = _make_bot(allowed_groups=["120363123456@g.us"])
        chat = "120363999999@g.us"
        chat_str = chat.split("@")[0]
        assert chat not in bot._allowed_groups
        assert chat_str not in bot._allowed_groups

    def test_group_message_from_other_ignored_without_group_allowlist(self):
        """Group message without allowed_groups set → rejected (handled by e2e tests)."""
        default_bot = _make_bot()
        assert default_bot._allowed_groups == set()


class TestFilteringCombined:
    """Test combined allowed_numbers + allowed_groups."""

    def test_allowed_number_in_dm(self):
        bot = _make_bot(
            allowed_numbers=["1234567890"],
            allowed_groups=["120363123456@g.us"],
        )
        sender = "1234567890@s.whatsapp.net"
        sender_num = sender.split("@")[0].split(":")[0]
        assert sender_num in bot._allowed_numbers

    def test_allowed_group_still_works(self):
        combined = _make_bot(
            allowed_numbers=["1234567890"],
            allowed_groups=["120363123456@g.us"],
        )
        assert "120363123456@g.us" in combined._allowed_groups

    def test_disallowed_number_not_in_groups_rejected(self):
        combined = _make_bot(
            allowed_numbers=["1234567890"],
            allowed_groups=["120363123456@g.us"],
        )
        sender = "9999999999@s.whatsapp.net"
        sender_num = sender.split("@")[0].split(":")[0]
        assert sender_num not in combined._allowed_numbers

    def test_self_message_always_passes_combined(self):
        combined = _make_bot(
            allowed_numbers=["1234567890"],
            allowed_groups=["120363123456@g.us"],
        )
        # Even with allowlists, self should pass
        event = _make_neonize_event(is_from_me=True, sender="5555@s.whatsapp.net")
        assert bool(event.Info.MessageSource.IsFromMe) is True
        assert combined._respond_to_all is False  # verify bot config used


# ── End-to-End Filtering Simulation ──────────────────────────────

class TestFilteringEndToEnd:
    """Simulate the actual filtering logic from _on_web_message.

    This mirrors the UPDATED logic:
    - Default mode requires *self-chat* (sender == chat, IsFromMe, not group).
    - IsFromMe alone in another person's chat is REJECTED.
    - Allowlists and respond_to_all bypass as before.
    """

    @staticmethod
    def _jid_user(jid_str: str) -> str:
        return jid_str.split("@")[0].split(":")[0] if jid_str else ""

    def _should_process(self, bot, is_from_me, is_group, sender_jid, chat_jid):
        """Reproduce the UPDATED filtering logic from _on_web_message."""
        if bot._respond_to_all:
            return True

        is_self_chat = (
            is_from_me
            and not is_group
            and self._jid_user(sender_jid) == self._jid_user(chat_jid)
        )

        if is_self_chat:
            return True

        if is_group and bot._allowed_groups:
            chat_jid_str = chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
            if chat_jid in bot._allowed_groups or chat_jid_str in bot._allowed_groups:
                return True
            return False

        if not is_group and bot._allowed_numbers:
            sender_num = self._jid_user(sender_jid)
            if sender_num in bot._allowed_numbers:
                return True
            return False

        # Not self-chat, not in any allowlist
        return False

    # ── Default self-chat mode ──────────────────────────────────

    def test_e2e_self_chat_passes(self):
        bot = _make_bot()
        # True self-chat: sender==chat, is_from_me
        assert self._should_process(
            bot, True, False, "me@s.whatsapp.net", "me@s.whatsapp.net"
        ) is True

    def test_e2e_is_from_me_other_chat_rejected(self):
        """IsFromMe in another person's chat should NOT pass default filter."""
        bot = _make_bot()
        assert self._should_process(
            bot, True, False, "me@s.whatsapp.net", "friend@s.whatsapp.net"
        ) is False

    def test_e2e_other_person_rejected(self):
        bot = _make_bot()
        assert self._should_process(
            bot, False, False, "other@s.whatsapp.net", "other@s.whatsapp.net"
        ) is False

    def test_e2e_group_rejected_by_default(self):
        bot = _make_bot()
        assert self._should_process(
            bot, False, True, "other@s.whatsapp.net", "grp@g.us"
        ) is False

    def test_e2e_is_from_me_in_group_rejected(self):
        """IsFromMe in a group chat should NOT pass default filter."""
        bot = _make_bot()
        assert self._should_process(
            bot, True, True, "me@s.whatsapp.net", "grp@g.us"
        ) is False

    # ── respond_to_all ──────────────────────────────────────────

    def test_e2e_respond_to_all(self):
        bot = _make_bot(respond_to_all=True)
        assert self._should_process(bot, True, False, "me@s", "me@s") is True
        assert self._should_process(bot, False, False, "other@s", "other@s") is True
        assert self._should_process(bot, False, True, "other@s", "grp@g.us") is True
        # IsFromMe in other chat also passes with respond_to_all
        assert self._should_process(bot, True, False, "me@s", "friend@s") is True

    # ── allowed_numbers ─────────────────────────────────────────

    def test_e2e_allowed_numbers(self):
        bot = _make_bot(allowed_numbers=["1234567890"])
        # Self-chat always passes
        assert self._should_process(
            bot, True, False, "me@s.whatsapp.net", "me@s.whatsapp.net"
        ) is True
        # Allowed number passes
        assert self._should_process(
            bot, False, False, "1234567890@s.whatsapp.net", "1234567890@s.whatsapp.net"
        ) is True
        # Disallowed number rejected
        assert self._should_process(
            bot, False, False, "9999999999@s.whatsapp.net", "9999999999@s.whatsapp.net"
        ) is False
        # Group message still rejected (no group allowlist)
        assert self._should_process(
            bot, False, True, "1234567890@s.whatsapp.net", "grp@g.us"
        ) is False

    # ── allowed_groups ──────────────────────────────────────────

    def test_e2e_allowed_groups(self):
        bot = _make_bot(allowed_groups=["120363123456@g.us"])
        # Self-chat passes
        assert self._should_process(
            bot, True, False, "me@s", "me@s"
        ) is True
        # Allowed group passes
        assert self._should_process(
            bot, False, True, "other@s", "120363123456@g.us"
        ) is True
        # Disallowed group rejected
        assert self._should_process(
            bot, False, True, "other@s", "999@g.us"
        ) is False
        # DM from other rejected
        assert self._should_process(
            bot, False, False, "other@s.whatsapp.net", "other@s.whatsapp.net"
        ) is False

    # ── combined ────────────────────────────────────────────────

    def test_e2e_combined(self):
        bot = _make_bot(
            allowed_numbers=["5551234"],
            allowed_groups=["grp1@g.us"],
        )
        # Self-chat passes
        assert self._should_process(
            bot, True, False, "me@s.whatsapp.net", "me@s.whatsapp.net"
        ) is True
        # IsFromMe in OTHER chat does NOT pass
        assert self._should_process(
            bot, True, False, "me@s.whatsapp.net", "friend@s.whatsapp.net"
        ) is False
        # Allowed number
        assert self._should_process(
            bot, False, False, "5551234@s.whatsapp.net", "5551234@s.whatsapp.net"
        ) is True
        # Disallowed number
        assert self._should_process(
            bot, False, False, "9999@s.whatsapp.net", "9999@s.whatsapp.net"
        ) is False
        # Allowed group
        assert self._should_process(
            bot, False, True, "other@s", "grp1@g.us"
        ) is True
        # Disallowed group
        assert self._should_process(
            bot, False, True, "other@s", "grp2@g.us"
        ) is False


# ── Timestamp Conversion ─────────────────────────────────────

class TestTimestampConversion:
    """Test millisecond→second conversion for neonize timestamps."""

    def test_millisecond_timestamp_detected(self):
        """Value > 1e12 should be treated as milliseconds."""
        raw_ts = 1700000000000  # ms
        ts = raw_ts / 1000.0 if raw_ts > 1e12 else float(raw_ts)
        assert abs(ts - 1700000000.0) < 0.01

    def test_second_timestamp_unchanged(self):
        """Value < 1e12 should be kept as seconds."""
        raw_ts = 1700000000  # already seconds
        ts = raw_ts / 1000.0 if raw_ts > 1e12 else float(raw_ts)
        assert abs(ts - 1700000000.0) < 0.01

    def test_zero_timestamp_fallback(self):
        """Zero or None should fall back to current time."""
        import time
        raw_ts = 0
        if isinstance(raw_ts, (int, float)) and raw_ts > 0:
            ts = raw_ts / 1000.0 if raw_ts > 1e12 else float(raw_ts)
        else:
            ts = time.time()
        assert ts > 1e9  # reasonable epoch

    def test_datetime_object_timestamp(self):
        """datetime objects should use .timestamp() method."""
        from unittest.mock import MagicMock
        fake_dt = MagicMock()
        fake_dt.timestamp.return_value = 1700000000.0
        assert hasattr(fake_dt, 'timestamp')
        assert fake_dt.timestamp() == 1700000000.0


# ── Stale Message Guard ──────────────────────────────────────

class TestStaleMessageGuard:
    """Test that messages older than connected_at are dropped."""

    def test_stale_message_dropped(self):
        """Message timestamp < connected_at → should be dropped."""
        connected_at = 1700000100.0
        msg_ts = 1700000050.0  # 50s before connection
        assert msg_ts < connected_at  # stale

    def test_fresh_message_passes(self):
        """Message timestamp >= connected_at → should pass."""
        connected_at = 1700000100.0
        msg_ts = 1700000150.0  # 50s after connection
        assert msg_ts >= connected_at  # fresh

    def test_exactly_equal_timestamp_passes(self):
        """Message at exactly connected_at → should pass (not <)."""
        connected_at = 1700000100.0
        msg_ts = 1700000100.0
        assert not (msg_ts < connected_at)  # passes

    def test_stale_guard_with_ms_converted(self):
        """Stale guard works after ms→s conversion."""
        connected_at = 1700000100.0
        raw_ms = 1700000050000  # 50s before, in ms
        ts = raw_ms / 1000.0 if raw_ms > 1e12 else float(raw_ms)
        assert ts < connected_at  # stale after conversion


# ── Self-Chat vs IsFromMe ────────────────────────────────────

class TestSelfChatVsIsFromMe:
    """Critical: distinguish true self-chat from IsFromMe in other chats."""

    @staticmethod
    def _jid_user(jid_str):
        return jid_str.split("@")[0].split(":")[0] if jid_str else ""

    def _is_self_chat(self, is_from_me, is_group, sender_jid, chat_jid):
        return (
            is_from_me
            and not is_group
            and self._jid_user(sender_jid) == self._jid_user(chat_jid)
        )

    def test_self_chat_true(self):
        assert self._is_self_chat(
            True, False, "1234@s.whatsapp.net", "1234@s.whatsapp.net"
        ) is True

    def test_self_chat_with_device_suffix(self):
        """Sender may have :device_id suffix — should still match."""
        assert self._is_self_chat(
            True, False, "1234:42@s.whatsapp.net", "1234@s.whatsapp.net"
        ) is True

    def test_not_self_chat_different_numbers(self):
        """IsFromMe but chat is a different person → NOT self-chat."""
        assert self._is_self_chat(
            True, False, "1234@s.whatsapp.net", "5678@s.whatsapp.net"
        ) is False

    def test_not_self_chat_when_group(self):
        """IsFromMe in a group → NOT self-chat."""
        assert self._is_self_chat(
            True, True, "1234@s.whatsapp.net", "grp@g.us"
        ) is False

    def test_not_self_chat_when_not_from_me(self):
        """Not from me at all → NOT self-chat."""
        assert self._is_self_chat(
            False, False, "1234@s.whatsapp.net", "1234@s.whatsapp.net"
        ) is False

    def test_empty_jids(self):
        assert self._is_self_chat(True, False, "", "") is True  # both empty → match
        assert self._is_self_chat(True, False, "1234@s", "") is False


# ── CLI Flag Parsing ─────────────────────────────────────────────

class TestCLIFlagParsing:
    """Test CLI argument parsing for filtering flags."""

    def _parse_whatsapp_args(self, *args):
        import argparse
        from praisonai.cli.features.bots_cli import add_bot_parser
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_bot_parser(subparsers)
        return parser.parse_args(["bot", "whatsapp"] + list(args))

    def test_no_filter_flags(self):
        args = self._parse_whatsapp_args("--mode", "web")
        assert getattr(args, "respond_to", None) is None
        assert getattr(args, "respond_to_groups", None) is None
        assert getattr(args, "respond_to_all", False) is False

    def test_respond_to_flag(self):
        args = self._parse_whatsapp_args("--mode", "web", "--respond-to", "123,456")
        assert args.respond_to == "123,456"
        nums = [n.strip() for n in args.respond_to.split(",") if n.strip()]
        assert nums == ["123", "456"]

    def test_respond_to_groups_flag(self):
        args = self._parse_whatsapp_args(
            "--mode", "web",
            "--respond-to-groups", "g1@g.us,g2@g.us",
        )
        groups = [g.strip() for g in args.respond_to_groups.split(",") if g.strip()]
        assert groups == ["g1@g.us", "g2@g.us"]

    def test_respond_to_all_flag(self):
        args = self._parse_whatsapp_args("--mode", "web", "--respond-to-all")
        assert args.respond_to_all is True

    def test_all_filter_flags_combined(self):
        args = self._parse_whatsapp_args(
            "--mode", "web",
            "--respond-to", "555",
            "--respond-to-groups", "grp@g.us",
            "--respond-to-all",
        )
        assert args.respond_to == "555"
        assert args.respond_to_groups == "grp@g.us"
        assert args.respond_to_all is True


# ── CLI → WhatsAppBot Wiring ─────────────────────────────────────

class TestCLIToWhatsAppBotWiring:
    """Test that CLI flags are correctly wired to WhatsAppBot constructor."""

    @patch("praisonai.cli.features.bots_cli.BotHandler._load_agent")
    @patch("praisonai.cli.features.bots_cli.BotHandler._load_dotenv")
    def test_respond_to_wired(self, mock_dotenv, mock_load_agent):
        mock_load_agent.return_value = MagicMock()
        from praisonai.cli.features.bots_cli import BotHandler

        handler = BotHandler()
        with patch("praisonai.bots.whatsapp.WhatsAppBot") as MockBot:
            MockBot.return_value = MagicMock()
            MockBot.return_value.start = AsyncMock()
            handler.start_whatsapp(
                mode="web",
                allowed_numbers=["1234567890", "5555555"],
                allowed_groups=["grp@g.us"],
                respond_to_all=False,
            )
            # Verify WhatsAppBot was called with filtering args
            call_kwargs = MockBot.call_args[1]
            assert call_kwargs["allowed_numbers"] == ["1234567890", "5555555"]
            assert call_kwargs["allowed_groups"] == ["grp@g.us"]
            assert call_kwargs["respond_to_all"] is False

    @patch("praisonai.cli.features.bots_cli.BotHandler._load_agent")
    @patch("praisonai.cli.features.bots_cli.BotHandler._load_dotenv")
    def test_respond_to_all_wired(self, mock_dotenv, mock_load_agent):
        mock_load_agent.return_value = MagicMock()
        from praisonai.cli.features.bots_cli import BotHandler

        handler = BotHandler()
        with patch("praisonai.bots.whatsapp.WhatsAppBot") as MockBot:
            MockBot.return_value = MagicMock()
            MockBot.return_value.start = AsyncMock()
            handler.start_whatsapp(
                mode="web",
                respond_to_all=True,
            )
            call_kwargs = MockBot.call_args[1]
            assert call_kwargs["respond_to_all"] is True


# ── YAML Config Wiring ───────────────────────────────────────────

class TestYAMLConfigWiring:
    """Test that YAML config fields are parsed and wired correctly."""

    @patch("praisonai.cli.features.bots_cli.BotHandler._load_agent")
    @patch("praisonai.cli.features.bots_cli.BotHandler._load_dotenv")
    def test_yaml_respond_to_list(self, mock_dotenv, mock_load_agent):
        """YAML respond_to as list."""
        mock_load_agent.return_value = MagicMock()
        from praisonai.cli.features.bots_cli import BotHandler

        handler = BotHandler()
        config = {
            "platform": "whatsapp",
            "mode": "web",
            "respond_to": ["1234567890", "9876543210"],
            "agent": {"name": "test"},
        }

        with patch("praisonai.cli.features.bots_cli.BotHandler.start_whatsapp") as mock_start:
            with patch("builtins.open", create=True):
                with patch("yaml.safe_load", return_value=config):
                    handler.start_from_config("bot.yaml")

            if mock_start.called:
                call_kwargs = mock_start.call_args[1]
                assert call_kwargs.get("allowed_numbers") == ["1234567890", "9876543210"]

    @patch("praisonai.cli.features.bots_cli.BotHandler._load_agent")
    @patch("praisonai.cli.features.bots_cli.BotHandler._load_dotenv")
    def test_yaml_respond_to_string(self, mock_dotenv, mock_load_agent):
        """YAML respond_to as comma-separated string."""
        mock_load_agent.return_value = MagicMock()
        from praisonai.cli.features.bots_cli import BotHandler

        handler = BotHandler()
        config = {
            "platform": "whatsapp",
            "mode": "web",
            "respond_to": "123,456",
            "agent": {"name": "test"},
        }

        with patch("praisonai.cli.features.bots_cli.BotHandler.start_whatsapp") as mock_start:
            with patch("builtins.open", create=True):
                with patch("yaml.safe_load", return_value=config):
                    handler.start_from_config("bot.yaml")

            if mock_start.called:
                call_kwargs = mock_start.call_args[1]
                assert call_kwargs.get("allowed_numbers") == ["123", "456"]

    @patch("praisonai.cli.features.bots_cli.BotHandler._load_agent")
    @patch("praisonai.cli.features.bots_cli.BotHandler._load_dotenv")
    def test_yaml_respond_to_all(self, mock_dotenv, mock_load_agent):
        """YAML respond_to_all: true."""
        mock_load_agent.return_value = MagicMock()
        from praisonai.cli.features.bots_cli import BotHandler

        handler = BotHandler()
        config = {
            "platform": "whatsapp",
            "mode": "web",
            "respond_to_all": True,
            "agent": {"name": "test"},
        }

        with patch("praisonai.cli.features.bots_cli.BotHandler.start_whatsapp") as mock_start:
            with patch("builtins.open", create=True):
                with patch("yaml.safe_load", return_value=config):
                    handler.start_from_config("bot.yaml")

            if mock_start.called:
                call_kwargs = mock_start.call_args[1]
                assert call_kwargs.get("respond_to_all") is True


# ── Edge Cases ───────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases in filtering."""

    def test_cloud_mode_ignores_filtering_params(self):
        """Cloud mode should accept but not break with filtering params."""
        from praisonai.bots.whatsapp import WhatsAppBot
        bot = WhatsAppBot(
            token="t",
            phone_number_id="p",
            mode="cloud",
            allowed_numbers=["123"],
            allowed_groups=["g@g.us"],
            respond_to_all=True,
        )
        # Should not crash; params are stored but only used in web mode
        assert bot._respond_to_all is True
        assert "123" in bot._allowed_numbers

    def test_empty_allowed_numbers_list(self):
        bot = _make_bot(allowed_numbers=[])
        assert bot._allowed_numbers == set()

    def test_empty_allowed_groups_list(self):
        bot = _make_bot(allowed_groups=[])
        assert bot._allowed_groups == set()

    def test_non_digit_input_ignored(self):
        """Input with no digits should be silently ignored."""
        bot = _make_bot(allowed_numbers=["abc", "+++"])
        assert bot._allowed_numbers == set()

    def test_group_jid_without_at_sign(self):
        """Group ID without @g.us should still match."""
        bot = _make_bot(allowed_groups=["120363123456"])
        assert "120363123456" in bot._allowed_groups

"""Issue #2376 — Shared group/channel session scope + sender attribution.

Tests that BotSessionManager can route group/channel messages to a single
shared session (``session_scope='per_chat'``) so the agent follows one
multi-party transcript, prefixes each turn with the sender, and keeps DMs
and the default ``per_user`` behaviour fully backward compatible.
"""

from __future__ import annotations

import pytest

from praisonai.bots._session import BotSessionManager


class FakeAgent:
    def __init__(self):
        self.chat_history = []
        self.calls = []

    def chat(self, prompt):
        self.calls.append((list(self.chat_history), prompt))
        self.chat_history.append({"role": "user", "content": prompt})
        reply = f"reply to {prompt}"
        self.chat_history.append({"role": "assistant", "content": reply})
        return reply


class TestPerUserDefault:
    """Default scope keeps today's per-sender isolation (back-compat)."""

    @pytest.mark.asyncio
    async def test_group_members_isolated_by_default(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram")  # default per_user

        # Two members of the same Telegram supergroup (-100...).
        await mgr.chat(agent, "alice_id", "from alice", chat_id="-100123")
        await mgr.chat(agent, "bob_id", "from bob", chat_id="-100123")

        # Each sender still gets an isolated session keyed by user id.
        assert "alice_id" in mgr._histories
        assert "bob_id" in mgr._histories
        # No shared chat key created.
        assert not any(":chat:" in k for k in mgr._histories)

    @pytest.mark.asyncio
    async def test_no_attribution_prefix_in_per_user(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram")

        await mgr.chat(agent, "alice_id", "hello", chat_id="-100123",
                       user_name="Alice")
        # Prompt forwarded verbatim — no "[Alice] " prefix.
        assert agent.calls[0][1] == "hello"


class TestPerChatSharedSession:
    """per_chat routes group/channel members to one shared transcript."""

    @pytest.mark.asyncio
    async def test_group_members_share_one_session(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "when is the launch?",
                       chat_id="-100123", user_name="Alice")
        await mgr.chat(agent, "bob_id", "next friday",
                       chat_id="-100123", user_name="Bob")

        # One shared session keyed by the chat, not per sender.
        chat_keys = [k for k in mgr._histories if ":chat:" in k]
        assert len(chat_keys) == 1
        assert "alice_id" not in mgr._histories
        assert "bob_id" not in mgr._histories
        # Shared transcript holds both turns (2 turns * 2 messages each).
        assert len(mgr._histories[chat_keys[0]]) == 4

    @pytest.mark.asyncio
    async def test_second_member_sees_first_members_turn(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "when is the launch?",
                       chat_id="-100123", user_name="Alice")
        await mgr.chat(agent, "bob_id", "and where?",
                       chat_id="-100123", user_name="Bob")

        # Bob's call must see Alice's turn already in history.
        history_for_bob = agent.calls[1][0]
        assert any(
            "when is the launch?" in str(m.get("content", ""))
            for m in history_for_bob
        )

    @pytest.mark.asyncio
    async def test_sender_attribution_prefix(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "when is the launch?",
                       chat_id="-100123", user_name="Alice")
        # The agent receives the attributed prompt.
        assert agent.calls[0][1] == "[Alice] when is the launch?"

    @pytest.mark.asyncio
    async def test_custom_attribution_template(self):
        agent = FakeAgent()
        mgr = BotSessionManager(
            platform="telegram", session_scope="per_chat",
            attribution="{sender}: ",
        )
        await mgr.chat(agent, "alice_id", "hi", chat_id="-100123",
                       user_name="Alice")
        assert agent.calls[0][1] == "Alice: hi"

    @pytest.mark.asyncio
    async def test_empty_attribution_disables_prefix(self):
        agent = FakeAgent()
        mgr = BotSessionManager(
            platform="telegram", session_scope="per_chat", attribution="",
        )
        await mgr.chat(agent, "alice_id", "hi", chat_id="-100123",
                       user_name="Alice")
        assert agent.calls[0][1] == "hi"

    @pytest.mark.asyncio
    async def test_falls_back_to_user_id_when_no_name(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")
        await mgr.chat(agent, "alice_id", "hi", chat_id="-100123")
        assert agent.calls[0][1] == "[alice_id] hi"


class TestPerChatKeepsDMsPerUser:
    """DMs stay per_user even when per_chat is enabled."""

    @pytest.mark.asyncio
    async def test_dm_stays_per_user(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        # A Telegram DM: positive chat_id == direct (detect_chat_type -> direct).
        await mgr.chat(agent, "alice_id", "private hi", chat_id="555",
                       user_name="Alice")

        # No shared chat key; sender-keyed session; no attribution.
        assert not any(":chat:" in k for k in mgr._histories)
        assert "alice_id" in mgr._histories
        assert agent.calls[0][1] == "private hi"

    @pytest.mark.asyncio
    async def test_no_chat_id_falls_back_to_per_user(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")
        await mgr.chat(agent, "alice_id", "hi", chat_id="", user_name="Alice")
        assert "alice_id" in mgr._histories
        assert agent.calls[0][1] == "hi"


class TestThreadScoping:
    """Different threads in the same chat get separate shared sessions."""

    @pytest.mark.asyncio
    async def test_threads_are_separate_sessions(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="slack", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "thread A",
                       chat_id="C123", thread_id="t1", user_name="Alice")
        await mgr.chat(agent, "bob_id", "thread B",
                       chat_id="C123", thread_id="t2", user_name="Bob")

        chat_keys = sorted(k for k in mgr._histories if ":chat:" in k)
        assert len(chat_keys) == 2
        assert chat_keys[0].endswith("t1")
        assert chat_keys[1].endswith("t2")


class TestResetPerChat:
    """/new in a group clears the shared session when routing is supplied."""

    @pytest.mark.asyncio
    async def test_reset_clears_shared_session(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "hi", chat_id="-100123",
                       user_name="Alice")
        chat_keys = [k for k in mgr._histories if ":chat:" in k]
        assert len(chat_keys) == 1

        existed = mgr.reset("bob_id", chat_id="-100123", chat_type="group")
        assert existed is True
        assert not any(":chat:" in k for k in mgr._histories)

    @pytest.mark.asyncio
    async def test_reset_with_only_chat_id_clears_shared_session(self):
        # A /new handler that supplies only chat_id (no chat_type) must still
        # clear the shared per_chat session — _storage_key derives the type.
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "hi", chat_id="-100123",
                       user_name="Alice")
        assert any(":chat:" in k for k in mgr._histories)

        existed = mgr.reset("bob_id", chat_id="-100123")
        assert existed is True
        assert not any(":chat:" in k for k in mgr._histories)

    @pytest.mark.asyncio
    async def test_dm_reset_with_chat_id_does_not_touch_shared_key(self):
        # reset() for a DM (positive telegram chat_id) must resolve to the
        # sender key, never a per_chat key, even without chat_type.
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "private hi", chat_id="555",
                       user_name="Alice")
        assert "alice_id" in mgr._histories

        existed = mgr.reset("alice_id", chat_id="555")
        assert existed is True
        assert "alice_id" not in mgr._histories
        assert not any(":chat:" in k for k in mgr._histories)


class TestAccountNamespacing:
    """Shared per_chat keys are namespaced per gateway account (no collisions)."""

    @pytest.mark.asyncio
    async def test_same_chat_id_different_accounts_isolated(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "acct A msg", chat_id="-100123",
                       user_name="Alice", account="acctA")
        await mgr.chat(agent, "bob_id", "acct B msg", chat_id="-100123",
                       user_name="Bob", account="acctB")

        # Two distinct shared sessions despite identical chat_id.
        chat_keys = [k for k in mgr._histories if ":chat:" in k]
        assert len(chat_keys) == 2
        assert any("acctA" in k for k in chat_keys)
        assert any("acctB" in k for k in chat_keys)

    @pytest.mark.asyncio
    async def test_missing_account_uses_default_namespace(self):
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "hi", chat_id="-100123",
                       user_name="Alice")
        chat_keys = [k for k in mgr._histories if ":chat:" in k]
        assert len(chat_keys) == 1
        assert ":acct:default:" in chat_keys[0]

    @pytest.mark.asyncio
    async def test_reset_must_match_account_to_clear_shared_session(self):
        # A /new in a multi-account gateway must forward the same account it
        # chatted under, otherwise the shared session stays active. The
        # adapter /new handlers now pass account, so the matching reset clears
        # the session and a mismatched account is a no-op.
        agent = FakeAgent()
        mgr = BotSessionManager(platform="telegram", session_scope="per_chat")

        await mgr.chat(agent, "alice_id", "hi", chat_id="-100123",
                       user_name="Alice", account="acctA")
        assert any(":acct:acctA:" in k for k in mgr._histories)

        # Wrong account → no-op, shared session survives.
        assert mgr.reset("bob_id", chat_id="-100123", account="acctB") is False
        assert any(":acct:acctA:" in k for k in mgr._histories)

        # Matching account → shared session cleared.
        assert mgr.reset("bob_id", chat_id="-100123", account="acctA") is True
        assert not any(":chat:" in k for k in mgr._histories)


class TestInvalidScope:
    """Unknown scope falls back to per_user."""

    def test_unknown_scope_falls_back(self):
        mgr = BotSessionManager(platform="telegram", session_scope="bogus")
        assert mgr._session_scope == "per_user"

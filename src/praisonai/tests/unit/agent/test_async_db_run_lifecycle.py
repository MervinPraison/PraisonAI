"""Core async turns must use PraisonAIDB's existing async lifecycle hooks."""

import asyncio

from praisonaiagents import Agent, MemoryConfig
from praisonai.db.adapter import PraisonAIDB
from praisonai.persistence.conversation.base import ConversationMessage, ConversationSession

TOOL_CALLS = [{"id": "call-1", "type": "function", "function": {"name": "check_status", "arguments": "{}"}}]


class AsyncConversation:
    async def get_session(self, session_id):
        return ConversationSession(session_id=session_id, user_id="operator")

    async def get_messages(self, session_id):
        return [
            ConversationMessage(session_id=session_id, role="assistant", content="", tool_calls=TOOL_CALLS),
            ConversationMessage(session_id=session_id, role="tool", content="ready", tool_call_id="call-1"),
            ConversationMessage(session_id=session_id, role="assistant", content="saved answer"),
        ]

    async def create_session(self, session):
        raise AssertionError("An existing session must be resumed")


class AsyncState:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value


def test_async_store_resumes_history_and_completes_run(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    state = AsyncState()
    db = PraisonAIDB._from_stores(conversation_store=AsyncConversation(), state_store=state)
    agent = Agent(name="resumed", rules=False, reflection=False, output="silent",
                  memory=MemoryConfig(db=db, session_id="saved-session", user_id="operator"))

    async def respond(**kwargs):
        assert agent.chat_history == [
            {"role": "assistant", "content": "", "tool_calls": TOOL_CALLS},
            {"role": "tool", "content": "ready", "tool_call_id": "call-1"},
            {"role": "assistant", "content": "saved answer"},
        ]
        return "new answer"

    monkeypatch.setattr(agent, "_achat_impl", respond)
    assert asyncio.run(agent.achat("new question")) == "new answer"
    runs = [value for key, value in state.data.items() if key.startswith("run:")]
    assert len(runs) == 1
    assert runs[0]["input_content"] == "new question"
    assert runs[0]["output_content"] == "new answer"
    assert runs[0]["status"] == "completed"
    assert runs[0]["metrics"]["duration_ms"] >= 0
    assert runs[0]["started_at"] <= runs[0]["ended_at"]

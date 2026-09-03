"""The custom-LLM streaming branch must compact too.

#4729 added context compaction to `_start_stream_impl`, but only inside the
OpenAI-client branch. Every agent routed through the custom-LLM path still
streamed its entire history uncompacted, so a long conversation was sent in
full and rejected by the provider for exceeding the context window.

The trigger is the routing flag, not the vendor: `llm="openai/gpt-4o-mini"`
takes this branch too, so this was not limited to Anthropic or Ollama users.

test_stream_context_management.py pins the OpenAI branch and hardcodes
`_using_custom_llm = False`, which is exactly why it stayed green while this
half was broken.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents import Agent


def _agent_with_history(messages: int, words: int):
    agent = Agent(name="t", instructions="x", llm="openai/gpt-4o-mini",
                  tools=[lambda x: x], context=True)
    agent.chat_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "filler " * words}
        for i in range(messages)
    ]
    sent = {}

    def fake_stream(**kwargs):
        sent["history"] = list(kwargs.get("chat_history") or [])
        yield "ok"

    agent._using_custom_llm = True
    agent.llm_instance = type("L", (), {"get_response_stream": staticmethod(fake_stream)})()
    return agent, sent


def _drain(agent, sent):
    list(agent._start_stream_impl("hello", stream=True))
    return sent.get("history")


class TestCustomLlmStreamCompaction:

    def test_an_oversized_history_is_compacted_before_sending(self):
        """Without this, 801 messages (~1.7M tokens) go at a 128k-token model."""
        agent, sent = _agent_with_history(800, 1200)
        history = _drain(agent, sent)
        assert history is not None, "the custom-LLM stream was never called"
        assert len(history) < 801, (
            "the whole history was streamed uncompacted; the provider would "
            "reject this turn for exceeding the context window"
        )

    def test_a_small_history_is_left_alone(self):
        """Compaction must not fire when it is not needed."""
        agent, sent = _agent_with_history(6, 5)
        history = _drain(agent, sent)
        assert len(history) == 7, "a short history was compacted unnecessarily"

    def test_the_context_manager_is_actually_configured_here(self):
        """Guards the premise: tools present auto-enable context management."""
        agent, _ = _agent_with_history(4, 5)
        assert agent.context_manager is not None

    def test_the_system_prompt_still_reaches_the_provider(self):
        """The prompt is built once now and reused; it must still be passed."""
        agent = Agent(name="t", instructions="be terse", llm="openai/gpt-4o-mini",
                      tools=[lambda x: x], context=True)
        agent.chat_history = []
        seen = {}

        def fake_stream(**kwargs):
            seen.update(kwargs)
            yield "ok"

        agent._using_custom_llm = True
        agent.llm_instance = type("L", (), {"get_response_stream": staticmethod(fake_stream)})()
        list(agent._start_stream_impl("hello", stream=True))
        assert "system_prompt" in seen
        assert seen["system_prompt"], "system_prompt was dropped when it was hoisted"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

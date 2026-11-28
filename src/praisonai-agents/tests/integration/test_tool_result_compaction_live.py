"""Opt-in Agent.start inference with repeated tool results in compacted history."""

import os

import pytest


@pytest.mark.live
def test_agent_continues_after_compacting_identical_tool_results(monkeypatch, tmp_path):
    from praisonaiagents import Agent
    from praisonaiagents.context.models import ContextConfig, OptimizerStrategy

    model = os.environ.get("PRAISONAI_TEST_MODEL")
    if not model:
        pytest.skip("Set PRAISONAI_TEST_MODEL to choose the live provider explicitly")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)

    def search(query: str) -> str:
        """Search for records matching a query."""
        return "No matching records were found. " * 10

    options = dict(
        instructions="Compare the search results in one short sentence.",
        llm={"model": model, "temperature": 0, "max_tokens": 96},
        tools=[search],
        context=ContextConfig(
            compact_threshold=0,
            strategy=OptimizerStrategy.TRUNCATE,
            keep_recent_turns=4,
        ),
        reflection=False, rules=False, output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    with Agent(**options) as agent:
        agent.context_manager._budget.history = 512
        agent.chat_history = [
            {"role": "user", "content": "Earlier context. " * 600},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": call_id, "type": "function", "function": {
                    "name": "search", "arguments": '{"query":"records"}'}}
                for call_id in ("search_a", "search_b")
            ]},
            {"role": "tool", "tool_call_id": "search_a", "content": search("records")},
            {"role": "tool", "tool_call_id": "search_b", "content": search("records")},
        ]
        processed = []
        process = agent.context_manager.process

        def capture_compaction(*args, **kwargs):
            result = process(*args, **kwargs)
            processed.append(result)
            return result

        monkeypatch.setattr(agent.context_manager, "process", capture_compaction)
        answer = agent.start("Compare the two results.")
        print("Full Agent.start output:", answer)
        assert isinstance(answer, str) and answer.strip()
        assert processed and processed[0]["optimized"]
        assert [m["tool_call_id"] for m in processed[0]["messages"]
                if m["role"] == "tool"] == ["search_a", "search_b"]

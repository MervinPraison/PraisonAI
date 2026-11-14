"""Regression tests for issue #6369.

1. Native OpenAI streaming must accumulate tool-call deltas by index.
2. ``@tool`` functions must get the same argument casting as plain functions,
   and durable runs must not inject ``idempotency_key`` they don't accept.
3. Parallel workflow fan-out must not share one Agent's chat_history.
"""
import threading
import time
from types import SimpleNamespace as NS

import pytest

from praisonaiagents.llm.openai_client import process_stream_chunks


def _chunk(tool_calls=None, content=None, finish=None):
    delta = NS(content=content, tool_calls=tool_calls, reasoning_content=None)
    return NS(choices=[NS(delta=delta, finish_reason=finish)], usage=None)


def _tc(i, id=None, name=None, args=None):
    return NS(index=i, id=id, type="function", function=NS(name=name, arguments=args))


class TestStreamToolCallAccumulation:
    def test_single_delta_keeps_arguments(self):
        r = process_stream_chunks([
            _chunk([_tc(0, "call_1", "add", '{"a": 2, "b": 3}')], finish="tool_calls"),
        ])
        calls = r.choices[0].message.tool_calls
        assert calls[0].function["arguments"] == '{"a": 2, "b": 3}'
        assert r.choices[0].finish_reason == "tool_calls"

    def test_parallel_calls_routed_by_index(self):
        r = process_stream_chunks([
            _chunk([_tc(0, "c1", "add"), _tc(1, "c2", "mul")]),
            _chunk([_tc(0, args='{"x": 1}')]),
            _chunk([_tc(1, args='{"y": 2}')], finish="tool_calls"),
        ])
        calls = r.choices[0].message.tool_calls
        assert [(c.function["name"], c.function["arguments"]) for c in calls] == [
            ("add", '{"x": 1}'),
            ("mul", '{"y": 2}'),
        ]

    def test_reused_index_with_new_id_is_a_new_call(self):
        r = process_stream_chunks([
            _chunk([_tc(0, "c1", "add", '{"x": 1}')]),
            _chunk([_tc(0, "c2", "mul", '{"y": 2}')], finish="tool_calls"),
        ])
        calls = r.choices[0].message.tool_calls
        assert [(c.id, c.function["name"], c.function["arguments"]) for c in calls] == [
            ("c1", "add", '{"x": 1}'),
            ("c2", "mul", '{"y": 2}'),
        ]

    def test_finish_reason_length_preserved_without_tools(self):
        r = process_stream_chunks([
            _chunk(content="partial..."),
            _chunk(finish="length"),
            NS(choices=[], usage=None),  # trailing usage-only chunk
        ])
        assert r.choices[0].finish_reason == "length"
        assert r.choices[0].message.tool_calls is None


class TestToolDecoratorCasting:
    @pytest.fixture
    def agent(self):
        from praisonaiagents import Agent, tool

        @tool
        def tool_add(a: int, b: int) -> int:
            """Add two ints."""
            return a + b

        @tool
        def tool_wipe(force: bool = False) -> str:
            """Dangerous op."""
            return "WIPED" if force else "skipped"

        return Agent(name="a", tools=[tool_add, tool_wipe], output="silent")

    def test_int_and_bool_are_cast(self, agent):
        assert agent.execute_tool("tool_add", {"a": "2", "b": "3"}) == 5
        assert agent.execute_tool("tool_wipe", {"force": "false"}) == "skipped"

    def test_durable_key_not_injected(self, agent, monkeypatch):
        import praisonaiagents.agent.durable as durable
        monkeypatch.setattr(durable, "get_durable_idempotency_key", lambda: "k1")
        assert agent.execute_tool("tool_add", {"a": "2", "b": "3"}) == 5


class TestParallelBranchHistoryIsolation:
    @pytest.fixture
    def recorded(self, monkeypatch):
        from openai.types.chat import ChatCompletion
        from praisonaiagents import Agent

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        log, lock = [], threading.Lock()

        def fake_cc(self, messages, *a, **k):
            users = [m["content"] for m in messages if m["role"] == "user"]
            with lock:
                log.append((users[-1], users[:-1]))
            time.sleep(0.1)
            return ChatCompletion(
                id="x", created=0, model="m", object="chat.completion",
                choices=[{"index": 0, "finish_reason": "stop",
                          "message": {"role": "assistant", "content": "ok " + users[-1]}}],
            )

        monkeypatch.setattr(Agent, "_chat_completion", fake_cc)
        return log

    def _agent(self):
        from praisonaiagents import Agent
        return Agent(name="Summ", instructions="Summarise", model="gpt-4o-mini", output="silent")

    def test_parallel_loop_items_do_not_see_siblings(self, recorded):
        from praisonaiagents import Task
        from praisonaiagents.workflows import Workflow, Loop

        agent = self._agent()
        wf = Workflow(
            steps=[Loop(Task(name="s", agent=agent, action="Doc {{item}}"),
                        over="items", parallel=True, max_workers=4)],
            variables={"items": ["A", "B", "C", "D"]},
        )
        wf.start("go")
        assert sorted(me for me, _ in recorded) == ["Doc A", "Doc B", "Doc C", "Doc D"]
        assert all(prior == [] for _, prior in recorded), recorded

    def test_parallel_shared_agent_branches_isolated(self, recorded):
        from praisonaiagents import Task
        from praisonaiagents.workflows import Workflow, Parallel

        agent = self._agent()
        wf = Workflow(steps=[Parallel(steps=[
            Task(name="p1", agent=agent, action="X1"),
            Task(name="p2", agent=agent, action="X2"),
        ])])
        wf.start("go")
        assert sorted(me for me, _ in recorded) == ["X1", "X2"]
        assert all(prior == [] for _, prior in recorded), recorded

    def test_nested_if_in_parallel_loop_isolated(self, recorded):
        from praisonaiagents import Task
        from praisonaiagents.workflows import Workflow, Loop, If

        agent = self._agent()
        body = If(condition="1 == 1",
                  then_steps=[Task(name="t", agent=agent, action="Doc {{item}}")])
        wf = Workflow(
            steps=[Loop(body, over="items", parallel=True, max_workers=4)],
            variables={"items": ["A", "B", "C"]},
        )
        wf.start("go")
        assert sorted(me for me, _ in recorded) == ["Doc A", "Doc B", "Doc C"]
        assert all(prior == [] for _, prior in recorded), recorded

    def test_branch_fork_keeps_config_and_isolates_history(self):
        agent = self._agent()
        agent.backend = sentinel = object()
        agent.custom_attr = "kept"
        agent.chat_history = [{"role": "user", "content": "earlier"}]

        fork = agent._fork_history()
        assert fork.backend is sentinel and fork.custom_attr == "kept"
        assert fork.tools is agent.tools
        assert fork.chat_history == agent.chat_history
        fork._append_to_chat_history({"role": "user", "content": "branch"})
        assert len(agent.chat_history) == 1 and len(fork.chat_history) == 2

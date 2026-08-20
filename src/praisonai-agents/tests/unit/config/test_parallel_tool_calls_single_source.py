"""ToolConfig.parallel and ExecutionConfig.parallel_tool_calls are one setting.

Every entry point must see the same value no matter which spelling was used,
and a bare ToolConfig() must not silently switch parallelism back off.
"""
import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig, ToolConfig


def _observed(**agent_kwargs):
    """Return the parallel_tool_calls each entry point forwards to the LLM."""
    agent = Agent(instructions="x", llm="openai/gpt-4o-mini", **agent_kwargs)
    llm = agent.llm_instance
    seen = {}

    def _sync(*_a, **kw):
        seen["chat"] = kw.get("parallel_tool_calls")
        return "ok"

    async def _async(*_a, **kw):
        seen["achat"] = kw.get("parallel_tool_calls")
        return "ok"

    def _stream(*_a, **kw):
        seen["iter_stream"] = kw.get("parallel_tool_calls")
        yield "ok"

    llm.get_response = _sync
    llm.get_response_async = _async
    llm.get_response_stream = _stream

    agent.chat("hi")
    asyncio.run(agent.achat("hi"))
    list(agent.iter_stream("hi"))

    async def _unified(*_a, **kw):
        seen["unified"] = kw.get("parallel_tool_calls")
        return "ok"

    llm.get_response_async = _unified
    asyncio.run(agent._unified_chat_impl("hi"))
    return seen


@pytest.mark.parametrize(
    "kwargs",
    [
        {"tool_config": ToolConfig(parallel=True)},
        {"execution": ExecutionConfig(parallel_tool_calls=True)},
        {
            "tool_config": ToolConfig(parallel=True),
            "execution": ExecutionConfig(parallel_tool_calls=True),
        },
        # The nastiest case: a bare ToolConfig() alongside an explicit
        # ExecutionConfig(parallel_tool_calls=True) used to turn parallelism off.
        {
            "tool_config": ToolConfig(),
            "execution": ExecutionConfig(parallel_tool_calls=True),
        },
    ],
    ids=["tool_config", "execution", "both", "bare_tool_config"],
)
def test_every_entry_point_sees_parallel_enabled(kwargs):
    assert _observed(**kwargs) == {
        "chat": True,
        "achat": True,
        "iter_stream": True,
        "unified": True,
    }


def test_default_is_sequential_everywhere():
    assert _observed() == {
        "chat": False,
        "achat": False,
        "iter_stream": False,
        "unified": False,
    }


def test_introspection_agrees_with_execution_config():
    agent = Agent(instructions="x", tool_config=ToolConfig(parallel=True))
    assert agent.parallel_tool_calls is True
    assert agent.execution.parallel_tool_calls is True


def test_alias_does_not_mutate_a_shared_execution_config():
    shared = ExecutionConfig()
    Agent(instructions="x", tool_config=ToolConfig(parallel=True), execution=shared)
    assert shared.parallel_tool_calls is False


def test_conflicting_spellings_raise_typeerror():
    with pytest.raises(TypeError) as excinfo:
        Agent(
            instructions="x",
            tool_config=ToolConfig(parallel=False),
            execution=ExecutionConfig(parallel_tool_calls=True),
        )
    message = str(excinfo.value)
    assert "ToolConfig.parallel" in message
    assert "ExecutionConfig.parallel_tool_calls" in message


def test_conflicting_spellings_raise_typeerror_reverse():
    # The symmetric direction: an explicit ExecutionConfig(parallel_tool_calls=False)
    # must NOT be silently overridden by ToolConfig(parallel=True).
    with pytest.raises(TypeError) as excinfo:
        Agent(
            instructions="x",
            tool_config=ToolConfig(parallel=True),
            execution=ExecutionConfig(parallel_tool_calls=False),
        )
    message = str(excinfo.value)
    assert "ToolConfig.parallel" in message
    assert "ExecutionConfig.parallel_tool_calls" in message


def test_explicit_execution_false_disables_everywhere():
    # An explicit sequential ExecutionConfig with no alias stays sequential.
    assert _observed(execution=ExecutionConfig(parallel_tool_calls=False)) == {
        "chat": False,
        "achat": False,
        "iter_stream": False,
        "unified": False,
    }

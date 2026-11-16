"""A configured completion promise must be the only success signal (#6027)."""

import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents.model_harness import ScriptedModel

NOT_DONE = (
    "I listed the files and started on the parser, but work remains: the tokenizer "
    "is still failing two tests and the CLI flag is not wired yet. Continuing next turn."
)
DONE_REPLY = "Fixed the tokenizer and wired the flag. <promise>DONE</promise>"
PROMPT = "Refactor auth module"  # stage=autonomous
DIRECT_PROMPT = "Implement feature X"  # stage=direct


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    for key in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "ANTHROPIC_BASE_URL"):
        monkeypatch.setenv(key, "http://127.0.0.1:9")
    monkeypatch.setenv("HOME", str(tmp_path))


def list_files(path: str) -> str:
    """List files in a directory."""
    return "parser.py tokenizer.py cli.py"


def _script(follow_ups=1):
    return (
        [ScriptedModel.tool_call("list_files", {"path": "."})]
        + [NOT_DONE] * follow_ups
        + [DONE_REPLY] * 3
    )


def _make(model, **autonomy):
    return Agent(
        name="worker", instructions="Do the task.", llm=model, tools=[list_files],
        output="silent", autonomy={"level": "full_auto", **autonomy},
    )


def _assert_promise(result):
    assert result.success is True
    assert result.completion_reason == "promise"
    assert "<promise>DONE</promise>" in result.output
    assert result.iterations >= 2


def test_sync_tool_completion_does_not_preempt_promise():
    r = _make(ScriptedModel(_script())).run_autonomous(
        PROMPT, completion_promise="DONE", max_iterations=5)
    _assert_promise(r)


def test_async_waits_for_promise():
    r = asyncio.run(_make(ScriptedModel(_script(2))).run_autonomous_async(
        PROMPT, completion_promise="DONE", max_iterations=5))
    _assert_promise(r)


def test_sync_direct_stage_waits_for_promise():
    r = _make(ScriptedModel([NOT_DONE, DONE_REPLY])).run_autonomous(
        DIRECT_PROMPT, completion_promise="DONE", max_iterations=5)
    _assert_promise(r)


def test_async_direct_stage_waits_for_promise():
    r = asyncio.run(_make(ScriptedModel([NOT_DONE, DONE_REPLY])).run_autonomous_async(
        DIRECT_PROMPT, completion_promise="DONE", max_iterations=5))
    _assert_promise(r)


def test_promise_never_emitted_ends_unsuccessfully():
    r = _make(ScriptedModel([NOT_DONE] * 5)).run_autonomous(
        PROMPT, completion_promise="DONE", max_iterations=3)
    assert r.success is False
    assert r.completion_reason == "max_iterations"


def test_iterative_mode_start_honours_promise():
    agent = Agent(
        name="loop_agent", instructions="Complete the task.", llm=ScriptedModel(_script()),
        tools=[list_files], output="silent",
        autonomy={"mode": "iterative", "max_iterations": 10,
                  "completion_promise": "DONE", "observe": False},
    )
    _assert_promise(agent.start(PROMPT))


def test_without_promise_tool_completion_unchanged():
    r = _make(ScriptedModel(_script())).run_autonomous(PROMPT, max_iterations=5)
    assert r.success is True
    assert r.completion_reason == "tool_completion"
    assert r.iterations == 1


def test_async_tool_path_counts_tools():
    r = asyncio.run(_make(ScriptedModel(_script(2))).run_autonomous_async(
        PROMPT, max_iterations=5))
    assert r.success is True
    assert r.completion_reason == "tool_completion"
    assert r.iterations == 1


def test_promise_tag_is_sent_to_model():
    model = ScriptedModel([DONE_REPLY])
    _make(model).run_autonomous(PROMPT, completion_promise="DONE", max_iterations=2)
    assert "<promise>DONE</promise>" in model.requests[0].last_user_message


def test_async_blocked_tool_does_not_count_as_tool_completion():
    from praisonaiagents.hooks import HookEvent, HookRegistry, HookResult

    registry = HookRegistry()

    @registry.on(HookEvent.BEFORE_TOOL)
    def deny(data):
        return HookResult.deny("blocked")

    agent = Agent(
        name="worker", instructions="Do the task.", llm=ScriptedModel(_script(2)),
        tools=[list_files], output="silent", hooks=registry,
        autonomy={"level": "full_auto"},
    )
    r = asyncio.run(agent.run_autonomous_async(PROMPT, max_iterations=3))
    assert r.completion_reason != "tool_completion"

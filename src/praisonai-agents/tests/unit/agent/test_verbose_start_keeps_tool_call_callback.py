"""A verbose terminal start() must not swap the process-global tool_call callback (G-23 step 1).

It used to install its status closure in the global registry for the run. Two
concurrent verbose agents then saw each other's tool calls, and the last one to
finish "restored" the other's dead closure, so the user's own callback was gone
for good.
"""

import io
import sys
import threading

import pytest

from praisonaiagents import Agent
from praisonaiagents import main as display


@pytest.fixture
def user_callback(monkeypatch):
    seen = []

    def cb(tool_name=None, **_):
        seen.append(tool_name)

    monkeypatch.setitem(display.sync_display_callbacks, "tool_call", cb)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    return cb, seen


def _agent_whose_chat_calls_a_tool(name, observed):
    agent = Agent(name=name, instructions="hi", output="verbose")

    def fake_chat(prompt, **kwargs):
        observed.append(display.sync_display_callbacks.get("tool_call"))
        display.execute_sync_callback("tool_call", tool_name=f"{name}-tool")
        return "done"

    agent.chat = fake_chat
    return agent


def test_global_callback_is_not_replaced_during_or_after_the_run(user_callback):
    cb, seen = user_callback
    observed = []
    assert _agent_whose_chat_calls_a_tool("a", observed).start("go") == "done"
    assert observed == [cb], "the global tool_call callback was swapped during the run"
    assert display.sync_display_callbacks["tool_call"] is cb


def test_run_status_still_sees_its_own_tool_calls(user_callback, monkeypatch):
    # The per-run status line still receives the tool call (it overrides the
    # global callback for this run only), and the user's callback is untouched.
    from rich.console import Console
    from praisonaiagents.agent import execution_mixin

    out = io.StringIO()
    monkeypatch.setattr(execution_mixin, "_get_console", lambda: lambda: Console(file=out, width=200))
    cb, seen = user_callback
    _agent_whose_chat_calls_a_tool("a", []).start("go")
    assert seen == []  # same as before: the status line owns tool_call during the run
    assert "Tools used: a-tool" in out.getvalue(), "the run's status line dropped its tool call"


def test_other_threads_keep_the_global_callback(user_callback):
    cb, seen = user_callback
    in_run, release = threading.Event(), threading.Event()
    agent = Agent(name="a", instructions="hi", output="verbose")

    def slow_chat(prompt, **kwargs):
        in_run.set()
        release.wait(10)
        return "done"

    agent.chat = slow_chat
    t = threading.Thread(target=agent.start, args=("go",))
    t.start()
    assert in_run.wait(10)
    display.execute_sync_callback("tool_call", tool_name="from-another-thread")
    release.set()
    t.join(10)
    assert seen == ["from-another-thread"]

"""The system prompt carries only guidance that applies to the agent.

* The model-family file-editing hint ("use edit_file ..." / "use
  apply_patch ...") is for agents that can edit files; every GPT or Claude
  agent got it, tools or not.
* ``Agent(instructions=...)`` sets both backstory and goal to the
  instructions, so the prompt repeated them under "Your Goal:".
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.tools.edit_tools import apply_patch, edit_file

OPENAI_HINT = "use edit_file to modify existing files precisely"
ANTHROPIC_HINT = "use apply_patch"


def lookup(query: str) -> str:
    """Look something up."""
    return query


@pytest.fixture
def make(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    made = []

    def _make(**kw):
        kw.setdefault("instructions", "Be brief.")
        agent = Agent(context=False, **kw)
        made.append(agent)
        return agent

    yield _make
    for agent in made:
        agent.close()


@pytest.mark.parametrize("tools", [None, [lookup]])
def test_agent_without_edit_tools_gets_no_edit_hint(make, tools):
    agent = make(llm="gpt-4o-mini", tools=tools)
    assert OPENAI_HINT not in agent._build_system_prompt()


def test_agent_with_edit_file_gets_the_openai_hint(make):
    agent = make(llm="gpt-4o-mini", tools=[edit_file, lookup])
    assert OPENAI_HINT in agent._build_system_prompt()


def test_agent_with_apply_patch_gets_the_anthropic_hint(make):
    agent = make(llm="anthropic/claude-sonnet-4-5", tools=[apply_patch])
    assert ANTHROPIC_HINT in agent._build_system_prompt()


def test_edit_tool_named_by_string_counts(make):
    agent = make(llm="gpt-4o-mini")
    assert OPENAI_HINT in agent._build_system_prompt(tools=["edit_file"])


def test_per_call_tools_decide_the_hint(make):
    agent = make(llm="gpt-4o-mini", tools=[edit_file])
    assert OPENAI_HINT not in agent._build_system_prompt(tools=[lookup])
    assert OPENAI_HINT in agent._build_system_prompt(tools=[edit_file])


def test_cached_prompt_follows_a_change_to_the_agents_tools(make):
    agent = make(llm="gpt-4o-mini", tools=[lookup])
    assert OPENAI_HINT not in agent._build_system_prompt()
    agent.tools = [edit_file]
    assert OPENAI_HINT in agent._build_system_prompt()
    agent.tools = [lookup]
    assert OPENAI_HINT not in agent._build_system_prompt()


def test_explicit_harness_override_is_always_used(make):
    agent = make(llm="gpt-4o-mini")
    agent.harness_base_prompt = "House rules."
    assert agent._build_system_prompt().startswith("House rules.")


def test_instructions_appear_once(make):
    agent = make(llm="gpt-4o-mini", instructions="Answer in French.")
    prompt = agent._build_system_prompt()
    assert prompt.count("Answer in French.") == 1
    assert "Your Goal:" not in prompt


def test_a_distinct_goal_is_still_stated(make):
    agent = make(llm="gpt-4o-mini", instructions=None, role="Editor",
                 goal="Tighten the copy", backstory="A veteran sub-editor")
    prompt = agent._build_system_prompt()
    assert "Your Goal: Tighten the copy" in prompt
    assert "A veteran sub-editor" in prompt
    assert "Your Role: Editor" in prompt


def test_a_tool_renamed_to_edit_file_counts(make):
    from praisonaiagents import tool

    @tool(name="edit_file")
    def my_editor(filepath: str, old_string: str, new_string: str) -> str:
        """Edit a file."""
        return "ok"

    agent = make(llm="gpt-4o-mini", tools=[my_editor])
    assert OPENAI_HINT in agent._build_system_prompt()


def test_nested_tool_list_offers_the_edit_hint(make):
    agent = make(llm="gpt-4o-mini", tools=[["edit_file"]])
    assert OPENAI_HINT in agent._build_system_prompt()


EDIT_SCHEMA = {"type": "function", "function": {
    "name": "edit_file", "description": "Edit a file.",
    "parameters": {"type": "object", "properties": {}}}}


def _system_sent(agent, monkeypatch, run):
    """Run ``run(agent)`` on the native path; return the system prompt and tool names sent."""
    from types import SimpleNamespace
    sent = []
    sent_tools = []

    def fake(messages=None, temperature=None, tools=None, *a, **k):
        sent.append(messages if messages is not None else k.get("messages"))
        sent_tools.append([t.get("function", {}).get("name") for t in tools or []])
        message = SimpleNamespace(content="ok", tool_calls=None, role="assistant", reasoning_content=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop", index=0)],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                               model="gpt-4o-mini")

    async def afake(*a, **k):
        return fake(*a, **k)

    monkeypatch.setattr(agent, "_chat_completion", fake)
    monkeypatch.setattr(agent, "_achat_completion_with_retry", afake)
    run(agent)
    return next(m["content"] for m in sent[-1] if m["role"] == "system"), sent_tools[-1]


def test_native_chat_follows_per_call_edit_tools(make, monkeypatch):
    agent = make(llm="gpt-4o-mini")
    system, tool_names = _system_sent(agent, monkeypatch, lambda a: a.chat("hi", tools=[EDIT_SCHEMA]))
    assert OPENAI_HINT in system
    assert "edit_file" in tool_names


def test_native_achat_follows_per_call_edit_tools(make, monkeypatch):
    import asyncio
    agent = make(llm="gpt-4o-mini")
    system, tool_names = _system_sent(agent, monkeypatch, lambda a: asyncio.run(a.achat("hi", tools=[EDIT_SCHEMA])))
    assert OPENAI_HINT in system
    assert "edit_file" in tool_names


def test_system_prompt_attribute_states_instructions_once(make):
    agent = make(llm="gpt-4o-mini", instructions="Answer in French.")
    assert agent.system_prompt.count("Answer in French.") == 1


def test_cached_prompt_follows_a_backstory_change(make):
    agent = make(llm="gpt-4o-mini", instructions="Answer in French.")
    assert "Your Goal:" not in agent._build_system_prompt()
    agent.backstory = "A translator"
    prompt = agent._build_system_prompt()
    assert "A translator" in prompt
    assert "Your Goal: Answer in French." in prompt

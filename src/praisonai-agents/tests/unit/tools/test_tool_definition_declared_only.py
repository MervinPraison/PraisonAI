"""A tool name resolves to a schema only from declared tools or the tool registry.

Tool execution stopped falling back to ``globals()`` / ``__main__`` for undeclared
names. The two definition helpers (``Agent._generate_tool_definition`` and
``LLM._generate_tool_definition``) still did, so the model was offered a schema for
a ``__main__`` callable that was never declared and that execution then refused.
The OpenAI-native path (``OpenAIClient._generate_tool_definition_from_name``) is
registry-only; all three now agree.
"""
import ast
import pathlib
import sys

import pytest

import praisonaiagents

PKG = pathlib.Path(praisonaiagents.__file__).parent


@pytest.fixture
def undeclared_in_main(monkeypatch):
    main = sys.modules["__main__"]

    def sneaky(msg: str = "ok") -> dict:
        """Never declared as a tool."""
        return {"ran": msg}

    monkeypatch.setattr(main, "sneaky", sneaky, raising=False)
    monkeypatch.setattr(
        main,
        "sneaky2_definition",
        {"type": "function", "function": {"name": "sneaky2", "parameters": {}}},
        raising=False,
    )
    return main


def test_llm_does_not_define_undeclared_main_callable(undeclared_in_main):
    from praisonaiagents.llm.llm import LLM

    llm = LLM(model="gpt-4o-mini")
    assert llm._generate_tool_definition("sneaky") is None
    assert llm._generate_tool_definition("sneaky2") is None


def test_agent_does_not_define_undeclared_main_callable(undeclared_in_main):
    from praisonaiagents import Agent

    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini")
    assert agent._generate_tool_definition("sneaky") is None
    assert agent._generate_tool_definition("sneaky2") is None


def test_declared_tool_still_resolves_by_name():
    from praisonaiagents import Agent

    def lookup(city: str) -> str:
        """Look up a city."""
        return city

    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini", tools=[lookup])
    tool_def = agent._generate_tool_definition("lookup")
    assert tool_def and tool_def["function"]["name"] == "lookup"


def test_registry_tool_still_resolves_by_name_in_llm():
    from praisonaiagents.llm.llm import LLM
    from praisonaiagents.tools.registry import get_registry

    def registry_probe_tool(q: str) -> str:
        """Probe."""
        return q

    registry = get_registry()
    registry.register(registry_probe_tool, name="registry_probe_tool")
    try:
        tool_def = LLM(model="gpt-4o-mini")._generate_tool_definition("registry_probe_tool")
        assert tool_def and tool_def["function"]["name"] == "registry_probe_tool"
    finally:
        registry.unregister("registry_probe_tool")


def test_no_module_looks_up_names_in_main():
    """Guard: no SDK module resolves a name through ``__main__``."""
    offenders = []
    for path in PKG.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name == "__main__" for a in node.names):
                offenders.append(f"{path.relative_to(PKG)}:{node.lineno}")
    assert offenders == [], offenders

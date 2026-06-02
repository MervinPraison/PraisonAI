from __future__ import annotations

import logging

import pytest


class _DummyAdapter:
    def __init__(self):
        self.last_tools_dict = None

    async def arun(
        self,
        config,
        llm_config,
        topic,
        *,
        tools_dict=None,
        agent_callback=None,
        task_callback=None,
        cli_config=None,
    ):
        self.last_tools_dict = tools_dict or {}
        return "ok"


class _DummyResolver:
    def resolve(self, name: str):
        if name == "MyTool":
            class _Tool:
                pass

            return _Tool
        return None

    def get_local_tool_classes(self):
        return {}

    def get_local_tool_classes_from_dir(self, path):
        return {}


@pytest.mark.asyncio
async def test_arun_framework_resolves_yaml_tools_via_tool_resolver(monkeypatch):
    from praisonai.agents_generator import AgentsGenerator

    adapter = _DummyAdapter()
    gen = object.__new__(AgentsGenerator)
    gen.framework = "crewai"
    gen.framework_adapter = adapter
    gen.config_list = []
    gen.tools = []
    gen.agent_callback = None
    gen.task_callback = None
    gen.cli_config = {}
    gen.logger = logging.getLogger("test-agents-generator-async")
    gen.tool_resolver = _DummyResolver()
    gen._validate_agents_config = lambda cfg: None
    gen._get_framework_adapter = lambda framework: adapter

    monkeypatch.setattr("praisonai.agents_generator.is_available", lambda _: True)
    monkeypatch.setattr(
        "praisonai.framework_adapters.validators.assert_framework_available",
        lambda _: None,
    )

    result = await gen._arun_framework(
        {
            "input": "topic",
            "roles": {
                "writer": {
                    "role": "Writer",
                    "goal": "Write",
                    "backstory": "Writes content",
                    "tools": ["MyTool"],
                    "tasks": {},
                }
            },
        }
    )

    assert result == "ok"
    assert "MyTool" in adapter.last_tools_dict


@pytest.mark.asyncio
async def test_arun_framework_uses_config_framework_when_instance_framework_empty(monkeypatch):
    from praisonai.agents_generator import AgentsGenerator

    adapter = _DummyAdapter()
    selected_frameworks = []

    def _get_framework_adapter(framework: str):
        selected_frameworks.append(framework)
        return adapter

    gen = object.__new__(AgentsGenerator)
    gen.framework = None
    gen.framework_adapter = adapter
    gen.config_list = []
    gen.tools = []
    gen.agent_callback = None
    gen.task_callback = None
    gen.cli_config = {}
    gen.logger = logging.getLogger("test-agents-generator-async")
    gen.tool_resolver = _DummyResolver()
    gen._validate_agents_config = lambda cfg: None
    gen._get_framework_adapter = _get_framework_adapter

    monkeypatch.setattr("praisonai.agents_generator.is_available", lambda _: False)
    monkeypatch.setattr(
        "praisonai.framework_adapters.validators.assert_framework_available",
        lambda _: None,
    )

    result = await gen._arun_framework(
        {
            "framework": "praisonaiagents",
            "input": "topic",
            "roles": {},
        }
    )

    assert result == "ok"
    assert gen.framework == "praisonaiagents"
    assert selected_frameworks == ["praisonaiagents"]

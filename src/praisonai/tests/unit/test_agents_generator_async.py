from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="AgentsGenerator async API refactored; tests need rewrite")


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


@pytest.mark.asyncio
async def test_arun_framework_defaults_to_praisonai_when_no_framework_specified(monkeypatch):
    """Test that AgentsGenerator with YAML file and no --framework flag defaults to praisonai (fixes #1877)"""
    from praisonai.agents_generator import AgentsGenerator

    class _MockAdapter:
        def __init__(self, name):
            self.name = name
            self.last_tools_dict = None

        def resolve(self):
            return self

        def setup(self, framework_tag=None):
            pass

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

    praisonai_adapter = _MockAdapter("praisonai")
    selected_frameworks = []

    def _get_framework_adapter(framework: str):
        selected_frameworks.append(framework)
        return praisonai_adapter

    gen = object.__new__(AgentsGenerator)
    gen.framework = None  # No --framework flag specified
    gen.framework_adapter = None  # Deferred initialization
    gen.config_list = []
    gen.tools = []
    gen.agent_callback = None
    gen.task_callback = None
    gen.cli_config = {}
    gen.logger = logging.getLogger("test-agents-generator-async")
    gen.tool_resolver = _DummyResolver()
    gen._validate_agents_config = lambda cfg: None
    gen._get_framework_adapter = _get_framework_adapter
    gen._validate_cli_backend_compatibility = lambda cfg, framework: None

    # Mock observability and validation
    monkeypatch.setattr("praisonai.agents_generator.is_available", lambda _: True)
    monkeypatch.setattr(
        "praisonai.framework_adapters.validators.assert_framework_available",
        lambda _: None,
    )
    monkeypatch.setattr(
        "praisonai.observability.hooks.init_observability",
        lambda _: None,
    )

    # Test YAML config without explicit framework (should default to praisonai)
    result = await gen._arun_framework(
        {
            "input": "test topic", 
            "roles": {
                "writer": {
                    "role": "Writer",
                    "goal": "Write content",
                    "backstory": "Writes",
                    "tasks": {},
                }
            },
            # No 'framework' key in YAML
        }
    )

    assert result == "ok"
    assert gen.framework == "praisonai"  # Should default to praisonai
    assert selected_frameworks == ["praisonai"]  # Should select praisonai, not crewai
    assert gen.framework_adapter.name == "praisonai"


@pytest.mark.asyncio 
async def test_async_path_adapter_resolve_and_observability_parity(monkeypatch):
    """Test that async path follows same adapter.resolve() + init_observability() pattern as sync path"""
    from praisonai.agents_generator import AgentsGenerator

    class _MockAdapter:
        def __init__(self, name):
            self.name = name
            self.resolved = False
            self.setup_called = False

        def resolve(self):
            """Mock resolve() call to track it was called"""
            self.resolved = True
            return self

        def setup(self, framework_tag=None):
            """Mock setup() call to track it was called"""
            self.setup_called = True

        async def arun(self, config, llm_config, topic, **kwargs):
            return "async_result"

    mock_adapter = _MockAdapter("testframework")
    observability_called = []
    validator_called = []

    def _get_framework_adapter(framework: str):
        return mock_adapter

    def mock_init_observability(framework_name):
        observability_called.append(framework_name)

    def mock_assert_framework_available(framework_name):
        validator_called.append(framework_name)

    gen = object.__new__(AgentsGenerator)
    gen.framework = "testframework"
    gen.framework_adapter = None  # Deferred initialization
    gen.config_list = []
    gen.tools = []
    gen.agent_callback = None
    gen.task_callback = None
    gen.cli_config = {}
    gen.logger = logging.getLogger("test-async-parity")
    gen.tool_resolver = _DummyResolver()
    gen._validate_agents_config = lambda cfg: None
    gen._get_framework_adapter = _get_framework_adapter
    gen._validate_cli_backend_compatibility = lambda cfg, framework: None

    # Mock the hooks and validation
    monkeypatch.setattr("praisonai.agents_generator.is_available", lambda _: True)
    monkeypatch.setattr(
        "praisonai.framework_adapters.validators.assert_framework_available",
        mock_assert_framework_available,
    )
    monkeypatch.setattr(
        "praisonai.observability.hooks.init_observability",
        mock_init_observability,
    )

    result = await gen._arun_framework({
        "input": "test", 
        "roles": {}
    })

    # Verify all key initialization steps are called in async path (same as sync)
    assert result == "async_result"
    assert mock_adapter.resolved == True, "adapter.resolve() should be called"
    assert mock_adapter.setup_called == True, "adapter.setup() should be called"
    assert observability_called == ["testframework"], "init_observability() should be called with adapter name"
    assert validator_called == ["testframework"], "assert_framework_available() should be called with adapter name"
    assert gen.framework_adapter == mock_adapter, "framework_adapter should be set to resolved adapter"

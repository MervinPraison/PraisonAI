"""Tests for ManagedAgent factory pattern and LocalManagedAgent."""

import os
from unittest.mock import patch, MagicMock


class TestManagedAgentFactory:
    def test_factory_returns_local_when_no_anthropic_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("CLAUDE_API_KEY", None)
            from praisonai.integrations.managed_agents import ManagedAgent
            agent = ManagedAgent()
            assert agent.provider != "anthropic"
            assert hasattr(agent, '_inner_agent')

    def test_factory_returns_anthropic_when_key_set(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}):
            from praisonai.integrations.managed_agents import ManagedAgent
            agent = ManagedAgent()
            assert agent.provider == "anthropic"
            assert hasattr(agent, '_get_client')

    def test_factory_explicit_local(self):
        from praisonai.integrations.managed_agents import ManagedAgent
        agent = ManagedAgent(provider="local")
        assert agent.provider == "local"

    def test_factory_explicit_anthropic(self):
        from praisonai.integrations.managed_agents import ManagedAgent
        agent = ManagedAgent(provider="anthropic", api_key="test")
        assert agent.provider == "anthropic"

    def test_factory_ollama_provider(self):
        from praisonai.integrations.managed_agents import ManagedAgent
        agent = ManagedAgent(provider="ollama")
        assert agent.provider == "ollama"

    def test_factory_openai_provider(self):
        from praisonai.integrations.managed_agents import ManagedAgent
        agent = ManagedAgent(provider="openai")
        assert agent.provider == "openai"

    def test_factory_gemini_provider(self):
        from praisonai.integrations.managed_agents import ManagedAgent
        agent = ManagedAgent(provider="gemini")
        assert agent.provider == "gemini"


class TestLocalManagedConfig:
    def test_defaults(self):
        from praisonai.integrations.managed_local import LocalManagedConfig
        cfg = LocalManagedConfig()
        assert cfg.name == "Agent"
        assert cfg.model == "gpt-4o"
        assert cfg.max_turns == 25
        assert "execute_command" in cfg.tools
        assert cfg.host_packages_ok is False

    def test_custom_config(self):
        from praisonai.integrations.managed_local import LocalManagedConfig
        cfg = LocalManagedConfig(
            model="ollama/llama3",
            system="Be helpful.",
            tools=["execute_command"],
            max_turns=10,
        )
        assert cfg.model == "ollama/llama3"
        assert cfg.system == "Be helpful."
        assert cfg.max_turns == 10


class TestLocalManagedAgent:
    def test_init_defaults(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        assert agent.provider == "local"
        assert agent.agent_id is None
        assert agent.environment_id is None
        assert agent._session_id is None
        assert agent.total_input_tokens == 0
        assert agent.total_output_tokens == 0

    def test_init_with_config(self):
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        cfg = LocalManagedConfig(model="gpt-4o-mini", name="TestAgent")
        agent = LocalManagedAgent(config=cfg)
        assert agent._cfg["model"] == "gpt-4o-mini"
        assert agent._cfg["name"] == "TestAgent"

    def test_ensure_session_creates_id(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        sid = agent._ensure_session()
        assert sid is not None
        assert sid.startswith("session_")
        assert agent._session_id == sid

    def test_ensure_session_idempotent(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        sid1 = agent._ensure_session()
        sid2 = agent._ensure_session()
        assert sid1 == sid2

    def test_reset_session(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        assert agent._session_id is not None
        agent.reset_session()
        assert agent._session_id is None

    def test_reset_all(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        agent.agent_id = "agent_test"
        agent.environment_id = "env_test"
        agent.total_input_tokens = 100
        agent.reset_all()
        assert agent.agent_id is None
        assert agent.environment_id is None
        assert agent._session_id is None
        assert agent._inner_agent is None
        assert agent.total_input_tokens == 0

    def test_update_agent(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent.agent_version = 1
        agent.update_agent(system="New system prompt", model="gpt-4o-mini")
        assert agent._cfg["system"] == "New system prompt"
        assert agent._cfg["model"] == "gpt-4o-mini"
        assert agent.agent_version == 2

    def test_save_restore_ids(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent.agent_id = "agent_abc"
        agent.environment_id = "env_xyz"
        agent._session_id = "session_123"
        agent.agent_version = 3

        ids = agent.save_ids()
        assert ids["agent_id"] == "agent_abc"
        assert ids["session_id"] == "session_123"

        agent2 = LocalManagedAgent()
        agent2.restore_ids(ids)
        assert agent2.agent_id == "agent_abc"
        assert agent2.environment_id == "env_xyz"
        assert agent2._session_id == "session_123"
        assert agent2.agent_version == 3

    def test_session_id_property(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        assert agent.session_id is None
        agent._ensure_session()
        assert agent.session_id is not None
        assert agent.managed_session_id == agent.session_id

    def test_retrieve_session(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        info = agent.retrieve_session()
        assert info["id"] == agent._session_id
        assert info["status"] == "idle"

    def test_list_sessions_empty(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        assert agent.list_sessions() == []

    def test_list_sessions_active(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        sessions = agent.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == agent._session_id

    def test_resolve_model_ollama(self):
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        agent = LocalManagedAgent(provider="ollama", config=LocalManagedConfig(model="llama3"))
        model = agent._resolve_model()
        assert model == "ollama/llama3"

    def test_resolve_model_gemini(self):
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        agent = LocalManagedAgent(provider="gemini", config=LocalManagedConfig(model="pro"))
        model = agent._resolve_model()
        assert model == "gemini/pro"

    def test_resolve_model_default(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        model = agent._resolve_model()
        assert model == "gpt-4o"


class TestToolConfigTranslation:
    def test_string_tools_pass_through(self):
        from praisonai.integrations.managed_local import _translate_anthropic_tools
        result = _translate_anthropic_tools(["execute_command", "read_file"])
        assert result == ["execute_command", "read_file"]

    def test_empty_returns_defaults(self):
        from praisonai.integrations.managed_local import _translate_anthropic_tools, _DEFAULT_TOOLS
        result = _translate_anthropic_tools([])
        assert result == list(_DEFAULT_TOOLS)

    def test_agent_toolset_all_defaults(self):
        from praisonai.integrations.managed_local import _translate_anthropic_tools, _DEFAULT_TOOLS
        result = _translate_anthropic_tools([{"type": "agent_toolset_20260401"}])
        assert result == list(_DEFAULT_TOOLS)

    def test_agent_toolset_selective_enabled(self):
        from praisonai.integrations.managed_local import _translate_anthropic_tools
        result = _translate_anthropic_tools([{
            "type": "agent_toolset_20260401",
            "default_config": {"enabled": False},
            "configs": [
                {"name": "bash", "enabled": True},
                {"name": "read", "enabled": True},
                {"name": "write", "enabled": True},
            ],
        }])
        assert "execute_command" in result
        assert "read_file" in result
        assert "write_file" in result
        assert "search_web" not in result

    def test_agent_toolset_disable_specific(self):
        from praisonai.integrations.managed_local import _translate_anthropic_tools
        result = _translate_anthropic_tools([{
            "type": "agent_toolset_20260401",
            "configs": [
                {"name": "web_fetch", "enabled": False},
                {"name": "web_search", "enabled": False},
            ],
        }])
        assert "web_crawl" not in result
        assert "search_web" not in result
        assert "execute_command" in result

    def test_custom_tool_preserved(self):
        from praisonai.integrations.managed_local import _translate_anthropic_tools
        result = _translate_anthropic_tools([
            {"type": "agent_toolset_20260401"},
            {"type": "custom", "name": "get_weather"},
        ])
        assert "execute_command" in result


class TestUsageTracking:
    def test_sync_usage_from_inner_agent(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        mock_inner = MagicMock()
        mock_inner._total_tokens_in = 500
        mock_inner._total_tokens_out = 200
        agent._inner_agent = mock_inner
        agent._sync_usage()
        assert agent.total_input_tokens == 500
        assert agent.total_output_tokens == 200

    def test_retrieve_session_includes_usage(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        mock_inner = MagicMock()
        mock_inner._total_tokens_in = 100
        mock_inner._total_tokens_out = 50
        agent._inner_agent = mock_inner
        info = agent.retrieve_session()
        assert info["usage"]["input_tokens"] == 100
        assert info["usage"]["output_tokens"] == 50


class TestSessionHistory:
    def test_session_history_tracked(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        assert len(agent._session_history) == 1
        assert agent._session_history[0]["id"] == agent._session_id
        assert "created_at" in agent._session_history[0]

    def test_list_sessions_returns_history(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        sid1 = agent._session_id
        agent._session_id = None
        agent._ensure_session()
        sid2 = agent._session_id
        sessions = agent.list_sessions()
        assert len(sessions) == 2
        assert sessions[0]["id"] == sid1
        assert sessions[1]["id"] == sid2

    def test_list_sessions_with_limit(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        for _ in range(5):
            agent._session_id = None
            agent._ensure_session()
        sessions = agent.list_sessions(limit=2)
        assert len(sessions) == 2

    def test_reset_all_clears_history(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        agent.reset_all()
        assert agent._session_history == []


class TestCustomToolCallback:
    def test_custom_tool_wired(self):
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        results = []
        def handle_custom(name, inp):
            results.append((name, inp))
            return "ok"

        cfg = LocalManagedConfig(
            tools=[
                {"type": "agent_toolset_20260401"},
                {
                    "type": "custom",
                    "name": "get_weather",
                    "description": "Get weather",
                    "input_schema": {"type": "object"},
                },
            ],
        )
        agent = LocalManagedAgent(config=cfg, on_custom_tool=handle_custom)
        tools = agent._resolve_tools()
        custom_fns = [t for t in tools if callable(t) and getattr(t, '__name__', '') == 'get_weather']
        assert len(custom_fns) == 1
        result = custom_fns[0](location="Tokyo")
        assert result == "ok"
        assert results == [("get_weather", {"location": "Tokyo"})]


class TestPackageConfig:
    def test_packages_in_config(self):
        from praisonai.integrations.managed_local import LocalManagedConfig
        cfg = LocalManagedConfig(packages={"pip": ["pandas", "numpy"]})
        assert cfg.packages == {"pip": ["pandas", "numpy"]}

    def test_host_packages_ok_default_false(self):
        from praisonai.integrations.managed_local import LocalManagedConfig
        cfg = LocalManagedConfig()
        assert cfg.host_packages_ok is False

    def test_host_packages_ok_explicit_true(self):
        from praisonai.integrations.managed_local import LocalManagedConfig
        cfg = LocalManagedConfig(host_packages_ok=True)
        assert cfg.host_packages_ok is True


class TestManagedSandboxSafety:
    """Test security features for managed agents package installation."""

    def test_install_packages_without_compute_raises(self):
        """Test that package installation without compute provider raises ManagedSandboxRequired."""
        import pytest
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        from praisonai.integrations.managed_agents import ManagedSandboxRequired
        
        cfg = LocalManagedConfig(packages={"pip": ["requests"]})
        agent = LocalManagedAgent(config=cfg)
        
        with pytest.raises(ManagedSandboxRequired) as exc_info:
            agent._install_packages()
        
        assert "Package installation requested" in str(exc_info.value)
        assert "security risk" in str(exc_info.value)
        assert "compute='docker'" in str(exc_info.value)
        assert "host_packages_ok=True" in str(exc_info.value)

    def test_install_packages_with_host_packages_ok_succeeds(self):
        """Test that package installation with host_packages_ok=True succeeds."""
        from unittest.mock import patch
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        cfg = LocalManagedConfig(packages={"pip": ["requests"]}, host_packages_ok=True)
        agent = LocalManagedAgent(config=cfg)
        
        with patch('praisonai.integrations.managed_local.subprocess.run') as mock_run:
            mock_run.return_value = None
            agent._install_packages()  # Should not raise
            mock_run.assert_called_once()

    def test_install_packages_with_compute_uses_sandbox(self):
        """Test that package installation with compute provider uses sandbox."""
        from unittest.mock import AsyncMock, patch
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        cfg = LocalManagedConfig(packages={"pip": ["requests"]})
        agent = LocalManagedAgent(config=cfg, compute="local")
        
        # Mock the compute execution
        with patch.object(agent, 'provision_compute') as mock_provision, \
             patch.object(agent._compute, 'execute') as mock_execute, \
             patch('asyncio.run') as mock_asyncio_run, \
             patch('asyncio.get_event_loop') as mock_get_loop:
            
            mock_provision.return_value = None
            mock_execute.return_value = {"exit_code": 0, "stdout": "installed"}
            agent._compute_instance_id = "test_instance"
            mock_asyncio_run.return_value = {"exit_code": 0, "stdout": "installed"}
            
            agent._install_packages()
            
            # Verify subprocess.run was NOT called (no host installation)
            with patch('praisonai.integrations.managed_local.subprocess.run') as mock_run:
                agent._install_packages()
                mock_run.assert_not_called()

    def test_no_packages_no_error(self):
        """Test that agents without packages work normally."""
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._install_packages()  # Should not raise

    def test_empty_packages_no_error(self):
        """Test that empty packages dict works normally."""
        from praisonai.integrations.managed_local import LocalManagedConfig, LocalManagedAgent
        cfg = LocalManagedConfig(packages={"pip": []})
        agent = LocalManagedAgent(config=cfg)
        agent._install_packages()  # Should not raise


class TestComputeToolBridge:
    """Test compute-based tool execution routing."""
    
    def test_bridged_tools_created_when_compute_attached(self):
        """Test that shell-based tools are bridged when compute is attached."""
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(compute="local")
        tools = agent._resolve_tools()
        
        # Should have tools but they should be wrapped/bridged versions
        tool_names = [getattr(t, '__name__', str(t)) for t in tools if callable(t)]
        assert "execute_command" in tool_names

    def test_non_bridged_tools_use_original_when_no_compute(self):
        """Test that tools use original implementation when no compute."""
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        tools = agent._resolve_tools()
        
        # Should have original tools
        tool_names = [getattr(t, '__name__', str(t)) for t in tools if callable(t)]
        assert "execute_command" in tool_names

    def test_compute_bridge_tool_execute_command(self):
        """Test that execute_command is properly bridged to compute."""
        from unittest.mock import AsyncMock, patch
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        agent = LocalManagedAgent(compute="local")
        agent._compute_instance_id = "test_instance"
        
        # Create a bridge tool for execute_command
        original_func = lambda command: "original result"
        bridge_tool = agent._create_compute_bridge_tool("execute_command", original_func)
        
        with patch.object(agent._compute, 'execute'), \
             patch('asyncio.get_event_loop', side_effect=RuntimeError('no loop')), \
             patch('asyncio.run') as mock_asyncio_run:
            
            mock_asyncio_run.return_value = {"exit_code": 0, "stdout": "compute result"}
            
            result = bridge_tool("echo hello")
            assert result == "compute result"
            
            # Verify it attempted to run in compute, not locally
            mock_asyncio_run.assert_called()

    def test_compute_bridge_tool_read_file(self):
        """Test that read_file is properly bridged to compute."""
        from unittest.mock import patch
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        agent = LocalManagedAgent(compute="local")
        agent._compute_instance_id = "test_instance"
        
        original_func = lambda filepath: "original content"
        bridge_tool = agent._create_compute_bridge_tool("read_file", original_func)
        
        with patch.object(agent, '_bridge_file_tool') as mock_bridge:
            mock_bridge.return_value = "file content from compute"
            
            result = bridge_tool("/path/to/file")
            assert result == "file content from compute"
            mock_bridge.assert_called_once_with("read_file", "/path/to/file")

    def test_compute_bridge_tool_write_file(self):
        """Test that write_file is properly bridged to compute."""
        from unittest.mock import patch
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        agent = LocalManagedAgent(compute="local") 
        agent._compute_instance_id = "test_instance"
        
        original_func = lambda filepath, content: "written locally"
        bridge_tool = agent._create_compute_bridge_tool("write_file", original_func)
        
        with patch.object(agent, '_bridge_file_tool') as mock_bridge:
            mock_bridge.return_value = "written to compute"
            
            result = bridge_tool("/path/to/file", "content")
            assert result == "written to compute"
            mock_bridge.assert_called_once_with("write_file", "/path/to/file", "content")

    def test_bridge_file_tool_read(self):
        """Test _bridge_file_tool for read operations."""
        from unittest.mock import patch
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        agent = LocalManagedAgent(compute="local")
        agent._compute_instance_id = "test_instance"
        
        with patch('asyncio.get_event_loop', side_effect=RuntimeError('no loop')), \
             patch('asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.return_value = {"exit_code": 0, "stdout": "file contents"}
            
            result = agent._bridge_file_tool("read_file", "/test/file")
            assert result == "file contents"

    def test_bridge_file_tool_write(self):
        """Test _bridge_file_tool for write operations."""
        from unittest.mock import patch
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        agent = LocalManagedAgent(compute="local")
        agent._compute_instance_id = "test_instance"
        
        with patch('asyncio.get_event_loop', side_effect=RuntimeError('no loop')), \
             patch('asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.return_value = {"exit_code": 0, "stdout": ""}
            
            result = agent._bridge_file_tool("write_file", "/test/file", "content")
            assert result == ""

    def test_bridge_file_tool_list(self):
        """Test _bridge_file_tool for list operations.""" 
        from unittest.mock import patch
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        agent = LocalManagedAgent(compute="local")
        agent._compute_instance_id = "test_instance"
        
        with patch('asyncio.get_event_loop', side_effect=RuntimeError('no loop')), \
             patch('asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.return_value = {"exit_code": 0, "stdout": "file1\nfile2\n"}
            
            result = agent._bridge_file_tool("list_files", "/test/dir")
            assert result == "file1\nfile2\n"


class TestUpdateAgentKeepsSession:
    def test_update_preserves_session(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent()
        agent._ensure_session()
        sid = agent._session_id
        agent.update_agent(system="new system")
        assert agent._session_id == sid


class TestAnthropicManagedAgentBackwardCompat:
    def test_class_exists(self):
        from praisonai.integrations.managed_agents import AnthropicManagedAgent
        agent = AnthropicManagedAgent(api_key="test-key")
        assert agent.provider == "anthropic"
        assert agent.api_key == "test-key"

    def test_managed_config_exists(self):
        from praisonai.integrations.managed_agents import ManagedConfig
        cfg = ManagedConfig(model="claude-sonnet-4-6")
        assert cfg.model == "claude-sonnet-4-6"

    def test_managed_config_tool_format(self):
        from praisonai.integrations.managed_agents import ManagedConfig
        cfg = ManagedConfig(
            tools=[{"type": "agent_toolset_20260401"}],
            packages={"pip": ["pandas"]},
        )
        assert cfg.tools[0]["type"] == "agent_toolset_20260401"
        assert cfg.packages == {"pip": ["pandas"]}


# ====================================================================== #
#  Compute provider integration in LocalManagedAgent
# ====================================================================== #

class TestComputeProviderWiring:
    def test_default_no_compute(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local")
        assert agent.compute_provider is None

    def test_resolve_string_local(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local", compute="local")
        assert agent.compute_provider is not None
        assert agent.compute_provider.provider_name == "local"

    def test_resolve_string_docker(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local", compute="docker")
        assert agent.compute_provider.provider_name == "docker"

    def test_resolve_string_e2b(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local", compute="e2b")
        assert agent.compute_provider.provider_name == "e2b"

    def test_resolve_string_modal(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local", compute="modal")
        assert agent.compute_provider.provider_name == "modal"

    def test_resolve_string_daytona(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local", compute="daytona")
        assert agent.compute_provider.provider_name == "daytona"

    def test_resolve_string_flyio(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local", compute="flyio")
        assert agent.compute_provider.provider_name == "flyio"

    def test_resolve_unknown_raises(self):
        import pytest
        from praisonai.integrations.managed_local import LocalManagedAgent
        with pytest.raises(ValueError, match="Unknown compute provider"):
            LocalManagedAgent(provider="local", compute="unknown_provider")

    def test_resolve_instance(self):
        from praisonai.integrations.managed_local import LocalManagedAgent
        from praisonai.integrations.compute.local import LocalCompute
        instance = LocalCompute()
        agent = LocalManagedAgent(provider="local", compute=instance)
        assert agent.compute_provider is instance

    def test_provision_without_compute_raises(self):
        import asyncio
        import pytest
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local")
        with pytest.raises(RuntimeError, match="No compute provider"):
            asyncio.run(agent.provision_compute())

    def test_execute_without_provision_raises(self):
        import asyncio
        import pytest
        from praisonai.integrations.managed_local import LocalManagedAgent
        agent = LocalManagedAgent(provider="local", compute="local")
        with pytest.raises(RuntimeError, match="No compute provisioned"):
            asyncio.run(agent.execute_in_compute("echo hello"))

    def test_provision_execute_shutdown_local(self):
        import asyncio
        from praisonai.integrations.managed_local import LocalManagedAgent

        agent = LocalManagedAgent(provider="local", compute="local")

        info = asyncio.run(agent.provision_compute())
        assert info.instance_id.startswith("local_")

        result = asyncio.run(agent.execute_in_compute("echo hello_compute"))
        assert result["exit_code"] == 0
        assert "hello_compute" in result["stdout"]

        asyncio.run(agent.shutdown_compute())
        assert agent._compute_instance_id is None

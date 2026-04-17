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
        assert cfg.host_packages_ok is False
        assert cfg.max_turns == 25
        assert "execute_command" in cfg.tools

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


# ====================================================================== #
#  Security tests - package installation and sandbox behavior
# ====================================================================== #

class TestManagedSandboxSafety:
    def test_install_packages_without_compute_raises(self):
        """Test that package installation without compute provider raises ManagedSandboxRequired."""
        import pytest
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        from praisonai.integrations.managed_agents import ManagedSandboxRequired
        
        cfg = LocalManagedConfig(packages={"pip": ["requests"]})
        agent = LocalManagedAgent(config=cfg)
        
        with pytest.raises(ManagedSandboxRequired, match="Package installation requires compute provider"):
            agent._install_packages()

    def test_install_packages_with_host_packages_ok_works(self):
        """Test that package installation with explicit opt-out works."""
        from unittest.mock import patch, MagicMock
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        cfg = LocalManagedConfig(packages={"pip": ["requests"]}, host_packages_ok=True)
        agent = LocalManagedAgent(config=cfg)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock()
            agent._install_packages()
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "pip" in args
            assert "install" in args
            assert "requests" in args

    def test_install_packages_with_compute_runs_in_sandbox(self):
        """Test that packages install in compute sandbox when compute provider attached."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        mock_compute = MagicMock()
        mock_compute.execute = AsyncMock(return_value={"exit_code": 0, "stdout": "success", "stderr": ""})
        
        cfg = LocalManagedConfig(packages={"pip": ["requests"]})
        agent = LocalManagedAgent(config=cfg, compute=mock_compute)
        agent._compute_instance_id = "test_instance"
        
        with patch('subprocess.run') as mock_subprocess:
            agent._install_packages()
            # subprocess.run should NOT be called when compute is attached
            mock_subprocess.assert_not_called()
            # compute.execute should be called instead
            mock_compute.execute.assert_called_once()

    def test_no_packages_skips_installation(self):
        """Test that no packages specified skips installation entirely."""
        from unittest.mock import patch
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        cfg = LocalManagedConfig()
        agent = LocalManagedAgent(config=cfg)
        
        with patch('subprocess.run') as mock_run:
            agent._install_packages()
            mock_run.assert_not_called()

    def test_empty_pip_packages_skips_installation(self):
        """Test that empty pip packages list skips installation."""
        from unittest.mock import patch
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        cfg = LocalManagedConfig(packages={"pip": []})
        agent = LocalManagedAgent(config=cfg)
        
        with patch('subprocess.run') as mock_run:
            agent._install_packages()
            mock_run.assert_not_called()

    def test_exception_message_includes_remediation(self):
        """Test that ManagedSandboxRequired exception includes actionable remediation."""
        import pytest
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        from praisonai.integrations.managed_agents import ManagedSandboxRequired
        
        cfg = LocalManagedConfig(packages={"pip": ["dangerous-package"]})
        agent = LocalManagedAgent(config=cfg)
        
        with pytest.raises(ManagedSandboxRequired) as exc_info:
            agent._install_packages()
        
        error_msg = str(exc_info.value)
        assert "dangerous-package" in error_msg
        assert "compute='docker'" in error_msg
        assert "host_packages_ok=True" in error_msg

    def test_managed_sandbox_required_exception_creation(self):
        """Test ManagedSandboxRequired exception can be created and has correct default message."""
        from praisonai.integrations.managed_agents import ManagedSandboxRequired
        
        exc = ManagedSandboxRequired()
        assert "Package installation requires compute provider for security" in str(exc)
        
        custom_exc = ManagedSandboxRequired("Custom message")
        assert str(custom_exc) == "Custom message"


class TestComputeToolBridge:
    """Test compute-bridged tool execution routing."""
    
    def test_tools_use_compute_bridge_when_compute_attached(self):
        """Test that shell tools use compute bridge when compute provider attached."""
        from unittest.mock import MagicMock
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        mock_compute = MagicMock()
        cfg = LocalManagedConfig(tools=["execute_command", "read_file", "write_file", "list_files"])
        agent = LocalManagedAgent(config=cfg, compute=mock_compute)
        
        tools = agent._resolve_tools()
        
        # Should have 4 compute-bridged tools
        shell_tools = [t for t in tools if hasattr(t, '__name__') and 
                      t.__name__ in {"execute_command", "read_file", "write_file", "list_files"}]
        assert len(shell_tools) == 4

    def test_tools_use_host_when_no_compute(self):
        """Test that tools use host versions when no compute provider."""
        from unittest.mock import patch, MagicMock
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        cfg = LocalManagedConfig(tools=["execute_command"])
        agent = LocalManagedAgent(config=cfg)
        
        with patch('praisonaiagents.tools.execute_command') as mock_tool:
            mock_tool.__name__ = "execute_command"
            tools = agent._resolve_tools()
            # Should use host tool, not compute bridge
            assert mock_tool in tools

    def test_compute_execute_command_bridge(self):
        """Test compute-bridged execute_command works correctly."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        mock_compute = MagicMock()
        mock_compute.execute = AsyncMock(return_value={
            "stdout": "hello world", 
            "stderr": "", 
            "exit_code": 0
        })
        
        agent = LocalManagedAgent(compute=mock_compute)
        agent._compute_instance_id = "test_instance"
        
        execute_command = agent._create_compute_execute_command()
        result = execute_command("echo hello world")
        
        assert result == "hello world"
        mock_compute.execute.assert_called_once_with("test_instance", "echo hello world", timeout=300)

    def test_compute_execute_command_with_stderr(self):
        """Test compute-bridged execute_command handles stderr correctly."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        mock_compute = MagicMock()
        mock_compute.execute = AsyncMock(return_value={
            "stdout": "output", 
            "stderr": "warning", 
            "exit_code": 1
        })
        
        agent = LocalManagedAgent(compute=mock_compute)
        agent._compute_instance_id = "test_instance"
        
        execute_command = agent._create_compute_execute_command()
        result = execute_command("failing_command")
        
        assert "output" in result
        assert "STDERR: warning" in result
        assert "Exit code: 1" in result

    def test_compute_read_file_bridge(self):
        """Test compute-bridged read_file works correctly."""
        from unittest.mock import MagicMock, AsyncMock
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        mock_compute = MagicMock()
        mock_compute.execute = AsyncMock(return_value={
            "stdout": "file contents", 
            "stderr": "", 
            "exit_code": 0
        })
        
        agent = LocalManagedAgent(compute=mock_compute)
        agent._compute_instance_id = "test_instance"
        
        read_file = agent._create_compute_read_file()
        result = read_file("/path/to/file.txt")
        
        assert result == "file contents"
        mock_compute.execute.assert_called_once_with("test_instance", "cat /path/to/file.txt", timeout=60)

    def test_compute_write_file_bridge(self):
        """Test compute-bridged write_file works correctly."""
        from unittest.mock import MagicMock, AsyncMock
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        mock_compute = MagicMock()
        mock_compute.execute = AsyncMock(return_value={
            "stdout": "", 
            "stderr": "", 
            "exit_code": 0
        })
        
        agent = LocalManagedAgent(compute=mock_compute)
        agent._compute_instance_id = "test_instance"
        
        write_file = agent._create_compute_write_file()
        result = write_file("/path/to/file.txt", "file content")
        
        assert "File written successfully" in result
        # Check that the command was properly escaped
        mock_compute.execute.assert_called_once()
        call_args = mock_compute.execute.call_args
        assert "echo" in call_args[0][1]
        assert "/path/to/file.txt" in call_args[0][1]

    def test_compute_list_files_bridge(self):
        """Test compute-bridged list_files works correctly."""
        from unittest.mock import MagicMock, AsyncMock
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        mock_compute = MagicMock()
        mock_compute.execute = AsyncMock(return_value={
            "stdout": "file1.txt\nfile2.txt\n", 
            "stderr": "", 
            "exit_code": 0
        })
        
        agent = LocalManagedAgent(compute=mock_compute)
        agent._compute_instance_id = "test_instance"
        
        list_files = agent._create_compute_list_files()
        result = list_files("/some/dir")
        
        assert "file1.txt" in result
        assert "file2.txt" in result
        mock_compute.execute.assert_called_once_with("test_instance", "ls -la /some/dir", timeout=60)

    def test_compute_tools_require_provisioned_instance(self):
        """Test that compute tools raise error when no instance is provisioned."""
        import pytest
        from praisonai.integrations.managed_local import LocalManagedAgent
        
        mock_compute = MagicMock()
        agent = LocalManagedAgent(compute=mock_compute)
        # Don't set _compute_instance_id
        
        execute_command = agent._create_compute_execute_command()
        with pytest.raises(RuntimeError, match="No compute provider provisioned"):
            execute_command("echo test")

    def test_auto_provision_compute_in_ensure_agent(self):
        """Test that _ensure_agent auto-provisions compute when needed."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        
        mock_compute = MagicMock()
        mock_info = MagicMock()
        mock_info.instance_id = "auto_provisioned_instance"
        
        cfg = LocalManagedConfig()
        agent = LocalManagedAgent(config=cfg, compute=mock_compute)
        
        with patch.object(agent, 'provision_compute', new_callable=AsyncMock) as mock_provision:
            mock_provision.return_value = mock_info
            with patch('praisonaiagents.Agent') as mock_agent_class:
                mock_agent_class.return_value = MagicMock()
                
                inner_agent = agent._ensure_agent()
                
                # Should have auto-provisioned compute
                mock_provision.assert_called_once()
                assert agent._compute_instance_id == "auto_provisioned_instance"

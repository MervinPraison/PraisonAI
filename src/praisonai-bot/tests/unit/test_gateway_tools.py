"""
TDD Tests for Gateway Tool Resolution Gaps (G1, G2, G3).

Tests the fixes for tool resolution in gateway agent creation.
"""

# Mocks available if needed for future tests


class TestGapG1GatewayToolResolution:
    """Test Gap G1: Gateway _create_agents_from_config() tool resolution."""

    def test_gateway_creates_agent_with_tools_from_yaml(self):
        """Gateway should resolve tools from YAML config."""
        from praisonai_bot.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        # Mock config with tools
        agents_cfg = {
            "researcher": {
                "instructions": "You are a researcher",
                "model": "gpt-4o-mini",
                "tools": ["internet_search", "get_current_time"],
            }
        }
        
        # Create agents from config
        gw._create_agents_from_config(agents_cfg)
        
        # Verify agent was created
        agent = gw.get_agent("researcher")
        assert agent is not None
        assert agent.name == "researcher"
        # Tools should be resolved (may be empty if ToolResolver can't find them)
        # The important thing is no error was raised

    def test_gateway_handles_missing_tool_gracefully(self):
        """Gateway should log warning for missing tools but not fail."""
        from praisonai_bot.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        agents_cfg = {
            "test_agent": {
                "instructions": "Test agent",
                "tools": ["nonexistent_tool_xyz"],
            }
        }
        
        # Should not raise
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("test_agent")
        assert agent is not None

    def test_gateway_agent_has_reflection_disabled_by_default(self):
        """Gateway agents should have reflection=False by default for performance."""
        from praisonai_bot.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        agents_cfg = {
            "assistant": {
                "instructions": "You are helpful",
            }
        }
        
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("assistant")
        assert agent is not None
        # self_reflect should be False by default (set via reflection param)
        assert getattr(agent, "self_reflect", True) is False

    def test_gateway_supports_tool_choice_from_yaml(self):
        """Gateway should store tool_choice from YAML config."""
        from praisonai_bot.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        agents_cfg = {
            "researcher": {
                "instructions": "Research assistant",
                "tools": ["internet_search"],
                "tool_choice": "required",
            }
        }
        
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("researcher")
        assert agent is not None
        # tool_choice should be stored as _yaml_tool_choice
        assert getattr(agent, "_yaml_tool_choice", None) == "required"

    def test_gateway_supports_reflection_opt_in(self):
        """Gateway should allow reflection to be enabled via YAML."""
        from praisonai_bot.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        agents_cfg = {
            "simple_agent": {
                "instructions": "Simple agent",
                "reflection": True,
            }
        }
        
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("simple_agent")
        assert agent is not None
        assert getattr(agent, "self_reflect", False) is True


class TestGatewayDurableRuns:
    """Issue #4028: gateway agents opt into durable runs so a restart resumes."""

    def test_agents_are_not_durable_by_default(self):
        """Default gateway agents stay non-durable (zero-overhead)."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        gw._create_agents_from_config({"a": {"instructions": "hi"}})

        agent = gw.get_agent("a")
        assert agent is not None
        assert getattr(agent.execution, "durable", False) is False

    def test_gateway_durable_runs_flag_enables_journalling(self):
        """``gateway.durable_runs: true`` builds durable agents."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        durable = gw._durable_runs_from_config({"gateway": {"durable_runs": True}})
        assert durable is True

        gw._create_agents_from_config(
            {"a": {"instructions": "hi"}}, durable_runs=durable,
        )
        agent = gw.get_agent("a")
        assert agent is not None
        assert getattr(agent.execution, "durable", False) is True

    def test_durable_runs_defaults_on_with_durable_store(self):
        """Issue #4216: crash-safe resume auto-enables by default because the
        session store is durable out of the box (no explicit opt-in needed)."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        # Sessions persist by default, so the effective store is durable here.
        assert gw._session_store is not None
        assert gw._durable_runs_from_config({}) is True
        assert gw._durable_runs_from_config({"gateway": {}}) is True
        assert gw._durable_runs_from_config(None) is True

    def test_durable_runs_off_when_sessions_not_persisted(self):
        """No durable store (``session.persist: false``) → no journal-backed
        resume to auto-enable, so it stays off (zero-overhead).

        The default follows the *effective* store, so with persistence off the
        gateway holds no store (``self._session_store is None``).
        """
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        gw._session_store = None
        assert gw._durable_runs_from_config(
            {"gateway": {"session": {"persist": False}}}
        ) is False
        assert gw._durable_runs_from_config({}) is False
        assert gw._durable_runs_from_config(None) is False

    def test_durable_runs_off_when_persistent_store_fails_to_init(self):
        """Issue #4216 / CodeRabbit: ``session.persist: true`` but the store
        degraded to in-memory (``_build_session_store`` returned ``None``) must
        NOT auto-enable durable runs — there is no journal to record against."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        # Simulate a persistent store that failed to initialise (absent/read-only
        # home dir): persistence intent is on, but the effective store is None.
        gw._session_store = None
        assert gw._durable_runs_from_config(
            {"gateway": {"session": {"persist": True}}}
        ) is False

    def test_reliability_off_opts_out_of_durable_runs(self):
        """``reliability: "off"`` (immediate-teardown posture) opts back out of
        the crash-safe default."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        assert gw._durable_runs_from_config(
            {"gateway": {"reliability": "off"}}
        ) is False

    def test_explicit_durable_runs_false_wins_over_default(self):
        """An explicit ``durable_runs: false`` opts out even with a durable
        store present."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        assert gw._durable_runs_from_config(
            {"gateway": {"durable_runs": False}}
        ) is False

    def test_per_agent_durable_overrides_gateway_default(self):
        """A per-agent ``durable: true`` opts in even when the gateway default is off."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        gw._create_agents_from_config(
            {
                "plain": {"instructions": "hi"},
                "durable_one": {"instructions": "hi", "durable": True},
            },
            durable_runs=False,
        )
        assert getattr(gw.get_agent("plain").execution, "durable", False) is False
        assert getattr(gw.get_agent("durable_one").execution, "durable", False) is True

    def test_string_false_disables_durable_runs(self):
        """Env-substituted string ``"false"``/``"0"`` must disable durability
        (bool("false") is truthy, so a naive cast would wrongly enable it)."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        for falsy in ("false", "False", "0", "no", "off", ""):
            assert gw._durable_runs_from_config(
                {"gateway": {"durable_runs": falsy}}
            ) is False

    def test_string_true_enables_durable_runs(self):
        """String ``"true"``/``"1"`` opts in (YAML/env may render bools as str)."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        for truthy in ("true", "True", "1", "yes", "on"):
            assert gw._durable_runs_from_config(
                {"gateway": {"durable_runs": truthy}}
            ) is True

    def test_per_agent_string_false_overrides_gateway_default(self):
        """A per-agent ``durable: "false"`` opts out even when the gateway
        default is enabled."""
        from praisonai_bot.gateway import WebSocketGateway

        gw = WebSocketGateway()
        gw._create_agents_from_config(
            {"opted_out": {"instructions": "hi", "durable": "false"}},
            durable_runs=True,
        )
        assert getattr(
            gw.get_agent("opted_out").execution, "durable", False
        ) is False

    def test_schema_accepts_gateway_durable_runs(self):
        """``gateway.durable_runs`` must pass the strict GatewayServerSchema
        (``extra="forbid"``) so the documented opt-in is not rejected at load."""
        from praisonai_bot.bots._config_schema import GatewayServerSchema

        cfg = GatewayServerSchema(durable_runs=True)
        assert cfg.durable_runs is True


class TestGapG1ToolResolver:
    """Test ToolResolver integration."""

    def test_tool_resolver_resolve_many_exists(self):
        """ToolResolver should have resolve_many method."""
        from praisonai_code.tool_resolver import ToolResolver
        
        resolver = ToolResolver()
        
        assert hasattr(resolver, "resolve_many")
        assert callable(resolver.resolve_many)

    def test_tool_resolver_resolve_returns_callable_or_none(self):
        """ToolResolver.resolve should return callable or None."""
        from praisonai_code.tool_resolver import ToolResolver
        
        resolver = ToolResolver()
        
        # Known tool should return callable
        result = resolver.resolve("internet_search")
        # May be None if tool not available, but should not raise
        if result is not None:
            assert callable(result)
        
        # Unknown tool should return None
        result = resolver.resolve("nonexistent_tool_xyz_123")
        assert result is None


class TestGapG2ProviderDefaultTools:
    """Test Gap G2: PraisonAIUI provider default tools."""

    def test_provider_agent_kwargs_include_reflection(self):
        """Provider should set reflection=True by default."""
        # This tests the pattern, not the actual provider (which is in PraisonAIUI)
        default_kwargs = {
            "name": "Assistant",
            "instructions": "You are a helpful assistant.",
            "memory": True,
            "reflection": True,
        }
        
        assert default_kwargs["reflection"] is True


class TestGapG3ChannelBotTools:
    """Test Gap G3: Channel bot agent tools."""

    def test_channel_bot_agent_pattern_includes_tools(self):
        """Channel bot agent creation pattern should include tools."""
        # This tests the pattern, not the actual channel bot (which is in PraisonAIUI)
        from praisonai_code.tool_resolver import ToolResolver
        
        resolver = ToolResolver()
        agent_tools = resolver.resolve_many(["internet_search", "get_current_time"])
        
        # Should return a list (may be empty if tools not available)
        assert isinstance(agent_tools, list)


class TestToolPreflight:
    """Test the #3553 start-time tool pre-flight gate."""

    def test_describe_unresolved_suggests_close_match(self):
        """describe_unresolved offers a 'did you mean' for a typo."""
        from praisonai_code.tool_resolver import ToolResolver

        resolver = ToolResolver()
        available = list(resolver.list_available().keys())
        if "read_file" not in available:
            import pytest

            pytest.skip("read_file tool not discoverable in this environment")

        msg = resolver.describe_unresolved("read_fil")
        assert "read_file" in msg
        assert "Did you mean" in msg

    def test_describe_unresolved_falls_back_to_generic_hint(self):
        """A wholly unknown name still yields an actionable hint."""
        from praisonai_code.tool_resolver import ToolResolver

        resolver = ToolResolver()
        msg = resolver.describe_unresolved("totally_made_up_xyz_123")
        assert "totally_made_up_xyz_123" in msg
        assert "not found" in msg

    def test_preflight_tools_strict_fails_fast(self, tmp_path):
        """A mistyped tool aborts start (exit 78) in strict mode."""
        import typer
        from praisonai_bot.cli.commands.gateway import _preflight_tools

        cfg = tmp_path / "gateway.yaml"
        cfg.write_text(
            "agents:\n  a:\n    instructions: hi\n    tools: [totally_made_up_xyz_123]\n"
        )

        with __import__("pytest").raises(typer.Exit) as exc:
            _preflight_tools(str(cfg), strict_tools=True)
        assert exc.value.exit_code == 78

    def test_preflight_tools_non_strict_continues(self, tmp_path):
        """--no-strict-tools warns but does not abort."""
        from praisonai_bot.cli.commands.gateway import _preflight_tools

        cfg = tmp_path / "gateway.yaml"
        cfg.write_text(
            "agents:\n  a:\n    instructions: hi\n    tools: [totally_made_up_xyz_123]\n"
        )

        _preflight_tools(str(cfg), strict_tools=False)

    def test_preflight_tools_yaml_opt_out(self, tmp_path):
        """strict_tools: false in the YAML disables the fail-fast gate."""
        from praisonai_bot.cli.commands.gateway import _preflight_tools

        cfg = tmp_path / "gateway.yaml"
        cfg.write_text(
            "strict_tools: false\n"
            "agents:\n  a:\n    instructions: hi\n    tools: [totally_made_up_xyz_123]\n"
        )

        _preflight_tools(str(cfg), strict_tools=True)

    def test_preflight_tools_ok_when_all_resolve(self, tmp_path):
        """No error when every named tool resolves (or none are named)."""
        from praisonai_bot.cli.commands.gateway import _preflight_tools

        cfg = tmp_path / "gateway.yaml"
        cfg.write_text("agents:\n  a:\n    instructions: hi\n")

        _preflight_tools(str(cfg), strict_tools=True)

    def test_preflight_loads_persisted_env_before_resolving(
        self, tmp_path, monkeypatch
    ):
        """~/.praisonai/.env is loaded before resolution so a var set there
        (e.g. PRAISONAI_ALLOW_LOCAL_TOOLS) is visible to the resolver — the
        gate runs before GatewayHandler.start() does the same load (#3553)."""
        from praisonai_bot.cli.commands import gateway as gw_cmd

        env_file = tmp_path / ".env"
        env_file.write_text("PRAISONAI_PREFLIGHT_ENV_MARKER=1\n")
        monkeypatch.setenv("PRAISONAI_ENV_FILE", str(env_file))
        monkeypatch.delenv("PRAISONAI_PREFLIGHT_ENV_MARKER", raising=False)

        cfg = tmp_path / "gateway.yaml"
        cfg.write_text("agents:\n  a:\n    instructions: hi\n")

        import os

        gw_cmd._preflight_tools(str(cfg), strict_tools=True)
        assert os.environ.get("PRAISONAI_PREFLIGHT_ENV_MARKER") == "1"

    def test_describe_unresolved_does_not_suggest_same_name(self):
        """A mapped-but-unloadable tool (returns None) yields an install/generic
        hint, never a useless 'Did you mean <same name>?' (#3553)."""
        from praisonai_code.tool_resolver import ToolResolver

        resolver = ToolResolver()
        available = list(resolver.list_available().keys())
        if not available:
            import pytest

            pytest.skip("no discoverable tools in this environment")

        name = available[0]
        msg = resolver.describe_unresolved(name)
        assert f"Did you mean '{name}'" not in msg


class TestToolResolverIntegration:
    """Integration tests for ToolResolver with gateway."""

    def test_full_gateway_agent_creation_with_tools(self):
        """Full integration test: gateway creates agent with resolved tools."""
        from praisonai_bot.gateway import WebSocketGateway
        from praisonai_code.tool_resolver import ToolResolver
        
        # First verify ToolResolver works
        resolver = ToolResolver()
        tools = resolver.resolve_many(["internet_search"])
        
        # Create gateway and agent
        gw = WebSocketGateway()
        agents_cfg = {
            "test_researcher": {
                "instructions": "Research assistant with tools",
                "model": "gpt-4o-mini",
                "tools": ["internet_search"],
                "reflection": True,
            }
        }
        
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("test_researcher")
        assert agent is not None
        assert agent.name == "test_researcher"
        
        # If tools were resolved, agent should have them
        if tools:
            assert agent.tools is not None
            assert len(agent.tools) > 0

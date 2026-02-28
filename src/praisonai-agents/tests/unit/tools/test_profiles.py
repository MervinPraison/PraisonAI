"""
TDD Tests for ToolProfile system.

Tests the ToolProfile dataclass, built-in profiles, and profile resolution.
"""

import pytest


class TestToolProfileDataclass:
    """Test ToolProfile dataclass structure."""
    
    def test_tool_profile_has_required_fields(self):
        """ToolProfile should have name, tools, and description fields."""
        from praisonaiagents.tools.profiles import ToolProfile
        
        profile = ToolProfile(
            name="test",
            tools=["tool1", "tool2"],
            description="Test profile"
        )
        
        assert profile.name == "test"
        assert profile.tools == ["tool1", "tool2"]
        assert profile.description == "Test profile"
    
    def test_tool_profile_description_optional(self):
        """ToolProfile description should default to empty string."""
        from praisonaiagents.tools.profiles import ToolProfile
        
        profile = ToolProfile(name="test", tools=["tool1"])
        
        assert profile.description == ""
    
    def test_tool_profile_is_dataclass(self):
        """ToolProfile should be a dataclass."""
        from dataclasses import is_dataclass
        from praisonaiagents.tools.profiles import ToolProfile
        
        assert is_dataclass(ToolProfile)


class TestBuiltinProfiles:
    """Test built-in profiles are defined correctly."""
    
    def test_builtin_profiles_dict_exists(self):
        """BUILTIN_PROFILES dict should exist."""
        from praisonaiagents.tools.profiles import BUILTIN_PROFILES
        
        assert isinstance(BUILTIN_PROFILES, dict)
        assert len(BUILTIN_PROFILES) > 0
    
    def test_code_intelligence_profile_exists(self):
        """code_intelligence profile should include ast-grep tools."""
        from praisonaiagents.tools.profiles import BUILTIN_PROFILES
        
        assert "code_intelligence" in BUILTIN_PROFILES
        profile = BUILTIN_PROFILES["code_intelligence"]
        assert "ast_grep_search" in profile.tools
        assert "ast_grep_rewrite" in profile.tools
        assert "ast_grep_scan" in profile.tools
    
    def test_file_ops_profile_exists(self):
        """file_ops profile should include file operation tools."""
        from praisonaiagents.tools.profiles import BUILTIN_PROFILES
        
        assert "file_ops" in BUILTIN_PROFILES
        profile = BUILTIN_PROFILES["file_ops"]
        assert "read_file" in profile.tools
        assert "write_file" in profile.tools
        assert "list_files" in profile.tools
    
    def test_shell_profile_exists(self):
        """shell profile should include shell tools."""
        from praisonaiagents.tools.profiles import BUILTIN_PROFILES
        
        assert "shell" in BUILTIN_PROFILES
        profile = BUILTIN_PROFILES["shell"]
        assert "execute_command" in profile.tools
    
    def test_web_profile_exists(self):
        """web profile should include web search tools."""
        from praisonaiagents.tools.profiles import BUILTIN_PROFILES
        
        assert "web" in BUILTIN_PROFILES
        profile = BUILTIN_PROFILES["web"]
        assert "internet_search" in profile.tools or "search_web" in profile.tools
    
    def test_code_exec_profile_exists(self):
        """code_exec profile should include code execution tools."""
        from praisonaiagents.tools.profiles import BUILTIN_PROFILES
        
        assert "code_exec" in BUILTIN_PROFILES
        profile = BUILTIN_PROFILES["code_exec"]
        assert "execute_code" in profile.tools
    
    def test_schedule_profile_exists(self):
        """schedule profile should include schedule tools."""
        from praisonaiagents.tools.profiles import BUILTIN_PROFILES
        
        assert "schedule" in BUILTIN_PROFILES
        profile = BUILTIN_PROFILES["schedule"]
        assert "schedule_add" in profile.tools
        assert "schedule_list" in profile.tools
        assert "schedule_remove" in profile.tools


class TestAutonomyProfile:
    """Test the composite AUTONOMY_PROFILE."""
    
    def test_autonomy_profile_exists(self):
        """AUTONOMY_PROFILE should exist."""
        from praisonaiagents.tools.profiles import AUTONOMY_PROFILE
        
        assert AUTONOMY_PROFILE is not None
        assert AUTONOMY_PROFILE.name == "autonomy"
    
    def test_autonomy_profile_includes_file_ops(self):
        """AUTONOMY_PROFILE should include file_ops tools."""
        from praisonaiagents.tools.profiles import AUTONOMY_PROFILE
        
        assert "read_file" in AUTONOMY_PROFILE.tools
        assert "write_file" in AUTONOMY_PROFILE.tools
    
    def test_autonomy_profile_includes_shell(self):
        """AUTONOMY_PROFILE should include shell tools."""
        from praisonaiagents.tools.profiles import AUTONOMY_PROFILE
        
        assert "execute_command" in AUTONOMY_PROFILE.tools
    
    def test_autonomy_profile_includes_web(self):
        """AUTONOMY_PROFILE should include web tools."""
        from praisonaiagents.tools.profiles import AUTONOMY_PROFILE
        
        assert "internet_search" in AUTONOMY_PROFILE.tools or "search_web" in AUTONOMY_PROFILE.tools
    
    def test_autonomy_profile_includes_code_intelligence(self):
        """AUTONOMY_PROFILE should include code_intelligence tools."""
        from praisonaiagents.tools.profiles import AUTONOMY_PROFILE
        
        assert "ast_grep_search" in AUTONOMY_PROFILE.tools
    
    def test_autonomy_profile_has_many_tools(self):
        """AUTONOMY_PROFILE should have 15+ tools (not just 3)."""
        from praisonaiagents.tools.profiles import AUTONOMY_PROFILE
        
        assert len(AUTONOMY_PROFILE.tools) >= 15, f"Expected 15+ tools, got {len(AUTONOMY_PROFILE.tools)}"


class TestProfileRegistry:
    """Test profile registration and retrieval."""
    
    def test_get_profile_returns_builtin(self):
        """get_profile should return built-in profiles."""
        from praisonaiagents.tools.profiles import get_profile
        
        profile = get_profile("file_ops")
        assert profile.name == "file_ops"
        assert "read_file" in profile.tools
    
    def test_get_profile_raises_for_unknown(self):
        """get_profile should raise KeyError for unknown profiles."""
        from praisonaiagents.tools.profiles import get_profile
        
        with pytest.raises(KeyError):
            get_profile("nonexistent_profile")
    
    def test_register_profile_adds_custom(self):
        """register_profile should add custom profiles."""
        from praisonaiagents.tools.profiles import (
            ToolProfile, register_profile, get_profile, _custom_profiles
        )
        
        # Clean up any previous test registrations
        if "test_custom" in _custom_profiles:
            del _custom_profiles["test_custom"]
        
        custom = ToolProfile(
            name="test_custom",
            tools=["custom_tool1", "custom_tool2"],
            description="Test custom profile"
        )
        register_profile(custom)
        
        retrieved = get_profile("test_custom")
        assert retrieved.name == "test_custom"
        assert "custom_tool1" in retrieved.tools
        
        # Cleanup
        del _custom_profiles["test_custom"]
    
    def test_custom_profile_overrides_builtin(self):
        """Custom profiles should override built-in profiles with same name."""
        from praisonaiagents.tools.profiles import (
            ToolProfile, register_profile, get_profile, _custom_profiles
        )
        
        # Register a custom profile with same name as builtin
        custom = ToolProfile(
            name="file_ops",
            tools=["custom_read", "custom_write"],
            description="Custom file ops"
        )
        register_profile(custom)
        
        retrieved = get_profile("file_ops")
        assert "custom_read" in retrieved.tools
        
        # Cleanup - restore original
        del _custom_profiles["file_ops"]


class TestResolveProfiles:
    """Test resolve_profiles function."""
    
    def test_resolve_single_profile(self):
        """resolve_profiles should return tools from a single profile."""
        from praisonaiagents.tools.profiles import resolve_profiles
        
        tools = resolve_profiles("file_ops")
        assert "read_file" in tools
        assert "write_file" in tools
    
    def test_resolve_multiple_profiles(self):
        """resolve_profiles should combine tools from multiple profiles."""
        from praisonaiagents.tools.profiles import resolve_profiles
        
        tools = resolve_profiles("file_ops", "shell")
        assert "read_file" in tools
        assert "execute_command" in tools
    
    def test_resolve_profiles_deduplicates(self):
        """resolve_profiles should deduplicate tools."""
        from praisonaiagents.tools.profiles import resolve_profiles
        
        # autonomy includes file_ops, so calling both should not duplicate
        tools = resolve_profiles("autonomy")
        
        # Count occurrences of read_file
        count = tools.count("read_file")
        assert count == 1, f"Expected 1 occurrence of read_file, got {count}"
    
    def test_resolve_profiles_returns_list(self):
        """resolve_profiles should return a list."""
        from praisonaiagents.tools.profiles import resolve_profiles
        
        tools = resolve_profiles("shell")
        assert isinstance(tools, list)
    
    def test_resolve_profiles_raises_for_unknown(self):
        """resolve_profiles should raise KeyError for unknown profiles."""
        from praisonaiagents.tools.profiles import resolve_profiles
        
        with pytest.raises(KeyError):
            resolve_profiles("nonexistent")


class TestAgentAutonomyWithProfiles:
    """Test that Agent with autonomy=True uses AUTONOMY_PROFILE tools."""
    
    def test_agent_autonomy_gets_profile_tools_when_no_tools_provided(self):
        """Agent(autonomy=True) with no tools should get AUTONOMY_PROFILE tools."""
        from praisonaiagents import Agent
        
        # No tools provided - should inject AUTONOMY_PROFILE
        agent = Agent(
            name="test",
            instructions="Test agent",
            autonomy=True,
        )
        
        # Should have more than just 3 ast-grep tools
        assert len(agent.tools) >= 15, f"Expected 15+ tools, got {len(agent.tools)}"
        
        # Check for file_ops tools
        tool_names = [getattr(t, '__name__', str(t)) for t in agent.tools]
        # At least one of these should be present
        has_file_tool = any(name in tool_names for name in ['read_file', 'write_file', 'list_files'])
        assert has_file_tool or len(agent.tools) >= 15, f"Expected file tools, got: {tool_names}"
    
    def test_agent_autonomy_does_not_inject_when_tools_provided(self):
        """Agent(autonomy=True) with tools should NOT inject AUTONOMY_PROFILE (avoid duplicates)."""
        from praisonaiagents import Agent
        
        def my_tool():
            """My custom tool."""
            return "custom"
        
        # Tools provided - should NOT inject AUTONOMY_PROFILE
        agent = Agent(
            name="test",
            instructions="Test agent",
            tools=[my_tool],
            autonomy=True,
        )
        
        # Should only have the user-provided tool, not AUTONOMY_PROFILE
        assert len(agent.tools) == 1, f"Expected 1 tool (user-provided), got {len(agent.tools)}"
        assert my_tool in agent.tools
    
    def test_agent_custom_default_tools_override(self):
        """Agent with custom default_tools should use those instead."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        def custom_tool():
            """Custom tool."""
            return "custom"
        
        config = AutonomyConfig(default_tools=[custom_tool])
        agent = Agent(
            name="test",
            instructions="Test agent",
            autonomy=config,
        )
        
        # Should have only the custom tool
        assert custom_tool in agent.tools
        # Should NOT have the full autonomy profile
        assert len(agent.tools) == 1
    
    def test_agent_empty_default_tools_disables_injection(self):
        """Agent with default_tools=[] should have no auto-injected tools."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig(default_tools=[])
        agent = Agent(
            name="test",
            instructions="Test agent",
            autonomy=config,
        )
        
        # Should have no tools
        assert len(agent.tools) == 0


class TestProfileExports:
    """Test that profiles are properly exported."""
    
    def test_import_from_tools_package(self):
        """ToolProfile should be importable from praisonaiagents.tools."""
        from praisonaiagents.tools import ToolProfile
        
        assert ToolProfile is not None
    
    def test_import_register_profile(self):
        """register_profile should be importable from praisonaiagents.tools."""
        from praisonaiagents.tools import register_profile
        
        assert callable(register_profile)
    
    def test_import_resolve_profiles(self):
        """resolve_profiles should be importable from praisonaiagents.tools."""
        from praisonaiagents.tools import resolve_profiles
        
        assert callable(resolve_profiles)
    
    def test_import_autonomy_profile(self):
        """AUTONOMY_PROFILE should be importable from praisonaiagents.tools."""
        from praisonaiagents.tools import AUTONOMY_PROFILE
        
        assert AUTONOMY_PROFILE is not None

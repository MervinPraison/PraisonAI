"""
Tests for Agent Profiles and Modes.

TDD: Tests for built-in agent profiles and mode configurations.
"""

from praisonaiagents.agents.profiles import (
    AgentMode,
    AgentProfile,
    get_profile,
    list_profiles,
    register_profile,
    get_profiles_by_mode,
    BUILTIN_PROFILES,
)


class TestAgentMode:
    """Tests for AgentMode enum."""
    
    def test_mode_values(self):
        """Test mode enum values."""
        assert AgentMode.PRIMARY.value == "primary"
        assert AgentMode.SUBAGENT.value == "subagent"
        assert AgentMode.ALL.value == "all"


class TestAgentProfile:
    """Tests for AgentProfile."""
    
    def test_profile_creation(self):
        """Test basic profile creation."""
        profile = AgentProfile(
            name="test",
            description="Test agent",
            mode=AgentMode.PRIMARY
        )
        
        assert profile.name == "test"
        assert profile.description == "Test agent"
        assert profile.mode == AgentMode.PRIMARY
    
    def test_profile_defaults(self):
        """Test profile default values."""
        profile = AgentProfile(name="test")
        
        assert profile.mode == AgentMode.ALL
        assert profile.temperature == 0.7
        assert profile.top_p == 1.0
        assert profile.max_steps == 50
        assert profile.hidden is False
    
    def test_profile_serialization(self):
        """Test profile round-trip."""
        profile = AgentProfile(
            name="test",
            description="Test",
            mode=AgentMode.SUBAGENT,
            tools=["read_file", "bash"],
            temperature=0.5,
        )
        
        d = profile.to_dict()
        restored = AgentProfile.from_dict(d)
        
        assert restored.name == profile.name
        assert restored.mode == profile.mode
        assert restored.tools == profile.tools
        assert restored.temperature == profile.temperature


class TestBuiltinProfiles:
    """Tests for built-in profiles."""
    
    def test_general_profile_exists(self):
        """Test general profile exists."""
        profile = get_profile("general")
        
        assert profile is not None
        assert profile.name == "general"
        assert profile.mode == AgentMode.PRIMARY
    
    def test_coder_profile_exists(self):
        """Test coder profile exists."""
        profile = get_profile("coder")
        
        assert profile is not None
        assert profile.name == "coder"
    
    def test_planner_profile_exists(self):
        """Test planner profile exists."""
        profile = get_profile("planner")
        
        assert profile is not None
        assert profile.mode == AgentMode.SUBAGENT
    
    def test_reviewer_profile_exists(self):
        """Test reviewer profile exists."""
        profile = get_profile("reviewer")
        
        assert profile is not None
    
    def test_explorer_profile_exists(self):
        """Test explorer profile exists."""
        profile = get_profile("explorer")
        
        assert profile is not None
    
    def test_debugger_profile_exists(self):
        """Test debugger profile exists."""
        profile = get_profile("debugger")
        
        assert profile is not None
    
    def test_hidden_profiles(self):
        """Test hidden profiles exist."""
        compaction = get_profile("compaction")
        title = get_profile("title")
        
        assert compaction is not None
        assert compaction.hidden is True
        
        assert title is not None
        assert title.hidden is True
    
    def test_nonexistent_profile(self):
        """Test getting non-existent profile."""
        profile = get_profile("nonexistent")
        
        assert profile is None


class TestListProfiles:
    """Tests for listing profiles."""
    
    def test_list_profiles(self):
        """Test listing profiles."""
        profiles = list_profiles()
        
        assert len(profiles) > 0
        names = [p.name for p in profiles]
        assert "general" in names
        assert "coder" in names
    
    def test_list_profiles_excludes_hidden(self):
        """Test that hidden profiles are excluded by default."""
        profiles = list_profiles(include_hidden=False)
        
        names = [p.name for p in profiles]
        assert "compaction" not in names
        assert "title" not in names
    
    def test_list_profiles_includes_hidden(self):
        """Test including hidden profiles."""
        profiles = list_profiles(include_hidden=True)
        
        names = [p.name for p in profiles]
        assert "compaction" in names
        assert "title" in names


class TestRegisterProfile:
    """Tests for registering custom profiles."""
    
    def test_register_profile(self):
        """Test registering a custom profile."""
        custom = AgentProfile(
            name="custom_test",
            description="Custom test agent",
            mode=AgentMode.PRIMARY,
        )
        
        register_profile(custom)
        
        retrieved = get_profile("custom_test")
        assert retrieved is not None
        assert retrieved.name == "custom_test"
        
        # Cleanup
        if "custom_test" in BUILTIN_PROFILES:
            del BUILTIN_PROFILES["custom_test"]


class TestGetProfilesByMode:
    """Tests for getting profiles by mode."""
    
    def test_get_primary_profiles(self):
        """Test getting primary mode profiles."""
        profiles = get_profiles_by_mode(AgentMode.PRIMARY)
        
        assert len(profiles) > 0
        # Should include PRIMARY and ALL mode profiles
        for p in profiles:
            assert p.mode in (AgentMode.PRIMARY, AgentMode.ALL)
    
    def test_get_subagent_profiles(self):
        """Test getting subagent mode profiles."""
        profiles = get_profiles_by_mode(AgentMode.SUBAGENT)
        
        assert len(profiles) > 0
        # Should include SUBAGENT and ALL mode profiles
        for p in profiles:
            assert p.mode in (AgentMode.SUBAGENT, AgentMode.ALL)
    
    def test_all_mode_in_both(self):
        """Test that ALL mode profiles appear in both."""
        primary = get_profiles_by_mode(AgentMode.PRIMARY)
        subagent = get_profiles_by_mode(AgentMode.SUBAGENT)
        
        primary_names = {p.name for p in primary}
        subagent_names = {p.name for p in subagent}
        
        # Coder is ALL mode, should be in both
        assert "coder" in primary_names
        assert "coder" in subagent_names

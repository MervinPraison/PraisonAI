"""Tests for skill capability validation."""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch

from praisonaiagents.skills.models import SkillProperties, SkillRequirements, SkillState
from praisonaiagents.skills.capability_validator import (
    CapabilityValidator, 
    EnforcementLevel,
    ValidationResult
)


class TestSkillRequirements:
    """Test SkillRequirements parsing and normalization."""
    
    def test_from_frontmatter_empty(self):
        """Test parsing empty frontmatter."""
        requirements = SkillRequirements.from_frontmatter({})
        assert requirements.is_empty()
        assert not requirements  # Test __bool__
        
    def test_from_frontmatter_tools_list(self):
        """Test parsing tools from list."""
        metadata = {"requires_tools": ["web_search", "file_write"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.tools == ["web_search", "file_write"]
        assert requirements.servers == []
        assert not requirements.is_empty()
        
    def test_from_frontmatter_tools_string(self):
        """Test parsing tools from string."""
        metadata = {"requires-tools": "web_search file_write"}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.tools == ["web_search", "file_write"]
        
    def test_from_frontmatter_backward_compatibility(self):
        """Test backward compatibility with allowed-tools."""
        metadata = {"allowed-tools": ["existing_tool"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.tools == ["existing_tool"]
        
    def test_from_frontmatter_servers(self):
        """Test parsing server requirements."""
        metadata = {"requires_servers": ["mcp:filesystem", "http:internal"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.servers == ["mcp:filesystem", "http:internal"]
        
    def test_from_frontmatter_env_vars(self):
        """Test parsing environment variable requirements."""
        metadata = {"requires_env": ["API_KEY", "SECRET_TOKEN"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.env_vars == ["API_KEY", "SECRET_TOKEN"]
        
    def test_from_frontmatter_openclaw_hints(self):
        """Test parsing OpenClaw hints."""
        metadata = {"openclaw": {"version": "1.0", "compatibility": "hermes"}}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.openclaw_hints == {"version": "1.0", "compatibility": "hermes"}
        
    def test_from_frontmatter_fallback_for_tools(self):
        """Test parsing fallback_for_tools (graceful degradation)."""
        metadata = {"fallback_for_tools": ["web_search", "web"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.fallback_for_tools == ["web_search", "web"]
        assert requirements.fallback_for_servers == []
        assert not requirements.is_empty()

    def test_from_frontmatter_fallback_for_servers(self):
        """Test parsing fallback_for_servers (graceful degradation)."""
        metadata = {"fallback-for-servers": "mcp:filesystem"}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.fallback_for_servers == ["mcp:filesystem"]
        assert not requirements.is_empty()

    def test_from_frontmatter_fallback_with_requires(self):
        """Fallback declarations compose with existing requires_* gates."""
        metadata = {
            "requires_tools": ["terminal"],
            "fallback_for_tools": ["web_search", "web"],
        }
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.tools == ["terminal"]
        assert requirements.fallback_for_tools == ["web_search", "web"]

    def test_normalize_list(self):
        """Test list normalization utility."""
        assert SkillRequirements._normalize_list("a b c") == ["a", "b", "c"]
        assert SkillRequirements._normalize_list("a,b,c") == ["a", "b", "c"]
        assert SkillRequirements._normalize_list("a, b c") == ["a", "b", "c"]
        assert SkillRequirements._normalize_list(["a", "b", "c"]) == ["a", "b", "c"]
        assert SkillRequirements._normalize_list("") == []
        assert SkillRequirements._normalize_list([]) == []
        assert SkillRequirements._normalize_list(123) == []


class TestCapabilityValidator:
    """Test capability validation logic."""
    
    def test_enforcement_levels(self):
        """Test different enforcement levels."""
        assert EnforcementLevel.DISABLED.value == "disabled"
        assert EnforcementLevel.WARN.value == "warn" 
        assert EnforcementLevel.STRICT.value == "strict"
        
    def test_validator_initialization(self):
        """Test validator initialization."""
        validator = CapabilityValidator()
        assert validator.enforcement_level == EnforcementLevel.WARN
        
        validator = CapabilityValidator(EnforcementLevel.STRICT)
        assert validator.enforcement_level == EnforcementLevel.STRICT
        
    def test_validate_skill_no_requirements(self):
        """Test validation of skill with no requirements."""
        skill = SkillProperties(
            name="test-skill",
            description="Test skill", 
            requirements=None
        )
        
        validator = CapabilityValidator()
        result = validator.validate_skill(skill)
        
        assert result.skill_name == "test-skill"
        assert result.state == SkillState.ACTIVE
        assert result.is_fully_satisfied
        assert not result.has_critical_missing
        
    def test_validate_skill_empty_requirements(self):
        """Test validation of skill with empty requirements."""
        requirements = SkillRequirements()
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator()
        result = validator.validate_skill(skill)
        
        assert result.state == SkillState.ACTIVE
        assert result.is_fully_satisfied
        
    @patch.dict(os.environ, {"TEST_VAR": "value"})
    def test_validate_skill_satisfied_requirements(self):
        """Test validation with all requirements satisfied."""
        requirements = SkillRequirements(
            tools=["available_tool"],
            servers=["available_server"],
            env_vars=["TEST_VAR"]
        )
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        available_tools = {"available_tool"}
        available_servers = {"available_server"}
        
        validator = CapabilityValidator()
        result = validator.validate_skill(
            skill, 
            available_tools=available_tools,
            available_servers=available_servers
        )
        
        assert result.state == SkillState.ACTIVE
        assert result.satisfied_tools == ["available_tool"]
        assert result.satisfied_servers == ["available_server"]
        assert result.satisfied_env_vars == ["TEST_VAR"]
        assert result.is_fully_satisfied
        
    def test_validate_skill_missing_tools_warn_mode(self):
        """Test validation with missing tools in warn mode."""
        requirements = SkillRequirements(tools=["missing_tool"])
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator(EnforcementLevel.WARN)
        result = validator.validate_skill(
            skill,
            available_tools=set(),
            available_servers=set()
        )
        
        assert result.state == SkillState.DEGRADED
        assert result.missing_tools == ["missing_tool"]
        assert not result.is_fully_satisfied
        assert result.has_critical_missing
        assert len(result.warnings) == 1
        assert "missing_tool" in result.warnings[0]
        
    def test_validate_skill_missing_tools_strict_mode(self):
        """Test validation with missing tools in strict mode."""
        requirements = SkillRequirements(tools=["missing_tool"])
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator(EnforcementLevel.STRICT)
        result = validator.validate_skill(
            skill,
            available_tools=set(),
            available_servers=set()
        )
        
        assert result.state == SkillState.UNAVAILABLE
        assert result.missing_tools == ["missing_tool"]
        assert not result.is_fully_satisfied
        assert result.has_critical_missing
        assert len(result.errors) == 1
        assert "missing_tool" in result.errors[0]
        
    def test_validate_skill_missing_env_vars_warn(self):
        """Test validation with missing environment variables in warn mode."""
        requirements = SkillRequirements(env_vars=["MISSING_VAR"])
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator(EnforcementLevel.WARN)
        result = validator.validate_skill(skill)
        
        assert result.state == SkillState.DEGRADED
        assert result.missing_env_vars == ["MISSING_VAR"]
        assert len(result.warnings) == 1
        assert len(result.errors) == 0

    def test_validate_skill_missing_env_vars_strict(self):
        """Test validation with missing environment variables in strict mode."""
        requirements = SkillRequirements(env_vars=["MISSING_VAR"])
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )

        validator = CapabilityValidator(EnforcementLevel.STRICT)
        result = validator.validate_skill(skill)

        assert result.state == SkillState.UNAVAILABLE
        assert result.missing_env_vars == ["MISSING_VAR"]
        assert len(result.warnings) == 0
        assert len(result.errors) == 1
        
    def test_available_servers_read_from_mcp_registry(self):
        """Issue #3307 Gap 3: _get_available_servers must reflect active MCP servers.

        Previously it was a stub returning an empty set, so any skill with an
        MCP-server requirement failed closed under STRICT enforcement no matter
        what was connected.
        """
        validator = CapabilityValidator(EnforcementLevel.STRICT)
        with patch(
            "praisonaiagents.mcp.mcp.MCP.list_active_server_names",
            return_value={"filesystem"},
        ):
            servers = validator._get_available_servers()
        assert "filesystem" in servers

    def test_available_servers_read_live_not_cached(self):
        """Issue #3307 Gap 3: server availability must not be cached stale.

        The MCP registry fills in as servers connect during a run, so a server
        registered after the first validation must become visible without an
        explicit clear_cache() call.
        """
        validator = CapabilityValidator(EnforcementLevel.STRICT)
        with patch(
            "praisonaiagents.mcp.mcp.MCP.list_active_server_names",
            return_value=set(),
        ):
            assert validator._get_available_servers() == set()
        with patch(
            "praisonaiagents.mcp.mcp.MCP.list_active_server_names",
            return_value={"filesystem"},
        ):
            assert "filesystem" in validator._get_available_servers()

    def test_mcp_gated_skill_passes_strict_when_server_active(self):
        """Issue #3307 Gap 3: an MCP-server-gated skill can now pass STRICT."""
        requirements = SkillRequirements(servers=["filesystem"])
        skill = SkillProperties(
            name="fs-skill",
            description="needs filesystem MCP server",
            requirements=requirements,
        )
        validator = CapabilityValidator(EnforcementLevel.STRICT)
        result = validator.validate_skill(
            skill,
            available_tools=set(),
            available_servers={"filesystem"},
        )
        assert result.state != SkillState.UNAVAILABLE
        assert result.satisfied_servers == ["filesystem"]

    def test_validation_result_to_dict(self):
        """Test ValidationResult serialization."""
        result = ValidationResult(
            skill_name="test-skill",
            state=SkillState.DEGRADED,
            satisfied_tools=["tool1"],
            missing_tools=["tool2"],
            satisfied_servers=[],
            missing_servers=[],
            satisfied_env_vars=[],
            missing_env_vars=["VAR1"],
            warnings=["Missing tool2"],
            errors=[]
        )
        
        data = result.to_dict()
        assert data["skill_name"] == "test-skill"
        assert data["state"] == "degraded"
        assert data["satisfied_tools"] == ["tool1"]
        assert data["missing_tools"] == ["tool2"]
        assert data["warnings"] == ["Missing tool2"]
        assert data["is_fully_satisfied"] == False
        assert data["has_critical_missing"] == True


class TestMCPRegistryLifecycle:
    """Regression tests for the MCP active-server refcount registry (issue #5135).

    The registry backs STRICT capability validation, so a disconnected server
    must disappear from ``list_active_server_names()`` once every owning MCP
    instance has shut down — including the common case where the raw server
    name is already a safe prefix (``prefix == sanitized``).
    """

    def _make_mcp(self):
        """Build a bare MCP instance without opening a real connection."""
        from praisonaiagents.mcp.mcp import MCP
        inst = object.__new__(MCP)
        inst._tools = []
        inst._tool_prefix = None
        return inst

    def _reset_registry(self):
        from praisonaiagents.mcp.mcp import MCP
        with MCP._active_server_names_lock:
            MCP._active_server_names.clear()

    def test_safe_name_released_after_shutdown(self):
        """An already-safe prefix (fs) must not leave a residual refcount."""
        from praisonaiagents.mcp.mcp import MCP
        self._reset_registry()
        mcp = self._make_mcp()
        mcp.with_tool_prefix("fs")  # prefix == sanitized == "fs"
        assert "fs" in MCP.list_active_server_names()
        assert MCP._active_server_names["fs"] == 1

        mcp.shutdown()
        assert "fs" not in MCP.list_active_server_names()

    def test_repeated_with_tool_prefix_no_residue(self):
        """Repeated with_tool_prefix() on one instance releases fully."""
        from praisonaiagents.mcp.mcp import MCP
        self._reset_registry()
        mcp = self._make_mcp()
        mcp.with_tool_prefix("docs")
        mcp.with_tool_prefix("docs")
        mcp.with_tool_prefix("docs")
        assert MCP._active_server_names["docs"] == 1

        mcp.shutdown()
        assert "docs" not in MCP.list_active_server_names()

    def test_name_stays_active_until_all_instances_shutdown(self):
        """Two instances sharing a name: released only after both shut down."""
        from praisonaiagents.mcp.mcp import MCP
        self._reset_registry()
        a = self._make_mcp()
        b = self._make_mcp()
        a.with_tool_prefix("shared")
        b.with_tool_prefix("shared")
        assert MCP._active_server_names["shared"] == 2

        a.shutdown()
        assert "shared" in MCP.list_active_server_names()
        b.shutdown()
        assert "shared" not in MCP.list_active_server_names()

    def test_double_shutdown_is_idempotent(self):
        """A second shutdown() must not underflow another holder's count."""
        from praisonaiagents.mcp.mcp import MCP
        self._reset_registry()
        a = self._make_mcp()
        b = self._make_mcp()
        a.with_tool_prefix("srv")
        b.with_tool_prefix("srv")

        a.shutdown()
        a.shutdown()  # idempotent — must not decrement b's hold
        assert MCP._active_server_names.get("srv") == 1
        b.shutdown()
        assert "srv" not in MCP.list_active_server_names()


class TestIntegration:
    """Integration tests for the full capability validation system."""
    
    def test_skill_parsing_with_requirements(self):
        """Test that skills parse requirements correctly."""
        from praisonaiagents.skills.parser import read_properties
        from tempfile import TemporaryDirectory
        
        with TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir) / "test-skill"
            skill_dir.mkdir()
            
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text('''---
name: test-skill
description: A test skill
requires_tools:
  - web_search
  - file_write
requires_servers:
  - mcp:filesystem
requires_env:
  - API_KEY
openclaw:
  version: "1.0"
---

# Test Skill

This is a test skill.
''')
            
            properties = read_properties(skill_dir)
            assert properties.requirements is not None
            assert properties.requirements.tools == ["web_search", "file_write"]
            assert properties.requirements.servers == ["mcp:filesystem"]
            assert properties.requirements.env_vars == ["API_KEY"]
            assert properties.requirements.openclaw_hints == {"version": "1.0"}
            
    def test_skill_manager_enforcement(self):
        """Test that SkillManager respects enforcement levels."""
        from praisonaiagents.skills.manager import SkillManager
        
        # Test that manager initializes with default enforcement
        manager = SkillManager()
        assert manager._validator.enforcement_level in [
            EnforcementLevel.WARN, 
            EnforcementLevel.DISABLED,
            EnforcementLevel.STRICT,
            EnforcementLevel.TELEMETRY
        ]
        
        # Test explicit enforcement level
        strict_manager = SkillManager(EnforcementLevel.STRICT)
        assert strict_manager._validator.enforcement_level == EnforcementLevel.STRICT

"""
Unit tests for MCP loader functionality.

Tests the smoke functionality for the new MCP client lifecycle
features implemented in this issue.
"""

import pytest
from unittest.mock import Mock, MagicMock
from praisonaiagents.memory.mcp_config import MCPConfig


def test_mcp_config_to_mcp_instance_import_fix():
    """Test that MCPConfig.to_mcp_instance() imports MCP correctly (A1)."""
    # Create a minimal config
    config = MCPConfig(
        name="test",
        command="echo",
        args=["hello"],
        enabled=True
    )
    
    # This should not raise ImportError anymore
    # Note: It might return None if MCP package is not installed, but the import should work
    try:
        result = config.to_mcp_instance()
        # If we get here without ImportError from wrong path, the fix worked
        assert True
    except ImportError as e:
        if "praisonaiagents.tools.mcp" in str(e):
            pytest.fail("Import still using wrong path - A1 fix failed")
        else:
            # This is expected if mcp package is not installed
            assert "praisonaiagents[mcp]" in str(e)


def test_load_mcp_tools_import():
    """Test that load_mcp_tools can be imported (B2)."""
    from praisonaiagents.mcp import load_mcp_tools
    assert callable(load_mcp_tools)


def test_mcp_client_protocol_import():
    """Test that MCPClientProtocol can be imported (B1)."""
    from praisonaiagents.mcp import MCPClientProtocol
    # Should be a protocol/type
    assert MCPClientProtocol is not None


def test_mcp_filter_parameters():
    """Test that MCP class accepts filter parameters (B3)."""
    try:
        from praisonaiagents.mcp import MCP
        # This should not raise TypeError for unknown parameters
        # Note: May raise ImportError if mcp package not installed
        mcp = MCP("echo hello", allowed_tools=["test"], disabled_tools=["bad"])
        assert mcp.allowed_tools == ["test"]
        assert mcp.disabled_tools == ["bad"]
    except ImportError as e:
        if "praisonaiagents[mcp]" in str(e):
            # Expected if MCP package not installed
            pytest.skip("MCP package not installed")
        else:
            raise


def test_filter_tool_functions_exist():
    """Test that filter functions exist and work (B3)."""
    from praisonaiagents.mcp.mcp_utils import filter_tools_by_allowlist, filter_disabled_tools
    
    tools = [
        {"name": "tool1", "description": "First tool"},
        {"name": "tool2", "description": "Second tool"},
        {"name": "tool3", "description": "Third tool"},
    ]
    
    # Test allowlist filtering
    filtered = filter_tools_by_allowlist(tools, ["tool1", "tool3"])
    assert len(filtered) == 2
    assert filtered[0]["name"] == "tool1"
    assert filtered[1]["name"] == "tool3"
    
    # Test disabled filtering
    filtered = filter_disabled_tools(tools, ["tool2"])
    assert len(filtered) == 2
    assert all(t["name"] != "tool2" for t in filtered)
    
    # Test precedence: include wins over exclude
    # This is handled at MCP class level, but filters should work independently


def test_prefix_collision_handling():
    """Test tool name prefix handling (B4)."""
    # The prefix logic is in the loader
    from praisonaiagents.mcp.loader import load_mcp_tools
    
    # Test that sanitization logic exists (basic check)
    # Full test would require mock MCP configs
    assert callable(load_mcp_tools)


class _FakeTool:
    """Minimal callable tool stub with a mutable __name__."""

    def __init__(self, name):
        self.__name__ = name
        self.__qualname__ = name

    def __call__(self, *args, **kwargs):  # pragma: no cover - not invoked
        return None


class _FakeMCP:
    """Lightweight stand-in for the real MCP client for loader tests."""

    def __init__(self, tool_names):
        self._tools = [_FakeTool(n) for n in tool_names]
        self._tool_prefix = None
        self.allowed_tools = None
        self.disabled_tools = None

    # Mirror the real MCP.with_tool_prefix behaviour (delegating sanitization
    # to the real MCP so the double can't drift from production logic).
    def with_tool_prefix(self, prefix):
        from praisonaiagents.mcp.mcp import MCP
        sanitized = MCP._sanitize_prefix(prefix or "")
        if not sanitized:
            raise ValueError(f"invalid prefix from {prefix!r}")
        self._tool_prefix = sanitized
        for tool in self._tools:
            original = getattr(tool, "__original_name__", tool.__name__)
            tool.__original_name__ = original
            tool.__name__ = f"{sanitized}_{original}"
        return self

    def _apply_tool_filters(self, tools):
        if self.allowed_tools:
            allowed = set(self.allowed_tools)
            return [t for t in tools if t.__name__ in allowed]
        if self.disabled_tools:
            disabled = set(self.disabled_tools)
            return [t for t in tools if t.__name__ not in disabled]
        return tools

    # Mirror the public MCP.apply_tool_filters contract used by the loader.
    def apply_tool_filters(self, allowed_tools=None, disabled_tools=None):
        if allowed_tools is not None:
            self.allowed_tools = allowed_tools
        if disabled_tools is not None:
            self.disabled_tools = disabled_tools
        if self.allowed_tools or self.disabled_tools:
            self._tools = self._apply_tool_filters(self._tools)
        return self


def _patch_configs(monkeypatch, mapping):
    """Patch MCPConfig.to_mcp_instance to return fake MCPs keyed by name."""
    from praisonaiagents.memory.mcp_config import MCPConfig

    def fake_to_instance(self):
        return mapping.get(self.name)

    monkeypatch.setattr(MCPConfig, "to_mcp_instance", fake_to_instance)


def test_multiple_servers_are_prefixed(monkeypatch):
    """Two servers sharing a tool name get namespaced (B4)."""
    from praisonaiagents.mcp.loader import load_mcp_tools
    from praisonaiagents.memory.mcp_config import MCPConfig

    fs = _FakeMCP(["read_file", "search"])
    gh = _FakeMCP(["search"])
    _patch_configs(monkeypatch, {"filesystem": fs, "github": gh})

    configs = [
        MCPConfig(name="filesystem", command="x"),
        MCPConfig(name="github", command="y"),
    ]
    result = load_mcp_tools(configs=configs)

    names = {t.__name__ for mcp in result for t in mcp._tools}
    assert names == {"filesystem_read_file", "filesystem_search", "github_search"}
    # Colliding 'search' is now disambiguated.
    assert "filesystem_search" in names
    assert "github_search" in names


def test_single_server_keeps_bare_names(monkeypatch):
    """Single-server loads must not gain gratuitous prefixes (backward compat)."""
    from praisonaiagents.mcp.loader import load_mcp_tools
    from praisonaiagents.memory.mcp_config import MCPConfig

    fs = _FakeMCP(["read_file", "search"])
    _patch_configs(monkeypatch, {"filesystem": fs})

    result = load_mcp_tools(configs=[MCPConfig(name="filesystem", command="x")])
    names = {t.__name__ for t in result[0]._tools}
    assert names == {"read_file", "search"}


def test_prefix_tools_false_disables_namespacing(monkeypatch):
    """prefix_tools=False keeps raw names even with multiple servers."""
    from praisonaiagents.mcp.loader import load_mcp_tools
    from praisonaiagents.memory.mcp_config import MCPConfig

    fs = _FakeMCP(["search"])
    gh = _FakeMCP(["search"])
    _patch_configs(monkeypatch, {"filesystem": fs, "github": gh})

    configs = [
        MCPConfig(name="filesystem", command="x"),
        MCPConfig(name="github", command="y"),
    ]
    result = load_mcp_tools(configs=configs, prefix_tools=False)
    for mcp in result:
        for tool in mcp._tools:
            assert tool.__name__ == "search"


def test_duplicate_server_name_raises(monkeypatch):
    """Same sanitized server name twice raises a clear error, not silent shadowing."""
    from praisonaiagents.mcp.loader import load_mcp_tools
    from praisonaiagents.memory.mcp_config import MCPConfig

    _patch_configs(monkeypatch, {"filesystem": _FakeMCP(["a"])})
    configs = [
        MCPConfig(name="file-system", command="x"),
        MCPConfig(name="file system", command="y"),
    ]
    with pytest.raises(ValueError, match="collision"):
        load_mcp_tools(configs=configs)


def test_identical_server_name_raises(monkeypatch):
    """Two configs with the exact same name also raise, not silently duplicate."""
    from praisonaiagents.mcp.loader import load_mcp_tools
    from praisonaiagents.memory.mcp_config import MCPConfig

    _patch_configs(monkeypatch, {"filesystem": _FakeMCP(["a"])})
    configs = [
        MCPConfig(name="filesystem", command="x"),
        MCPConfig(name="filesystem", command="y"),
    ]
    with pytest.raises(ValueError, match="collision"):
        load_mcp_tools(configs=configs)


def test_single_loaded_instance_keeps_bare_names(monkeypatch):
    """If only one config yields an instance, it must stay unprefixed (backward compat)."""
    from praisonaiagents.mcp.loader import load_mcp_tools
    from praisonaiagents.memory.mcp_config import MCPConfig

    # 'github' resolves to None (e.g. missing optional dep); only 'filesystem' loads.
    _patch_configs(monkeypatch, {"filesystem": _FakeMCP(["read_file", "search"])})
    configs = [
        MCPConfig(name="filesystem", command="x"),
        MCPConfig(name="github", command="y"),
    ]
    result = load_mcp_tools(configs=configs)
    assert len(result) == 1
    names = {t.__name__ for t in result[0]._tools}
    assert names == {"read_file", "search"}


def test_include_exclude_filters_applied(monkeypatch):
    """include/exclude filters are honoured per server (B3)."""
    from praisonaiagents.mcp.loader import load_mcp_tools
    from praisonaiagents.memory.mcp_config import MCPConfig

    fs = _FakeMCP(["read_file", "write_file", "delete_file"])
    _patch_configs(monkeypatch, {"filesystem": fs})

    config = MCPConfig(name="filesystem", command="x")
    config.disabled_tools = ["delete_file"]
    result = load_mcp_tools(configs=[config])
    names = {t.__name__ for t in result[0]._tools}
    assert names == {"read_file", "write_file"}


def test_safe_env_build():
    """Test safe environment building (B5)."""
    try:
        from praisonaiagents.mcp import MCP
        
        # Create MCP instance to test env building
        # This tests that _build_safe_env method exists
        mcp = MCP("echo test")
        assert hasattr(mcp, '_build_safe_env')
        
        # Test safe env function
        safe_env = mcp._build_safe_env({"CUSTOM_VAR": "test"})
        assert isinstance(safe_env, dict)
        assert "CUSTOM_VAR" in safe_env
        assert safe_env["CUSTOM_VAR"] == "test"
        # Should have safe baseline
        assert "PATH" in safe_env
        assert "HOME" in safe_env
        
    except ImportError as e:
        if "praisonaiagents[mcp]" in str(e):
            pytest.skip("MCP package not installed") 
        else:
            raise
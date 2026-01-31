"""
TDD Tests for Single-File Plugin System.

Tests the WordPress-style plugin format with docstring headers.
"""

import pytest
import tempfile
import os
from pathlib import Path


class TestPluginHeaderParser:
    """Tests for parsing WordPress-style plugin headers from docstrings."""
    
    def test_parse_basic_header(self):
        """Test parsing a basic plugin header with required fields."""
        from praisonaiagents.plugins.parser import parse_plugin_header
        
        content = '''"""
Plugin Name: Weather Tools
Description: Get weather for any city
Version: 1.0.0
"""

from praisonaiagents import tool

@tool
def get_weather(city: str) -> str:
    return f"Weather in {city}"
'''
        
        metadata = parse_plugin_header(content)
        
        assert metadata["name"] == "Weather Tools"
        assert metadata["description"] == "Get weather for any city"
        assert metadata["version"] == "1.0.0"
    
    def test_parse_header_with_all_fields(self):
        """Test parsing header with all optional fields."""
        from praisonaiagents.plugins.parser import parse_plugin_header
        
        content = '''"""
Plugin Name: Advanced Weather
Description: Weather tools with hooks
Version: 2.0.0
Author: John Doe
Hooks: before_tool, after_tool
Dependencies: requests, aiohttp
"""

# Plugin code here
'''
        
        metadata = parse_plugin_header(content)
        
        assert metadata["name"] == "Advanced Weather"
        assert metadata["description"] == "Weather tools with hooks"
        assert metadata["version"] == "2.0.0"
        assert metadata["author"] == "John Doe"
        assert metadata["hooks"] == ["before_tool", "after_tool"]
        assert metadata["dependencies"] == ["requests", "aiohttp"]
    
    def test_parse_header_missing_name_raises(self):
        """Test that missing Plugin Name raises error."""
        from praisonaiagents.plugins.parser import parse_plugin_header, PluginParseError
        
        content = '''"""
Description: No name provided
Version: 1.0.0
"""
'''
        
        with pytest.raises(PluginParseError, match="Plugin Name"):
            parse_plugin_header(content)
    
    def test_parse_header_no_docstring(self):
        """Test parsing file without docstring header."""
        from praisonaiagents.plugins.parser import parse_plugin_header, PluginParseError
        
        content = '''
# Just a comment
from praisonaiagents import tool

@tool
def my_tool():
    pass
'''
        
        with pytest.raises(PluginParseError, match="docstring"):
            parse_plugin_header(content)
    
    def test_parse_header_from_file(self):
        """Test parsing header from actual file."""
        from praisonaiagents.plugins.parser import parse_plugin_header_from_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''"""
Plugin Name: Test Plugin
Description: A test plugin
Version: 1.0.0
"""

def test():
    pass
''')
            f.flush()
            
            try:
                metadata = parse_plugin_header_from_file(f.name)
                assert metadata["name"] == "Test Plugin"
            finally:
                os.unlink(f.name)


class TestPluginDiscovery:
    """Tests for plugin discovery from directories."""
    
    def test_get_default_plugin_dirs(self):
        """Test getting default plugin directories."""
        from praisonaiagents.plugins.discovery import get_default_plugin_dirs
        
        # get_default_plugin_dirs only returns EXISTING directories
        # So we just verify it returns a list (may be empty if dirs don't exist)
        dirs = get_default_plugin_dirs()
        assert isinstance(dirs, list)
    
    def test_discover_plugins_empty_dir(self):
        """Test discovering plugins in empty directory."""
        from praisonaiagents.plugins.discovery import discover_plugins
        
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins = discover_plugins([tmpdir])
            assert plugins == []
    
    def test_discover_plugins_with_valid_plugin(self):
        """Test discovering a valid plugin file."""
        from praisonaiagents.plugins.discovery import discover_plugins
        
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = Path(tmpdir) / "weather.py"
            plugin_path.write_text('''"""
Plugin Name: Weather Plugin
Description: Weather tools
Version: 1.0.0
"""

from praisonaiagents import tool

@tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Sunny in {city}"
''')
            
            plugins = discover_plugins([tmpdir])
            
            assert len(plugins) == 1
            assert plugins[0]["name"] == "Weather Plugin"
            # Use resolve() to handle /private prefix on macOS
            assert Path(plugins[0]["path"]).resolve() == plugin_path.resolve()
    
    def test_discover_plugins_skips_invalid(self):
        """Test that invalid plugins are skipped."""
        from praisonaiagents.plugins.discovery import discover_plugins
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Valid plugin
            valid_path = Path(tmpdir) / "valid.py"
            valid_path.write_text('''"""
Plugin Name: Valid Plugin
Description: A valid plugin
Version: 1.0.0
"""
''')
            
            # Invalid plugin (no header)
            invalid_path = Path(tmpdir) / "invalid.py"
            invalid_path.write_text('''
# No docstring header
def foo():
    pass
''')
            
            plugins = discover_plugins([tmpdir])
            
            assert len(plugins) == 1
            assert plugins[0]["name"] == "Valid Plugin"
    
    def test_discover_plugins_skips_underscore_files(self):
        """Test that files starting with underscore are skipped."""
        from praisonaiagents.plugins.discovery import discover_plugins
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # File starting with underscore
            underscore_path = Path(tmpdir) / "_private.py"
            underscore_path.write_text('''"""
Plugin Name: Private Plugin
Description: Should be skipped
Version: 1.0.0
"""
''')
            
            plugins = discover_plugins([tmpdir])
            assert len(plugins) == 0


class TestPluginLoading:
    """Tests for loading plugins and registering tools/hooks."""
    
    def test_load_plugin_registers_tools(self):
        """Test that loading a plugin registers its tools."""
        from praisonaiagents.plugins.discovery import load_plugin
        
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = Path(tmpdir) / "tools_plugin.py"
            plugin_path.write_text('''"""
Plugin Name: Tools Plugin
Description: Plugin with tools
Version: 1.0.0
"""

from praisonaiagents import tool

@tool
def plugin_test_tool(query: str) -> str:
    """A test tool from plugin."""
    return f"Result: {query}"
''')
            
            # Load plugin
            result = load_plugin(str(plugin_path))
            
            assert result is not None
            assert result["name"] == "Tools Plugin"
            # Tool should be registered
            assert "plugin_test_tool" in result.get("tools", [])
    
    def test_load_plugin_with_hooks(self):
        """Test that loading a plugin registers its hooks."""
        from praisonaiagents.plugins.discovery import load_plugin
        
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = Path(tmpdir) / "hooks_plugin.py"
            plugin_path.write_text('''"""
Plugin Name: Hooks Plugin
Description: Plugin with hooks
Version: 1.0.0
Hooks: before_tool
"""

from praisonaiagents import tool
from praisonaiagents.hooks import add_hook, HookResult

@tool
def hooked_tool(x: str) -> str:
    """A tool."""
    return x

@add_hook("before_tool")
def my_hook(data):
    """A hook."""
    return HookResult.allow()
''')
            
            result = load_plugin(str(plugin_path))
            
            assert result is not None
            assert result["name"] == "Hooks Plugin"
            assert "before_tool" in result.get("hooks", [])


class TestPluginIntegration:
    """Integration tests for plugins with Agent."""
    
    def test_agent_can_use_plugin_tool(self):
        """Test that Agent can use tools from plugins."""
        from praisonaiagents.plugins.discovery import load_plugin
        from praisonaiagents.tools.registry import get_registry
        
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = Path(tmpdir) / "agent_test_plugin.py"
            plugin_path.write_text('''"""
Plugin Name: Agent Test Plugin
Description: Plugin for agent testing
Version: 1.0.0
"""

from praisonaiagents import tool

@tool
def agent_plugin_tool(message: str) -> str:
    """Tool for agent testing."""
    return f"Plugin says: {message}"
''')
            
            # Load plugin
            load_plugin(str(plugin_path))
            
            # Verify tool is in registry
            registry = get_registry()
            tool = registry.get("agent_plugin_tool")
            assert tool is not None
            
            # Verify tool works
            result = tool(message="hello")
            assert "Plugin says: hello" in result


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass."""
    
    def test_plugin_metadata_creation(self):
        """Test creating PluginMetadata."""
        from praisonaiagents.plugins.parser import PluginMetadata
        
        metadata = PluginMetadata(
            name="Test Plugin",
            description="A test",
            version="1.0.0"
        )
        
        assert metadata.name == "Test Plugin"
        assert metadata.description == "A test"
        assert metadata.version == "1.0.0"
        assert metadata.author is None
        assert metadata.hooks == []
        assert metadata.dependencies == []
    
    def test_plugin_metadata_with_all_fields(self):
        """Test PluginMetadata with all fields."""
        from praisonaiagents.plugins.parser import PluginMetadata
        
        metadata = PluginMetadata(
            name="Full Plugin",
            description="Full description",
            version="2.0.0",
            author="Jane Doe",
            hooks=["before_tool", "after_tool"],
            dependencies=["requests"],
            path="/path/to/plugin.py"
        )
        
        assert metadata.author == "Jane Doe"
        assert metadata.hooks == ["before_tool", "after_tool"]
        assert metadata.dependencies == ["requests"]
        assert metadata.path == "/path/to/plugin.py"

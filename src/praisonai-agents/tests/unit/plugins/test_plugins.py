"""
Tests for the Plugins module.

TDD: Tests for dynamic plugin loading and hook execution.
"""

import shutil
import tempfile

from praisonaiagents.plugins.plugin import (
    Plugin,
    PluginHook,
    PluginInfo,
    FunctionPlugin,
)
from praisonaiagents.plugins.manager import (
    PluginManager,
    get_plugin_manager,
)


class TestPluginHook:
    """Tests for PluginHook enum."""
    
    def test_hook_values(self):
        """Test hook enum values."""
        assert PluginHook.ON_INIT.value == "on_init"
        assert PluginHook.BEFORE_TOOL.value == "before_tool"
        assert PluginHook.AFTER_AGENT.value == "after_agent"


class TestPluginInfo:
    """Tests for PluginInfo."""
    
    def test_info_creation(self):
        """Test plugin info creation."""
        info = PluginInfo(
            name="test_plugin",
            version="1.0.0",
            description="Test plugin"
        )
        
        assert info.name == "test_plugin"
        assert info.version == "1.0.0"
    
    def test_info_to_dict(self):
        """Test info serialization."""
        info = PluginInfo(
            name="test",
            hooks=[PluginHook.BEFORE_TOOL]
        )
        
        d = info.to_dict()
        assert d["name"] == "test"
        assert "before_tool" in d["hooks"]


class TestFunctionPlugin:
    """Tests for FunctionPlugin."""
    
    def test_function_plugin_creation(self):
        """Test creating function plugin."""
        plugin = FunctionPlugin(
            name="test",
            version="1.0.0"
        )
        
        assert plugin.info.name == "test"
    
    def test_function_plugin_with_hooks(self):
        """Test function plugin with hook functions."""
        def before_tool(tool_name, args):
            args["modified"] = True
            return args
        
        plugin = FunctionPlugin(
            name="test",
            hooks={PluginHook.BEFORE_TOOL: before_tool}
        )
        
        result = plugin.before_tool("bash", {"cmd": "ls"})
        
        assert result["modified"] is True
        assert result["cmd"] == "ls"
    
    def test_function_plugin_passthrough(self):
        """Test that unregistered hooks pass through."""
        plugin = FunctionPlugin(name="test")
        
        result = plugin.before_tool("bash", {"cmd": "ls"})
        
        assert result == {"cmd": "ls"}


class MockPlugin(Plugin):
    """Mock plugin for testing."""
    
    def __init__(self, name: str = "mock"):
        self._name = name
        self.init_called = False
        self.shutdown_called = False
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name=self._name,
            version="1.0.0",
            hooks=[PluginHook.BEFORE_TOOL, PluginHook.AFTER_TOOL]
        )
    
    def on_init(self, context):
        self.init_called = True
    
    def on_shutdown(self):
        self.shutdown_called = True
    
    def before_tool(self, tool_name, args):
        args["plugin_modified"] = True
        return args


class TestPluginManager:
    """Tests for PluginManager."""
    
    def test_manager_creation(self):
        """Test manager creation."""
        manager = PluginManager()
        
        assert len(manager.list_plugins()) == 0
    
    def test_register_plugin(self):
        """Test registering a plugin."""
        manager = PluginManager()
        plugin = MockPlugin()
        
        result = manager.register(plugin)
        
        assert result is True
        assert len(manager.list_plugins()) == 1
        assert plugin.init_called is True
    
    def test_register_duplicate(self):
        """Test registering duplicate plugin."""
        manager = PluginManager()
        plugin1 = MockPlugin("test")
        plugin2 = MockPlugin("test")
        
        manager.register(plugin1)
        result = manager.register(plugin2)
        
        assert result is False
        assert len(manager.list_plugins()) == 1
    
    def test_unregister_plugin(self):
        """Test unregistering a plugin."""
        manager = PluginManager()
        plugin = MockPlugin()
        
        manager.register(plugin)
        result = manager.unregister("mock")
        
        assert result is True
        assert len(manager.list_plugins()) == 0
        assert plugin.shutdown_called is True
    
    def test_enable_disable(self):
        """Test enabling and disabling plugins."""
        manager = PluginManager()
        plugin = MockPlugin()
        
        manager.register(plugin)
        
        assert manager.is_enabled("mock") is True
        
        manager.disable("mock")
        assert manager.is_enabled("mock") is False
        
        manager.enable("mock")
        assert manager.is_enabled("mock") is True
    
    def test_get_plugin(self):
        """Test getting a plugin by name."""
        manager = PluginManager()
        plugin = MockPlugin()
        
        manager.register(plugin)
        
        retrieved = manager.get_plugin("mock")
        assert retrieved is plugin
    
    def test_execute_hook(self):
        """Test executing a hook."""
        manager = PluginManager()
        plugin = MockPlugin()
        
        manager.register(plugin)
        
        result = manager.execute_hook(
            PluginHook.BEFORE_TOOL,
            "bash",
            {"cmd": "ls"}
        )
        
        assert result["plugin_modified"] is True
    
    def test_execute_hook_disabled(self):
        """Test that disabled plugins don't execute hooks."""
        manager = PluginManager()
        plugin = MockPlugin()
        
        manager.register(plugin)
        manager.disable("mock")
        
        result = manager.execute_hook(
            PluginHook.BEFORE_TOOL,
            "bash",
            {"cmd": "ls"}
        )
        
        # Should return original args since plugin is disabled
        assert "plugin_modified" not in result
    
    def test_get_all_tools(self):
        """Test getting tools from plugins."""
        class ToolPlugin(Plugin):
            @property
            def info(self):
                return PluginInfo(name="tool_plugin")
            
            def get_tools(self):
                return [{"name": "custom_tool"}]
        
        manager = PluginManager()
        manager.register(ToolPlugin())
        
        tools = manager.get_all_tools()
        
        assert len(tools) == 1
        assert tools[0]["name"] == "custom_tool"
    
    def test_shutdown(self):
        """Test shutting down all plugins."""
        manager = PluginManager()
        plugin1 = MockPlugin("plugin1")
        plugin2 = MockPlugin("plugin2")
        
        manager.register(plugin1)
        manager.register(plugin2)
        
        manager.shutdown()
        
        assert len(manager.list_plugins()) == 0
        assert plugin1.shutdown_called is True
        assert plugin2.shutdown_called is True


class TestLoadFromDirectory:
    """Tests for loading plugins from directory."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_load_from_empty_directory(self):
        """Test loading from empty directory."""
        manager = PluginManager()
        
        loaded = manager.load_from_directory(self.temp_dir)
        
        assert loaded == 0
    
    def test_load_from_nonexistent_directory(self):
        """Test loading from non-existent directory."""
        manager = PluginManager()
        
        loaded = manager.load_from_directory("/nonexistent/path")
        
        assert loaded == 0
    
    def test_load_plugin_file(self):
        """Test loading a plugin from file."""
        # Create a plugin file
        plugin_code = '''
from praisonaiagents.plugins.plugin import Plugin, PluginInfo

class TestPlugin(Plugin):
    @property
    def info(self):
        return PluginInfo(name="file_plugin", version="1.0.0")
'''
        
        plugin_path = f"{self.temp_dir}/test_plugin.py"
        with open(plugin_path, "w") as f:
            f.write(plugin_code)
        
        manager = PluginManager()
        loaded = manager.load_from_directory(self.temp_dir)
        
        assert loaded == 1
        assert manager.get_plugin("file_plugin") is not None


class TestGlobalPluginManager:
    """Tests for global plugin manager."""
    
    def test_get_plugin_manager(self):
        """Test getting global manager."""
        manager = get_plugin_manager()
        
        assert isinstance(manager, PluginManager)
    
    def test_singleton_behavior(self):
        """Test that global manager is singleton."""
        manager1 = get_plugin_manager()
        manager2 = get_plugin_manager()
        
        assert manager1 is manager2

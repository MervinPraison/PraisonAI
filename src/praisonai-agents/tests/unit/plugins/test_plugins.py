"""
Tests for the Plugins module.

TDD: Tests for dynamic plugin loading and hook execution.
"""

import shutil
import tempfile
import uuid

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
    
    def test_message_hooks(self):
        """Test message lifecycle hooks (moltbot parity)."""
        assert PluginHook.MESSAGE_RECEIVED.value == "message_received"
        assert PluginHook.MESSAGE_SENDING.value == "message_sending"
        assert PluginHook.MESSAGE_SENT.value == "message_sent"
    
    def test_gateway_hooks(self):
        """Test gateway lifecycle hooks (moltbot parity)."""
        assert PluginHook.GATEWAY_START.value == "gateway_start"
        assert PluginHook.GATEWAY_STOP.value == "gateway_stop"
    
    def test_session_hooks(self):
        """Test session lifecycle hooks."""
        assert PluginHook.SESSION_START.value == "session_start"
        assert PluginHook.SESSION_END.value == "session_end"
    
    def test_compaction_hooks(self):
        """Test compaction hooks (memory management)."""
        assert PluginHook.BEFORE_COMPACTION.value == "before_compaction"
        assert PluginHook.AFTER_COMPACTION.value == "after_compaction"
    
    def test_error_hooks(self):
        """Test error handling hooks."""
        assert PluginHook.ON_ERROR.value == "on_error"
        assert PluginHook.ON_RETRY.value == "on_retry"
    
    def test_tool_result_persist_hook(self):
        """TOOL_RESULT_PERSIST is an alias of the live AFTER_TOOL event.

        AFTER_TOOL already receives the tool result before it is persisted and
        its in-place rewrite of ``tool_output`` is what gets stored, so a
        separate member could only ever be a dead slot that swallowed hooks.
        """
        assert PluginHook.TOOL_RESULT_PERSIST is PluginHook.AFTER_TOOL
    
    def test_message_lifecycle_aliases(self):
        """BEFORE_/AFTER_MESSAGE are the live inbound/outbound events.

        ``Plugin.before_message`` / ``Plugin.after_message`` have always routed
        to MESSAGE_RECEIVED / MESSAGE_SENDING, so the identically named enum
        members must resolve to the same events rather than to dead slots.
        """
        assert PluginHook.BEFORE_MESSAGE is PluginHook.MESSAGE_RECEIVED
        assert PluginHook.AFTER_MESSAGE is PluginHook.MESSAGE_SENDING

    def test_claude_code_parity_hooks(self):
        """Only the parity hook with a real emission site survives.

        SUBAGENT_STOP is emitted by ``tools/subagent_tool.py``.
        USER_PROMPT_SUBMIT / NOTIFICATION / SETUP had no emission site anywhere
        and were removed, so reaching for one now fails loudly instead of
        registering a hook that silently never fires.
        """
        assert PluginHook.SUBAGENT_STOP.value == "subagent_stop"
        for removed in ("USER_PROMPT_SUBMIT", "NOTIFICATION", "SETUP"):
            assert not hasattr(PluginHook, removed)


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

    def test_plugin_tools_wired_into_agent(self):
        """An enabled PluginType.TOOL plugin's tool must reach the agent.

        Regression for the silent-failure where get_tools() output was
        collected by get_all_tools() but never merged into any agent. Crucially
        this does NOT flip the package-wide ``plugins.enable()`` flag: the docs
        state tools work WITHOUT calling enable(), so a merely-registered tool
        plugin must still reach the agent.
        """
        from praisonaiagents.plugins.manager import get_plugin_manager
        from praisonaiagents import Agent

        def random_number() -> int:
            """Returns a random number"""
            return 42

        class BasicToolPlugin(Plugin):
            @property
            def info(self):
                return PluginInfo(name="basic_tools")

            def get_tools(self):
                return [random_number]

        manager = get_plugin_manager()
        manager.register(BasicToolPlugin())

        try:
            # No plugins.enable() call — registration alone must suffice.
            agent = Agent(instructions="test", llm="gpt-4o-mini")
            names = [getattr(t, "__name__", str(t)) for t in agent.tools]
            assert "random_number" in names

            # Collision: agent's own tool wins, no duplicate.
            agent2 = Agent(
                instructions="test", llm="gpt-4o-mini", tools=[random_number]
            )
            names2 = [getattr(t, "__name__", str(t)) for t in agent2.tools]
            assert names2.count("random_number") == 1
        finally:
            manager.unregister("basic_tools")

    def test_plugin_metadata_only_dict_tool_skipped(self):
        """A metadata-only ``{"name": ...}`` descriptor with no executable
        implementation must be skipped rather than advertised as a callable
        tool the agent could never invoke."""
        from praisonaiagents.plugins.manager import get_plugin_manager
        from praisonaiagents import Agent

        class MetaOnlyPlugin(Plugin):
            @property
            def info(self):
                return PluginInfo(name="meta_only")

            def get_tools(self):
                return [{"name": "phantom_tool"}]

        manager = get_plugin_manager()
        manager.register(MetaOnlyPlugin())
        try:
            agent = Agent(instructions="test", llm="gpt-4o-mini")
            assert {"name": "phantom_tool"} not in agent.tools
        finally:
            manager.unregister("meta_only")

    def test_clone_does_not_duplicate_unnamed_hosted_plugin_tool(self):
        """Cloning must not append the same unnamed hosted spec twice."""
        from praisonaiagents.plugins.manager import get_plugin_manager
        from praisonaiagents import Agent

        plugin_name = f"hosted_clone_{uuid.uuid4().hex}"
        hosted_tool = {"type": "web_search"}

        class HostedToolPlugin(Plugin):
            @property
            def info(self):
                return PluginInfo(name=plugin_name)

            def get_tools(self):
                return [hosted_tool]

        manager = get_plugin_manager()
        assert manager.register(HostedToolPlugin())
        try:
            agent = Agent(instructions="test", llm="gpt-4o-mini")
            assert sum(tool is hosted_tool for tool in agent.tools) == 1

            clone = agent.clone_for_channel()
            assert sum(tool is hosted_tool for tool in clone.tools) == 1
        finally:
            manager.unregister(plugin_name)

    def test_shared_plugin_tool_remains_active_until_last_owner_disabled(self):
        """A shared tool is revoked only after every provider is disabled."""
        from praisonaiagents import Agent

        suffix = uuid.uuid4().hex
        first_name = f"shared_owner_first_{suffix}"
        second_name = f"shared_owner_second_{suffix}"
        shared_tool = lambda: "shared"

        def make_plugin(name):
            class SharedToolPlugin(Plugin):
                @property
                def info(self):
                    return PluginInfo(name=name)

                def get_tools(self):
                    return [shared_tool]

            return SharedToolPlugin()

        manager = get_plugin_manager()
        assert manager.register(make_plugin(first_name))
        assert manager.register(make_plugin(second_name))
        try:
            agent = Agent(instructions="test", llm="gpt-4o-mini")
            assert sum(tool is shared_tool for tool in agent.tools) == 1
            owners = agent._plugin_tool_owners[id(shared_tool)]
            assert {entry[0] for entry in owners} == {first_name, second_name}
            assert agent._is_plugin_tool_active(shared_tool) is True

            manager.disable(first_name)
            assert agent._is_plugin_tool_active(shared_tool) is True
            manager.disable(second_name)
            assert agent._is_plugin_tool_active(shared_tool) is False
        finally:
            manager.unregister(first_name)
            manager.unregister(second_name)

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
        # Reimport PluginManager fresh to ensure class identity matches dynamically loaded plugins
        from praisonaiagents.plugins.manager import PluginManager
        
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


class TestEntryPointsDiscovery:
    """Tests for entry_points plugin discovery."""
    
    def test_discover_entry_points_no_plugins(self, monkeypatch):
        """Test entry_points discovery with no plugins installed."""
        import importlib.metadata as metadata

        def mock_entry_points(*args, **kwargs):
            if kwargs.get("group") == "praisonai.plugins":
                return []
            return {"praisonai.plugins": []}

        monkeypatch.setattr(metadata, "entry_points", mock_entry_points)
        manager = PluginManager()
        
        # Should return 0 when no entry_points exist for our group
        loaded = manager.discover_entry_points()
        
        assert loaded == 0
    
    def test_discover_entry_points_import_error(self, monkeypatch):
        """Test graceful handling when importlib.metadata is not available."""
        import sys
        
        # Remove importlib.metadata from sys.modules to simulate import failure
        original_module = sys.modules.pop("importlib.metadata", None)
        
        # Mock the import to raise ImportError
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "importlib.metadata":
                raise ImportError("No module named importlib.metadata")
            return real_import(name, *args, **kwargs)
        
        monkeypatch.setattr(builtins, "__import__", mock_import)
        
        try:
            manager = PluginManager()
            loaded = manager.discover_entry_points()
            
            assert loaded == 0
        finally:
            # Restore the module if it existed
            if original_module is not None:
                sys.modules["importlib.metadata"] = original_module
    
    def test_discover_entry_points_success(self, monkeypatch):
        """Test successful entry_points discovery and plugin loading."""
        import importlib.metadata as metadata
        from praisonaiagents.plugins.plugin import Plugin, PluginInfo
        
        # Create a mock plugin class
        class MockPlugin(Plugin):
            @property
            def info(self) -> PluginInfo:
                return PluginInfo(
                    name="test_plugin",
                    version="1.0.0",
                    description="Test plugin"
                )
        
        # Create a mock entry point
        class MockEntryPoint:
            def __init__(self, name, plugin_class):
                self.name = name
                self._plugin_class = plugin_class
            
            def load(self):
                return self._plugin_class
        
        mock_ep = MockEntryPoint("test_plugin", MockPlugin)
        
        def mock_entry_points(*args, **kwargs):
            if kwargs.get("group") == "praisonai.plugins":
                return [mock_ep]
            return {"praisonai.plugins": [mock_ep]}
        
        monkeypatch.setattr(metadata, "entry_points", mock_entry_points)
        
        manager = PluginManager()
        loaded = manager.discover_entry_points()
        
        assert loaded == 1
        assert "test_plugin" in manager._plugins
        assert manager._plugins["test_plugin"].__class__ == MockPlugin


class TestPluginSuppression:
    """Tests for one-shot plugin suppression (--pure / PRAISONAI_NO_PLUGINS)."""

    def _install_mock_entry_point(self, monkeypatch):
        """Install a single loadable entry point so discovery would find one."""
        import importlib.metadata as metadata
        from praisonaiagents.plugins.plugin import Plugin, PluginInfo

        class MockPlugin(Plugin):
            @property
            def info(self) -> PluginInfo:
                return PluginInfo(
                    name="suppressible_plugin",
                    version="1.0.0",
                    description="Test plugin",
                )

        class MockEntryPoint:
            def __init__(self, name, plugin_class):
                self.name = name
                self._plugin_class = plugin_class

            def load(self):
                return self._plugin_class

        mock_ep = MockEntryPoint("suppressible_plugin", MockPlugin)

        def mock_entry_points(*args, **kwargs):
            if kwargs.get("group") == "praisonai.plugins":
                return [mock_ep]
            return {"praisonai.plugins": [mock_ep]}

        monkeypatch.setattr(metadata, "entry_points", mock_entry_points)

    def test_env_var_suppresses_discovery(self, monkeypatch):
        """PRAISONAI_NO_PLUGINS=1 short-circuits entry-point discovery."""
        self._install_mock_entry_point(monkeypatch)
        monkeypatch.setenv("PRAISONAI_NO_PLUGINS", "1")

        manager = PluginManager()
        assert manager.is_discovery_disabled() is True
        assert manager.discover_entry_points() == 0
        assert manager._plugins == {}

    def test_constructor_param_suppresses_discovery(self, monkeypatch):
        """PluginManager(disabled=True) forces suppression (Python parity)."""
        self._install_mock_entry_point(monkeypatch)
        monkeypatch.delenv("PRAISONAI_NO_PLUGINS", raising=False)

        manager = PluginManager(disabled=True)
        assert manager.is_discovery_disabled() is True
        assert manager.discover_entry_points() == 0
        assert manager._plugins == {}

    def test_constructor_param_overrides_env(self, monkeypatch):
        """An explicit disabled=False wins over the env var."""
        self._install_mock_entry_point(monkeypatch)
        monkeypatch.setenv("PRAISONAI_NO_PLUGINS", "1")

        manager = PluginManager(disabled=False)
        assert manager.is_discovery_disabled() is False
        assert manager.discover_entry_points() == 1

    def test_not_disabled_by_default(self, monkeypatch):
        """Absent env/param, discovery is not suppressed (backward compatible)."""
        monkeypatch.delenv("PRAISONAI_NO_PLUGINS", raising=False)
        manager = PluginManager()
        assert manager.is_discovery_disabled() is False

    def test_auto_discover_suppressed_leaves_state(self, monkeypatch):
        """auto_discover_plugins() is a no-op under suppression."""
        monkeypatch.setenv("PRAISONAI_NO_PLUGINS", "true")
        manager = PluginManager()
        assert manager.auto_discover_plugins() == 0
        assert manager._plugins == {}

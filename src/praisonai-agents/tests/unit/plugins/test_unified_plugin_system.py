"""
Tests for Unified Plugin System.

TDD tests for:
1. Path centralization (using paths.py instead of hardcoded paths)
2. Hook unification (PluginHook = HookEvent)
3. PluginType enum
4. Async hook execution
5. Thread safety
"""

import pytest
import threading
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestPathCentralization:
    """Tests for centralized path usage in discovery modules."""
    
    def test_plugins_discovery_uses_paths_module(self):
        """plugins/discovery.py should use paths.get_plugins_dir()."""
        from praisonaiagents.plugins.discovery import get_default_plugin_dirs
        from praisonaiagents.paths import get_plugins_dir, get_project_data_dir
        
        # The function should use paths.py functions internally
        # We verify by checking the returned paths match the expected format
        dirs = get_default_plugin_dirs()
        
        # Should return paths that end with 'plugins'
        for d in dirs:
            assert d.name == "plugins", f"Expected 'plugins' dir, got {d}"
    
    def test_skills_discovery_uses_paths_module(self):
        """skills/discovery.py should use paths.get_skills_dir()."""
        from praisonaiagents.skills.discovery import get_default_skill_dirs
        from praisonaiagents.paths import get_skills_dir
        
        dirs = get_default_skill_dirs()
        
        # Should return paths that end with 'skills'
        for d in dirs:
            assert d.name == "skills", f"Expected 'skills' dir, got {d}"
    
    def test_paths_module_returns_praisonai_dir(self):
        """paths.py should return ~/.praisonai/ as default."""
        from praisonaiagents.paths import get_data_dir, DEFAULT_DIR_NAME
        
        assert DEFAULT_DIR_NAME == ".praisonai"
        
        # Without env override, should use .praisonai
        data_dir = get_data_dir()
        assert data_dir.name in [".praisonai", ".praison"]  # .praison for legacy


class TestHookUnification:
    """Tests for PluginHook = HookEvent unification."""
    
    def test_plugin_hook_is_hook_event_alias(self):
        """PluginHook should be an alias for HookEvent."""
        from praisonaiagents.plugins import PluginHook
        from praisonaiagents.hooks import HookEvent
        
        # They should be the same enum
        assert PluginHook is HookEvent, "PluginHook should be HookEvent alias"
    
    def test_hook_event_has_plugin_lifecycle_events(self):
        """HookEvent should have ON_INIT, ON_SHUTDOWN, etc."""
        from praisonaiagents.hooks import HookEvent
        
        # Plugin lifecycle events
        assert hasattr(HookEvent, 'ON_INIT'), "Missing ON_INIT"
        assert hasattr(HookEvent, 'ON_SHUTDOWN'), "Missing ON_SHUTDOWN"
        
        # Permission/config events
        assert hasattr(HookEvent, 'ON_PERMISSION_ASK'), "Missing ON_PERMISSION_ASK"
        assert hasattr(HookEvent, 'ON_CONFIG'), "Missing ON_CONFIG"
        assert hasattr(HookEvent, 'ON_AUTH'), "Missing ON_AUTH"
        
        # Message events
        assert hasattr(HookEvent, 'BEFORE_MESSAGE'), "Missing BEFORE_MESSAGE"
        assert hasattr(HookEvent, 'AFTER_MESSAGE'), "Missing AFTER_MESSAGE"
    
    def test_hook_event_values_match_plugin_hook_values(self):
        """HookEvent values should match expected plugin hook values."""
        from praisonaiagents.hooks import HookEvent
        
        assert HookEvent.ON_INIT.value == "on_init"
        assert HookEvent.ON_SHUTDOWN.value == "on_shutdown"
        assert HookEvent.BEFORE_TOOL.value == "before_tool"
        assert HookEvent.AFTER_TOOL.value == "after_tool"


class TestPluginType:
    """Tests for PluginType enum."""
    
    def test_plugin_type_enum_exists(self):
        """PluginType enum should exist."""
        from praisonaiagents.plugins import PluginType
        
        assert PluginType is not None
    
    def test_plugin_type_has_expected_values(self):
        """PluginType should have TOOL, HOOK, SKILL, POLICY."""
        from praisonaiagents.plugins import PluginType
        
        assert hasattr(PluginType, 'TOOL')
        assert hasattr(PluginType, 'HOOK')
        assert hasattr(PluginType, 'SKILL')
        assert hasattr(PluginType, 'POLICY')
        
        assert PluginType.TOOL.value == "tool"
        assert PluginType.HOOK.value == "hook"
        assert PluginType.SKILL.value == "skill"
        assert PluginType.POLICY.value == "policy"


class TestAsyncHookExecution:
    """Tests for async hook execution."""
    
    @pytest.mark.asyncio
    async def test_async_execute_hook_exists(self):
        """PluginManager should have async_execute_hook method."""
        from praisonaiagents.plugins import PluginManager
        
        manager = PluginManager()
        assert hasattr(manager, 'async_execute_hook'), "Missing async_execute_hook"
        assert asyncio.iscoroutinefunction(manager.async_execute_hook)
    
    @pytest.mark.asyncio
    async def test_async_execute_hook_works(self):
        """async_execute_hook should execute hooks asynchronously."""
        from praisonaiagents.plugins import PluginManager, Plugin, PluginInfo
        from praisonaiagents.hooks import HookEvent
        
        class AsyncTestPlugin(Plugin):
            @property
            def info(self):
                return PluginInfo(
                    name="async_test",
                    hooks=[HookEvent.BEFORE_TOOL]
                )
            
            def before_tool(self, tool_name, args):
                args["async_modified"] = True
                return args
        
        manager = PluginManager()
        manager.register(AsyncTestPlugin())
        
        result = await manager.async_execute_hook(
            HookEvent.BEFORE_TOOL,
            "test_tool",
            {"original": True}
        )
        
        assert result.get("async_modified") is True


class TestThreadSafety:
    """Tests for thread safety in PluginManager."""
    
    def test_plugin_manager_has_lock(self):
        """PluginManager should have a threading lock."""
        from praisonaiagents.plugins import PluginManager
        
        manager = PluginManager()
        assert hasattr(manager, '_lock'), "Missing _lock attribute"
        assert isinstance(manager._lock, type(threading.RLock()))
    
    def test_concurrent_registration_is_safe(self):
        """Concurrent plugin registration should be thread-safe."""
        from praisonaiagents.plugins import PluginManager, Plugin, PluginInfo
        from praisonaiagents.hooks import HookEvent
        
        class TestPlugin(Plugin):
            def __init__(self, name):
                self._name = name
            
            @property
            def info(self):
                return PluginInfo(name=self._name, hooks=[])
        
        manager = PluginManager()
        errors = []
        
        def register_plugin(i):
            try:
                manager.register(TestPlugin(f"plugin_{i}"))
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=register_plugin, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(manager.list_plugins()) == 10


class TestBackwardCompatibility:
    """Tests for backward compatibility."""
    
    def test_legacy_plugin_hook_import_works(self):
        """Importing PluginHook from plugins should still work."""
        from praisonaiagents.plugins import PluginHook
        
        # Should be able to use PluginHook values
        assert PluginHook.BEFORE_TOOL.value == "before_tool"
    
    def test_legacy_paths_fallback(self):
        """Legacy ~/.praison/ path should work with warning."""
        from praisonaiagents.paths import get_data_dir, LEGACY_DIR_NAME
        
        assert LEGACY_DIR_NAME == ".praison"
    
    def test_plugin_info_still_works(self):
        """PluginInfo should still work with PluginHook."""
        from praisonaiagents.plugins import PluginInfo, PluginHook
        
        info = PluginInfo(
            name="test",
            hooks=[PluginHook.BEFORE_TOOL, PluginHook.AFTER_TOOL]
        )
        
        assert len(info.hooks) == 2


class TestExports:
    """Tests for proper exports in __init__.py files."""
    
    def test_plugins_exports_plugin_type(self):
        """plugins/__init__.py should export PluginType."""
        from praisonaiagents.plugins import PluginType
        assert PluginType is not None
    
    def test_plugins_exports_plugin_hook(self):
        """plugins/__init__.py should export PluginHook."""
        from praisonaiagents.plugins import PluginHook
        assert PluginHook is not None
    
    def test_hooks_exports_all_events(self):
        """hooks/__init__.py should export HookEvent with all values."""
        from praisonaiagents.hooks import HookEvent
        
        # Core events
        assert hasattr(HookEvent, 'BEFORE_TOOL')
        assert hasattr(HookEvent, 'AFTER_TOOL')
        assert hasattr(HookEvent, 'BEFORE_AGENT')
        assert hasattr(HookEvent, 'AFTER_AGENT')
        
        # Plugin lifecycle events (new)
        assert hasattr(HookEvent, 'ON_INIT')
        assert hasattr(HookEvent, 'ON_SHUTDOWN')

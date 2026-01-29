"""Tests for built-in plugins."""

import logging


class TestLoggingPlugin:
    """Tests for LoggingPlugin."""
    
    def test_logging_plugin_info(self):
        """Test LoggingPlugin info property."""
        from praisonaiagents.plugins.builtin import LoggingPlugin
        
        plugin = LoggingPlugin()
        info = plugin.info
        
        assert info.name == "logging"
        assert info.version == "1.0.0"
        assert len(info.hooks) > 0
    
    def test_logging_plugin_before_tool(self):
        """Test LoggingPlugin before_tool hook."""
        from praisonaiagents.plugins.builtin import LoggingPlugin
        
        plugin = LoggingPlugin(log_tools=True)
        args = {"query": "test"}
        
        result = plugin.before_tool("test_tool", args)
        
        assert result == args
    
    def test_logging_plugin_after_tool(self):
        """Test LoggingPlugin after_tool hook."""
        from praisonaiagents.plugins.builtin import LoggingPlugin
        
        plugin = LoggingPlugin(log_tools=True)
        
        result = plugin.after_tool("test_tool", "result_value")
        
        assert result == "result_value"
    
    def test_logging_plugin_before_agent(self):
        """Test LoggingPlugin before_agent hook."""
        from praisonaiagents.plugins.builtin import LoggingPlugin
        
        plugin = LoggingPlugin(log_agents=True)
        
        result = plugin.before_agent("Hello", {})
        
        assert result == "Hello"
    
    def test_logging_plugin_after_agent(self):
        """Test LoggingPlugin after_agent hook."""
        from praisonaiagents.plugins.builtin import LoggingPlugin
        
        plugin = LoggingPlugin(log_agents=True)
        
        result = plugin.after_agent("Response", {})
        
        assert result == "Response"
    
    def test_logging_plugin_custom_level(self):
        """Test LoggingPlugin with custom log level."""
        from praisonaiagents.plugins.builtin import LoggingPlugin
        
        plugin = LoggingPlugin(level=logging.DEBUG)
        
        assert plugin._level == logging.DEBUG
    
    def test_logging_plugin_selective_hooks(self):
        """Test LoggingPlugin with selective hook configuration."""
        from praisonaiagents.plugins.builtin import LoggingPlugin
        from praisonaiagents.plugins import PluginHook
        
        plugin = LoggingPlugin(log_tools=True, log_agents=False, log_llm=False)
        
        assert PluginHook.BEFORE_TOOL in plugin.info.hooks
        assert PluginHook.AFTER_TOOL in plugin.info.hooks
        assert PluginHook.BEFORE_AGENT not in plugin.info.hooks
        assert PluginHook.BEFORE_LLM not in plugin.info.hooks


class TestMetricsPlugin:
    """Tests for MetricsPlugin."""
    
    def test_metrics_plugin_info(self):
        """Test MetricsPlugin info property."""
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        plugin = MetricsPlugin()
        info = plugin.info
        
        assert info.name == "metrics"
        assert info.version == "1.0.0"
        assert len(info.hooks) == 6
    
    def test_metrics_plugin_tool_tracking(self):
        """Test MetricsPlugin tool call tracking."""
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        plugin = MetricsPlugin()
        
        plugin.before_tool("test_tool", {"arg": "value"})
        plugin.after_tool("test_tool", "result")
        
        metrics = plugin.get_metrics()
        
        assert "test_tool" in metrics["tools"]
        assert metrics["tools"]["test_tool"]["call_count"] == 1
    
    def test_metrics_plugin_agent_tracking(self):
        """Test MetricsPlugin agent call tracking."""
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        plugin = MetricsPlugin()
        
        plugin.before_agent("Hello world", {})
        plugin.after_agent("Response text", {})
        
        metrics = plugin.get_metrics()
        
        assert metrics["agent"]["prompt_count"] == 1
        assert metrics["agent"]["response_count"] == 1
        assert metrics["agent"]["total_prompt_chars"] == 11
        assert metrics["agent"]["total_response_chars"] == 13
    
    def test_metrics_plugin_llm_tracking(self):
        """Test MetricsPlugin LLM call tracking."""
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        plugin = MetricsPlugin()
        
        messages = [{"role": "user", "content": "Hi"}]
        plugin.before_llm(messages, {})
        plugin.after_llm("Hello!", {"prompt_tokens": 10, "completion_tokens": 5})
        
        metrics = plugin.get_metrics()
        
        assert metrics["llm"]["call_count"] == 1
        assert metrics["llm"]["total_input_tokens"] == 10
        assert metrics["llm"]["total_output_tokens"] == 5
    
    def test_metrics_plugin_reset(self):
        """Test MetricsPlugin reset functionality."""
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        plugin = MetricsPlugin()
        
        plugin.before_tool("test_tool", {})
        plugin.after_tool("test_tool", "result")
        
        plugin.reset_metrics()
        
        metrics = plugin.get_metrics()
        
        assert len(metrics["tools"]) == 0
        assert metrics["agent"]["prompt_count"] == 0
    
    def test_metrics_plugin_multiple_tool_calls(self):
        """Test MetricsPlugin with multiple tool calls."""
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        plugin = MetricsPlugin()
        
        for _ in range(3):
            plugin.before_tool("tool_a", {})
            plugin.after_tool("tool_a", "result")
        
        plugin.before_tool("tool_b", {})
        plugin.after_tool("tool_b", "result")
        
        metrics = plugin.get_metrics()
        
        assert metrics["tools"]["tool_a"]["call_count"] == 3
        assert metrics["tools"]["tool_b"]["call_count"] == 1
    
    def test_metrics_plugin_uptime(self):
        """Test MetricsPlugin uptime tracking."""
        from praisonaiagents.plugins.builtin import MetricsPlugin
        import time
        
        plugin = MetricsPlugin()
        time.sleep(0.1)
        
        metrics = plugin.get_metrics()
        
        assert metrics["uptime_seconds"] >= 0.1


class TestPluginSDK:
    """Tests for Plugin SDK."""
    
    def test_sdk_exports(self):
        """Test that SDK exports are available."""
        from praisonaiagents.plugins.sdk import Plugin, PluginHook, PluginInfo, FunctionPlugin
        
        assert Plugin is not None
        assert PluginHook is not None
        assert PluginInfo is not None
        assert FunctionPlugin is not None
    
    def test_function_plugin(self):
        """Test FunctionPlugin creation."""
        from praisonaiagents.plugins.sdk import FunctionPlugin, PluginHook
        
        def my_before_tool(tool_name, args):
            args["modified"] = True
            return args
        
        plugin = FunctionPlugin(
            name="test_plugin",
            hooks={PluginHook.BEFORE_TOOL: my_before_tool},
            version="1.0.0",
        )
        
        assert plugin.info.name == "test_plugin"
        assert plugin.info.version == "1.0.0"
        
        result = plugin.before_tool("test", {"key": "value"})
        assert result["modified"] is True


class TestPluginManagerIntegration:
    """Integration tests for PluginManager with built-in plugins."""
    
    def test_register_logging_plugin(self):
        """Test registering LoggingPlugin with PluginManager."""
        from praisonaiagents.plugins import PluginManager
        from praisonaiagents.plugins.builtin import LoggingPlugin
        
        manager = PluginManager()
        plugin = LoggingPlugin()
        
        result = manager.register(plugin)
        
        assert result is True
        assert len(manager.list_plugins()) == 1
    
    def test_register_metrics_plugin(self):
        """Test registering MetricsPlugin with PluginManager."""
        from praisonaiagents.plugins import PluginManager
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        manager = PluginManager()
        plugin = MetricsPlugin()
        
        result = manager.register(plugin)
        
        assert result is True
        assert len(manager.list_plugins()) == 1
    
    def test_execute_hook_with_builtin_plugins(self):
        """Test executing hooks with built-in plugins."""
        from praisonaiagents.plugins import PluginManager, PluginHook
        from praisonaiagents.plugins.builtin import MetricsPlugin
        
        manager = PluginManager()
        metrics_plugin = MetricsPlugin()
        manager.register(metrics_plugin)
        
        manager.execute_hook(PluginHook.BEFORE_TOOL, "test_tool", {"arg": "value"})
        manager.execute_hook(PluginHook.AFTER_TOOL, "test_tool", "result")
        
        metrics = metrics_plugin.get_metrics()
        
        assert metrics["tools"]["test_tool"]["call_count"] == 1

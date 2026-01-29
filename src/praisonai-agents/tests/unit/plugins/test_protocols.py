"""Tests for plugin protocols."""

from typing import Any, Dict, List


class TestPluginProtocol:
    """Tests for PluginProtocol."""
    
    def test_protocol_is_runtime_checkable(self):
        """Test that PluginProtocol is runtime checkable."""
        from praisonaiagents.plugins.protocols import PluginProtocol
        
        class ValidPlugin:
            @property
            def name(self) -> str:
                return "test"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def on_init(self, context: Dict[str, Any]) -> None:
                pass
            
            def on_shutdown(self) -> None:
                pass
        
        plugin = ValidPlugin()
        assert isinstance(plugin, PluginProtocol)
    
    def test_protocol_rejects_invalid_implementation(self):
        """Test that incomplete implementations are rejected."""
        from praisonaiagents.plugins.protocols import PluginProtocol
        
        class InvalidPlugin:
            pass
        
        plugin = InvalidPlugin()
        assert not isinstance(plugin, PluginProtocol)


class TestToolPluginProtocol:
    """Tests for ToolPluginProtocol."""
    
    def test_tool_plugin_protocol(self):
        """Test ToolPluginProtocol implementation."""
        from praisonaiagents.plugins.protocols import ToolPluginProtocol
        
        class ToolPlugin:
            @property
            def name(self) -> str:
                return "tool_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def on_init(self, context: Dict[str, Any]) -> None:
                pass
            
            def on_shutdown(self) -> None:
                pass
            
            def get_tools(self) -> List[Dict[str, Any]]:
                return [{"name": "test_tool"}]
        
        plugin = ToolPlugin()
        assert isinstance(plugin, ToolPluginProtocol)
        assert plugin.get_tools() == [{"name": "test_tool"}]


class TestHookPluginProtocol:
    """Tests for HookPluginProtocol."""
    
    def test_hook_plugin_protocol(self):
        """Test HookPluginProtocol implementation."""
        from praisonaiagents.plugins.protocols import HookPluginProtocol
        
        class HookPlugin:
            @property
            def name(self) -> str:
                return "hook_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def on_init(self, context: Dict[str, Any]) -> None:
                pass
            
            def on_shutdown(self) -> None:
                pass
            
            def before_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
                args["modified"] = True
                return args
            
            def after_tool(self, tool_name: str, result: Any) -> Any:
                return f"modified: {result}"
        
        plugin = HookPlugin()
        assert isinstance(plugin, HookPluginProtocol)
        
        result = plugin.before_tool("test", {"key": "value"})
        assert result["modified"] is True
        
        result = plugin.after_tool("test", "original")
        assert result == "modified: original"


class TestAgentPluginProtocol:
    """Tests for AgentPluginProtocol."""
    
    def test_agent_plugin_protocol(self):
        """Test AgentPluginProtocol implementation."""
        from praisonaiagents.plugins.protocols import AgentPluginProtocol
        
        class AgentPlugin:
            @property
            def name(self) -> str:
                return "agent_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def on_init(self, context: Dict[str, Any]) -> None:
                pass
            
            def on_shutdown(self) -> None:
                pass
            
            def before_agent(self, prompt: str, context: Dict[str, Any]) -> str:
                return f"[PREFIX] {prompt}"
            
            def after_agent(self, response: str, context: Dict[str, Any]) -> str:
                return f"{response} [SUFFIX]"
        
        plugin = AgentPlugin()
        assert isinstance(plugin, AgentPluginProtocol)
        
        result = plugin.before_agent("Hello", {})
        assert result == "[PREFIX] Hello"
        
        result = plugin.after_agent("World", {})
        assert result == "World [SUFFIX]"


class TestLLMPluginProtocol:
    """Tests for LLMPluginProtocol."""
    
    def test_llm_plugin_protocol(self):
        """Test LLMPluginProtocol implementation."""
        from praisonaiagents.plugins.protocols import LLMPluginProtocol
        
        class LLMPlugin:
            @property
            def name(self) -> str:
                return "llm_plugin"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            def on_init(self, context: Dict[str, Any]) -> None:
                pass
            
            def on_shutdown(self) -> None:
                pass
            
            def before_llm(self, messages: List[Dict], params: Dict[str, Any]) -> tuple:
                messages.append({"role": "system", "content": "Be helpful"})
                return messages, params
            
            def after_llm(self, response: str, usage: Dict[str, Any]) -> str:
                return response.upper()
        
        plugin = LLMPlugin()
        assert isinstance(plugin, LLMPluginProtocol)
        
        messages = [{"role": "user", "content": "Hi"}]
        result_messages, result_params = plugin.before_llm(messages, {})
        assert len(result_messages) == 2
        
        result = plugin.after_llm("hello", {})
        assert result == "HELLO"

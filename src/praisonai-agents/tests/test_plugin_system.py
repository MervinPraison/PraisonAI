"""Tests for the plugin system (BaseTool, @tool decorator, ToolRegistry).

Run with: pytest tests/test_plugin_system.py -v
"""

import pytest
from typing import List


class TestBaseTool:
    """Tests for BaseTool abstract class."""
    
    def test_import_from_main_package(self):
        """BaseTool should be importable from praisonaiagents."""
        from praisonaiagents import BaseTool
        assert BaseTool is not None
    
    def test_subclass_with_required_attributes(self):
        """Subclass with name, description, and run() should work."""
        from praisonaiagents import BaseTool
        
        class MyTool(BaseTool):
            name = "my_tool"
            description = "A test tool"
            
            def run(self, query: str) -> str:
                return f"Result: {query}"
        
        tool = MyTool()
        assert tool.name == "my_tool"
        assert tool.description == "A test tool"
        assert tool.run(query="test") == "Result: test"
    
    def test_auto_name_from_class(self):
        """Name should default to lowercase class name without 'tool'."""
        from praisonaiagents import BaseTool
        
        class WeatherTool(BaseTool):
            description = "Get weather"
            
            def run(self) -> str:
                return "sunny"
        
        tool = WeatherTool()
        assert tool.name == "weather"
    
    def test_auto_description_from_docstring(self):
        """Description should default to class docstring."""
        from praisonaiagents import BaseTool
        
        class MyTool(BaseTool):
            """This tool does amazing things."""
            name = "my_tool"
            
            def run(self) -> str:
                return "done"
        
        tool = MyTool()
        assert "amazing things" in tool.description
    
    def test_auto_generate_parameters_schema(self):
        """Parameters schema should be auto-generated from run() signature."""
        from praisonaiagents import BaseTool
        
        class SearchTool(BaseTool):
            name = "search"
            description = "Search for things"
            
            def run(self, query: str, max_results: int = 5) -> List[str]:
                return []
        
        tool = SearchTool()
        schema = tool.parameters
        
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "max_results" in schema["properties"]
        assert "query" in schema["required"]
        assert "max_results" not in schema["required"]  # Has default
    
    def test_callable_like_function(self):
        """Tool should be callable directly."""
        from praisonaiagents import BaseTool
        
        class AddTool(BaseTool):
            name = "add"
            description = "Add numbers"
            
            def run(self, a: int, b: int) -> int:
                return a + b
        
        tool = AddTool()
        result = tool(a=2, b=3)
        assert result == 5
    
    def test_safe_run_success(self):
        """safe_run() should return ToolResult on success."""
        from praisonaiagents import BaseTool
        
        class OkTool(BaseTool):
            name = "ok"
            description = "Always works"
            
            def run(self) -> str:
                return "ok"
        
        tool = OkTool()
        result = tool.safe_run()
        
        assert result.success is True
        assert result.output == "ok"
        assert result.error is None
    
    def test_safe_run_failure(self):
        """safe_run() should catch exceptions and return ToolResult."""
        from praisonaiagents import BaseTool
        
        class FailTool(BaseTool):
            name = "fail"
            description = "Always fails"
            
            def run(self) -> str:
                raise ValueError("Something went wrong")
        
        tool = FailTool()
        result = tool.safe_run()
        
        assert result.success is False
        assert result.output is None
        assert "Something went wrong" in result.error
    
    def test_get_schema_openai_format(self):
        """get_schema() should return OpenAI-compatible function schema."""
        from praisonaiagents import BaseTool
        
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Does something"
            
            def run(self, x: str) -> str:
                return x
        
        tool = MyTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "my_tool"
        assert schema["function"]["description"] == "Does something"
        assert "parameters" in schema["function"]


class TestToolDecorator:
    """Tests for @tool decorator."""
    
    def test_import_from_main_package(self):
        """tool decorator should be importable from praisonaiagents."""
        from praisonaiagents import tool
        assert tool is not None
    
    def test_decorator_without_args(self):
        """@tool without arguments should work."""
        from praisonaiagents import tool
        
        @tool
        def my_search(query: str) -> List[str]:
            """Search for things."""
            return [query]
        
        assert my_search.name == "my_search"
        assert "Search for things" in my_search.description
        result = my_search(query="test")
        assert result == ["test"]
    
    def test_decorator_with_args(self):
        """@tool(name=..., description=...) should work."""
        from praisonaiagents import tool
        
        @tool(name="custom_search", description="Custom description")
        def search(query: str) -> List[str]:
            return [query]
        
        assert search.name == "custom_search"
        assert search.description == "Custom description"
    
    def test_decorated_function_is_basetool(self):
        """Decorated function should be a BaseTool instance."""
        from praisonaiagents import tool, BaseTool
        
        @tool
        def my_func(x: str) -> str:
            return x
        
        assert isinstance(my_func, BaseTool)
    
    def test_decorated_function_has_schema(self):
        """Decorated function should have auto-generated schema."""
        from praisonaiagents import tool
        
        @tool
        def calculate(a: int, b: int, operation: str = "add") -> int:
            """Perform calculation."""
            return a + b
        
        schema = calculate.get_schema()
        params = schema["function"]["parameters"]
        
        assert "a" in params["properties"]
        assert "b" in params["properties"]
        assert "operation" in params["properties"]
        assert "a" in params["required"]
        assert "operation" not in params["required"]
    
    def test_decorated_function_callable_both_ways(self):
        """Decorated function should work with positional and keyword args."""
        from praisonaiagents import tool
        
        @tool
        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"
        
        # Keyword args (BaseTool style)
        assert greet(name="World") == "Hello, World!"
        
        # Positional args (function style)
        assert greet("World", "Hi") == "Hi, World!"


class TestToolRegistry:
    """Tests for ToolRegistry."""
    
    def test_import_from_main_package(self):
        """Registry functions should be importable from praisonaiagents."""
        from praisonaiagents import get_registry, register_tool, get_tool, ToolRegistry
        assert get_registry is not None
        assert register_tool is not None
        assert get_tool is not None
        assert ToolRegistry is not None
    
    def test_register_and_get_basetool(self):
        """Should register and retrieve BaseTool instances."""
        from praisonaiagents import BaseTool, ToolRegistry
        
        class MyTool(BaseTool):
            name = "registry_test_tool"
            description = "Test"
            
            def run(self) -> str:
                return "ok"
        
        registry = ToolRegistry()
        tool = MyTool()
        registry.register(tool)
        
        retrieved = registry.get("registry_test_tool")
        assert retrieved is tool
    
    def test_register_and_get_function(self):
        """Should register and retrieve plain functions."""
        from praisonaiagents import ToolRegistry
        
        def my_func(x: str) -> str:
            return x
        
        registry = ToolRegistry()
        registry.register(my_func)
        
        retrieved = registry.get("my_func")
        assert retrieved is my_func
    
    def test_register_with_custom_name(self):
        """Should allow custom name override."""
        from praisonaiagents import ToolRegistry
        
        def original_name() -> str:
            return "ok"
        
        registry = ToolRegistry()
        registry.register(original_name, name="custom_name")
        
        assert registry.get("custom_name") is original_name
        assert registry.get("original_name") is None
    
    def test_list_tools(self):
        """Should list all registered tool names."""
        from praisonaiagents import ToolRegistry, BaseTool
        
        class Tool1(BaseTool):
            name = "tool1"
            description = "First"
            def run(self): return 1
        
        class Tool2(BaseTool):
            name = "tool2"
            description = "Second"
            def run(self): return 2
        
        registry = ToolRegistry()
        registry.register(Tool1())
        registry.register(Tool2())
        
        names = registry.list_tools()
        assert "tool1" in names
        assert "tool2" in names
    
    def test_unregister(self):
        """Should remove tools from registry."""
        from praisonaiagents import ToolRegistry
        
        def temp_func() -> str:
            return "temp"
        
        registry = ToolRegistry()
        registry.register(temp_func)
        assert "temp_func" in registry
        
        result = registry.unregister("temp_func")
        assert result is True
        assert "temp_func" not in registry
    
    def test_no_duplicate_registration(self):
        """Should not overwrite existing tools by default."""
        from praisonaiagents import ToolRegistry
        
        def func_v1() -> str:
            return "v1"
        
        def func_v2() -> str:
            return "v2"
        
        registry = ToolRegistry()
        registry.register(func_v1, name="my_func")
        registry.register(func_v2, name="my_func")  # Should be ignored
        
        retrieved = registry.get("my_func")
        assert retrieved() == "v1"
    
    def test_overwrite_registration(self):
        """Should overwrite when overwrite=True."""
        from praisonaiagents import ToolRegistry
        
        def func_v1() -> str:
            return "v1"
        
        def func_v2() -> str:
            return "v2"
        
        registry = ToolRegistry()
        registry.register(func_v1, name="my_func")
        registry.register(func_v2, name="my_func", overwrite=True)
        
        retrieved = registry.get("my_func")
        assert retrieved() == "v2"
    
    def test_global_registry_singleton(self):
        """get_registry() should return same instance."""
        from praisonaiagents import get_registry
        
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2
    
    def test_clear_registry(self):
        """clear() should remove all tools."""
        from praisonaiagents import ToolRegistry
        
        registry = ToolRegistry()
        registry.register(lambda: "a", name="a")
        registry.register(lambda: "b", name="b")
        assert len(registry) == 2
        
        registry.clear()
        assert len(registry) == 0


class TestToolResult:
    """Tests for ToolResult wrapper."""
    
    def test_import_from_main_package(self):
        """ToolResult should be importable from praisonaiagents."""
        from praisonaiagents import ToolResult
        assert ToolResult is not None
    
    def test_success_result(self):
        """Should create success result."""
        from praisonaiagents import ToolResult
        
        result = ToolResult(output="data", success=True)
        assert result.success is True
        assert result.output == "data"
        assert result.error is None
    
    def test_error_result(self):
        """Should create error result."""
        from praisonaiagents import ToolResult
        
        result = ToolResult(output=None, success=False, error="Failed")
        assert result.success is False
        assert result.error == "Failed"
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        from praisonaiagents import ToolResult
        
        result = ToolResult(output="data", success=True, metadata={"key": "value"})
        d = result.to_dict()
        
        assert d["output"] == "data"
        assert d["success"] is True
        assert d["metadata"]["key"] == "value"
    
    def test_str_representation(self):
        """String should show output or error."""
        from praisonaiagents import ToolResult
        
        success = ToolResult(output="hello", success=True)
        assert str(success) == "hello"
        
        failure = ToolResult(output=None, success=False, error="oops")
        assert "oops" in str(failure)


class TestFunctionTool:
    """Tests for FunctionTool class."""
    
    def test_import_from_main_package(self):
        """FunctionTool should be importable from praisonaiagents."""
        from praisonaiagents import FunctionTool
        assert FunctionTool is not None
    
    def test_wraps_function(self):
        """Should wrap a function and preserve its behavior."""
        from praisonaiagents import FunctionTool
        
        def original(x: int, y: int) -> int:
            """Add two numbers."""
            return x + y
        
        wrapped = FunctionTool(original)
        
        assert wrapped.name == "original"
        assert "Add two numbers" in wrapped.description
        assert wrapped(1, 2) == 3
        assert wrapped.run(x=1, y=2) == 3


class TestAgentIntegration:
    """Tests for Agent integration with plugin tools."""
    
    def test_agent_with_basetool_instance(self):
        """Agent should accept BaseTool instances in tools list."""
        from praisonaiagents import Agent, BaseTool
        
        class AddTool(BaseTool):
            name = "add"
            description = "Add two numbers"
            
            def run(self, a: int, b: int) -> int:
                return a + b
        
        tool = AddTool()
        agent = Agent(
            name="TestAgent",
            role="Tester",
            goal="Test tools",
            tools=[tool]
        )
        
        assert len(agent.tools) == 1
        assert agent.tools[0] is tool
    
    def test_agent_with_decorated_tool(self):
        """Agent should accept @tool decorated functions."""
        from praisonaiagents import Agent, tool
        
        @tool
        def multiply(a: int, b: int) -> int:
            """Multiply two numbers."""
            return a * b
        
        agent = Agent(
            name="TestAgent",
            role="Tester",
            goal="Test tools",
            tools=[multiply]
        )
        
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "multiply"
    
    def test_agent_execute_basetool(self):
        """Agent.execute_tool should work with BaseTool instances."""
        from praisonaiagents import Agent, BaseTool
        
        class ConcatTool(BaseTool):
            name = "concat"
            description = "Concatenate strings"
            
            def run(self, a: str, b: str) -> str:
                return a + b
        
        agent = Agent(
            name="TestAgent",
            role="Tester",
            goal="Test tools",
            tools=[ConcatTool()]
        )
        
        result = agent.execute_tool("concat", {"a": "hello", "b": "world"})
        assert result == "helloworld"
    
    def test_agent_execute_decorated_tool(self):
        """Agent.execute_tool should work with @tool decorated functions."""
        from praisonaiagents import Agent, tool
        
        @tool
        def subtract(a: int, b: int) -> int:
            """Subtract b from a."""
            return a - b
        
        agent = Agent(
            name="TestAgent",
            role="Tester",
            goal="Test tools",
            tools=[subtract]
        )
        
        result = agent.execute_tool("subtract", {"a": 10, "b": 3})
        assert result == 7
    
    def test_agent_with_tool_names_from_registry(self):
        """Agent should resolve tool names from registry."""
        from praisonaiagents import Agent, BaseTool, register_tool, get_registry
        
        # Clear registry first
        get_registry().clear()
        
        class DivideTool(BaseTool):
            name = "divide"
            description = "Divide two numbers"
            
            def run(self, a: float, b: float) -> float:
                return a / b
        
        # Register tool
        register_tool(DivideTool())
        
        # Create agent with tool name string
        agent = Agent(
            name="TestAgent",
            role="Tester",
            goal="Test tools",
            tools=["divide"]
        )
        
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "divide"
        
        # Clean up
        get_registry().clear()
    
    def test_agent_execute_tool_from_registry(self):
        """Agent should find tools in registry during execute_tool."""
        from praisonaiagents import Agent, BaseTool, register_tool, get_registry
        
        # Clear registry first
        get_registry().clear()
        
        class PowerTool(BaseTool):
            name = "power"
            description = "Raise to power"
            
            def run(self, base: int, exp: int) -> int:
                return base ** exp
        
        register_tool(PowerTool())
        
        # Agent without tools - should still find from registry
        agent = Agent(
            name="TestAgent",
            role="Tester",
            goal="Test tools",
            tools=[]
        )
        
        result = agent.execute_tool("power", {"base": 2, "exp": 3})
        assert result == 8
        
        # Clean up
        get_registry().clear()


class TestPluginDiscovery:
    """Tests for entry_points plugin discovery."""
    
    def test_discover_plugins_returns_count(self):
        """discover_plugins() should return number of plugins found."""
        from praisonaiagents import ToolRegistry
        
        registry = ToolRegistry()
        count = registry.discover_plugins()
        # Should return 0 or more (no external plugins installed in test env)
        assert isinstance(count, int)
        assert count >= 0
    
    def test_discover_plugins_only_runs_once(self):
        """discover_plugins() should only run once per registry."""
        from praisonaiagents import ToolRegistry
        
        registry = ToolRegistry()
        _count1 = registry.discover_plugins()  # First call
        count2 = registry.discover_plugins()
        
        # Second call should return 0 (already discovered)
        assert count2 == 0
        assert _count1 >= 0  # Use variable to avoid lint warning
    
    def test_discover_plugins_with_mock_entry_point(self, mocker):
        """Should load tools from mocked entry_points."""
        from praisonaiagents import ToolRegistry, BaseTool
        from unittest.mock import MagicMock
        
        # Create a mock tool class
        class MockPluginTool(BaseTool):
            name = "mock_plugin"
            description = "A mocked plugin tool"
            def run(self) -> str:
                return "mocked"
        
        # Create mock entry point
        mock_ep = MagicMock()
        mock_ep.name = "mock_plugin"
        mock_ep.load.return_value = MockPluginTool
        
        # Reset the lazy-loaded entry_points cache
        import praisonaiagents.tools.registry as registry_module
        registry_module._entry_points = None
        
        # Mock entry_points at the source (importlib.metadata)
        mocker.patch(
            'importlib.metadata.entry_points',
            return_value=[mock_ep]
        )
        
        registry = ToolRegistry()
        count = registry.discover_plugins()
        
        assert count == 1
        assert "mock_plugin" in registry
        
        tool = registry.get("mock_plugin")
        assert tool.run() == "mocked"
    
    def test_discover_plugins_handles_load_error(self, mocker):
        """Should handle errors when loading plugins gracefully."""
        from praisonaiagents import ToolRegistry
        from unittest.mock import MagicMock
        
        # Create mock entry point that raises on load
        mock_ep = MagicMock()
        mock_ep.name = "broken_plugin"
        mock_ep.load.side_effect = ImportError("Module not found")
        
        # Reset the lazy-loaded entry_points cache
        import praisonaiagents.tools.registry as registry_module
        registry_module._entry_points = None
        
        # Mock entry_points at the source (importlib.metadata)
        mocker.patch(
            'importlib.metadata.entry_points',
            return_value=[mock_ep]
        )
        
        registry = ToolRegistry()
        # Should not raise, just log warning
        count = registry.discover_plugins()
        
        assert count == 0
        assert "broken_plugin" not in registry
    
    def test_discover_callable_function(self, mocker):
        """Should register plain functions from entry_points."""
        from praisonaiagents import ToolRegistry
        from unittest.mock import MagicMock
        
        def plugin_function(x: str) -> str:
            return f"plugin: {x}"
        
        mock_ep = MagicMock()
        mock_ep.name = "func_plugin"
        mock_ep.load.return_value = plugin_function
        
        # Reset the lazy-loaded entry_points cache
        import praisonaiagents.tools.registry as registry_module
        registry_module._entry_points = None
        
        # Mock entry_points at the source (importlib.metadata)
        mocker.patch(
            'importlib.metadata.entry_points',
            return_value=[mock_ep]
        )
        
        registry = ToolRegistry()
        count = registry.discover_plugins()
        
        assert count == 1
        func = registry.get("func_plugin")
        assert func("test") == "plugin: test"
    
    def test_auto_discover_on_get_if_not_found(self, mocker):
        """get() should trigger discovery if tool not found."""
        from praisonaiagents import ToolRegistry, BaseTool
        from unittest.mock import MagicMock
        
        class LazyTool(BaseTool):
            name = "lazy_tool"
            description = "Lazy loaded"
            def run(self) -> str:
                return "lazy"
        
        mock_ep = MagicMock()
        mock_ep.name = "lazy_tool"
        mock_ep.load.return_value = LazyTool
        
        # Reset the lazy-loaded entry_points cache
        import praisonaiagents.tools.registry as registry_module
        registry_module._entry_points = None
        
        # Mock entry_points at the source (importlib.metadata)
        mocker.patch(
            'importlib.metadata.entry_points',
            return_value=[mock_ep]
        )
        
        registry = ToolRegistry()
        # Don't call discover_plugins() explicitly
        # get() should trigger it
        tool = registry.get("lazy_tool")
        
        assert tool is not None
        assert tool.run() == "lazy"


class TestToolValidation:
    """Tests for tool validation."""
    
    def test_import_validation_error(self):
        """ToolValidationError should be importable."""
        from praisonaiagents import ToolValidationError
        assert ToolValidationError is not None
    
    def test_import_validate_tool(self):
        """validate_tool should be importable."""
        from praisonaiagents import validate_tool
        assert validate_tool is not None
    
    def test_valid_tool_passes_validation(self):
        """Valid tool should pass validation."""
        from praisonaiagents import BaseTool
        
        class ValidTool(BaseTool):
            name = "valid"
            description = "A valid tool"
            
            def run(self) -> str:
                return "ok"
        
        tool = ValidTool()
        assert tool.validate() is True
    
    def test_tool_without_name_gets_auto_name(self):
        """Tool without name should get auto-generated name from class."""
        from praisonaiagents import BaseTool
        
        class MyCustomTool(BaseTool):
            name = ""  # Empty name - will be auto-filled
            description = "Has description"
            
            def run(self) -> str:
                return "ok"
        
        tool = MyCustomTool()
        # Name should be auto-generated from class name
        assert tool.name == "mycustom"  # "MyCustomTool" -> "mycustom" (lowercase, "tool" removed)
        assert tool.validate() is True
    
    def test_tool_without_description_gets_auto_description(self):
        """Tool without description should get auto-generated description."""
        from praisonaiagents import BaseTool
        
        class NoDescTool(BaseTool):
            """This is the docstring description."""
            name = "no_desc"
            description = ""  # Empty - will use docstring
            
            def run(self) -> str:
                return "ok"
        
        tool = NoDescTool()
        # Description should be auto-generated from docstring
        assert "docstring description" in tool.description
        assert tool.validate() is True
    
    def test_tool_with_manually_cleared_name_fails(self):
        """Tool with name manually cleared after init should fail validation."""
        from praisonaiagents import BaseTool, ToolValidationError
        
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Test"
            def run(self) -> str:
                return "ok"
        
        tool = MyTool()
        tool.name = ""  # Manually clear after init
        with pytest.raises(ToolValidationError):
            tool.validate()
    
    def test_validate_tool_function_with_basetool(self):
        """validate_tool() should work with BaseTool instances."""
        from praisonaiagents import BaseTool, validate_tool
        
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Test"
            def run(self) -> str:
                return "ok"
        
        assert validate_tool(MyTool()) is True
    
    def test_validate_tool_function_with_callable(self):
        """validate_tool() should work with plain callables."""
        from praisonaiagents import validate_tool
        
        def my_func() -> str:
            return "ok"
        
        assert validate_tool(my_func) is True
    
    def test_validate_tool_rejects_invalid_type(self):
        """validate_tool() should reject non-tool objects."""
        from praisonaiagents import validate_tool, ToolValidationError
        
        with pytest.raises(ToolValidationError):
            validate_tool("not a tool")
        
        with pytest.raises(ToolValidationError):
            validate_tool(123)
    
    def test_validate_class_method(self):
        """BaseTool.validate_class() should check class validity."""
        from praisonaiagents import BaseTool
        
        class ValidTool(BaseTool):
            name = "valid"
            description = "Valid"
            def run(self) -> str:
                return "ok"
        
        assert ValidTool.validate_class() is True
    
    def test_decorated_tool_passes_validation(self):
        """@tool decorated functions should pass validation."""
        from praisonaiagents import tool, validate_tool
        
        @tool
        def my_search(query: str) -> list:
            """Search for things."""
            return []
        
        assert validate_tool(my_search) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

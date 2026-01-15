"""
Tool Protocol Definitions.

Provides Protocol interfaces that define the minimal contract for tool implementations.
This enables:
- Mocking tools in tests without real execution
- Creating custom tool implementations
- Type checking with static analyzers

These protocols are lightweight and have zero performance impact.
"""
from typing import Protocol, runtime_checkable, Any, Dict, Optional


@runtime_checkable
class ToolProtocol(Protocol):
    """
    Minimal Protocol for tool implementations.
    
    This defines the essential interface that any tool must provide.
    It enables proper mocking and testing.
    
    Example:
        ```python
        # Create a mock tool for testing
        class MockSearchTool:
            name = "mock_search"
            description = "Mock search tool"
            
            def run(self, query: str = "", **kwargs) -> str:
                return f"Mock results for: {query}"
            
            def get_schema(self) -> dict:
                return {
                    "type": "function",
                    "function": {
                        "name": self.name,
                        "description": self.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"}
                            }
                        }
                    }
                }
        
        # Use as tool
        tool: ToolProtocol = MockSearchTool()
        ```
    """
    
    @property
    def name(self) -> str:
        """The tool's unique name/identifier."""
        ...
    
    @property
    def description(self) -> str:
        """Description of what the tool does."""
        ...
    
    def run(self, **kwargs) -> Any:
        """
        Execute the tool with given arguments.
        
        Args:
            **kwargs: Tool-specific arguments
            
        Returns:
            Tool output (any type)
        """
        ...
    
    def get_schema(self) -> Dict[str, Any]:
        """
        Get OpenAI-compatible function schema for this tool.
        
        Returns:
            Dict containing the function schema in OpenAI format
        """
        ...


@runtime_checkable
class CallableToolProtocol(ToolProtocol, Protocol):
    """
    Protocol for tools that can be called directly.
    """
    
    def __call__(self, **kwargs) -> Any:
        """Allow direct calling like tool(arg=value)."""
        ...


@runtime_checkable
class AsyncToolProtocol(Protocol):
    """
    Protocol for tools that support async execution.
    """
    
    @property
    def name(self) -> str:
        """The tool's unique name/identifier."""
        ...
    
    async def arun(self, **kwargs) -> Any:
        """
        Async execute the tool with given arguments.
        
        Args:
            **kwargs: Tool-specific arguments
            
        Returns:
            Tool output (any type)
        """
        ...


@runtime_checkable
class ValidatableToolProtocol(ToolProtocol, Protocol):
    """
    Protocol for tools that support validation.
    """
    
    def validate(self) -> bool:
        """
        Validate the tool configuration.
        
        Returns:
            True if validation passes
            
        Raises:
            ToolValidationError: If validation fails
        """
        ...


__all__ = [
    'ToolProtocol',
    'CallableToolProtocol', 
    'AsyncToolProtocol',
    'ValidatableToolProtocol',
]

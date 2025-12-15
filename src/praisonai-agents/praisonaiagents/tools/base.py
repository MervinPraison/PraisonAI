"""Base classes for PraisonAI Agent tools.

This module provides the foundation for creating tools that can be used by agents.
External developers can create plugins by subclassing BaseTool.

Usage:
    from praisonaiagents import BaseTool

    class MyTool(BaseTool):
        name = "my_tool"
        description = "Does something useful"
        
        def run(self, query: str) -> str:
            return f"Result for {query}"
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, get_type_hints
import inspect
import logging


class ToolValidationError(Exception):
    """Raised when a tool fails validation."""
    pass


class ToolResult:
    """Wrapper for tool execution results."""
    
    def __init__(
        self,
        output: Any,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.output = output
        self.success = success
        self.error = error
        self.metadata = metadata or {}
    
    def __str__(self) -> str:
        if self.success:
            return str(self.output)
        return f"Error: {self.error}"
    
    def __repr__(self) -> str:
        return f"ToolResult(success={self.success}, output={self.output!r})"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "output": self.output,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata
        }


class BaseTool(ABC):
    """Abstract base class for all PraisonAI tools.
    
    Subclass this to create custom tools that can be:
    - Used directly by agents
    - Distributed as pip-installable plugins
    - Auto-discovered via entry_points
    
    Attributes:
        name: Unique identifier for the tool
        description: Human-readable description (used by LLM)
        version: Tool version string (default: "1.0.0")
        parameters: JSON Schema for parameters (auto-generated if not provided)
    
    Example:
        class WeatherTool(BaseTool):
            name = "get_weather"
            description = "Get current weather for a location"
            
            def run(self, location: str, units: str = "celsius") -> dict:
                # Implementation here
                return {"temp": 22, "condition": "sunny"}
    """
    
    # Required class attributes (must be overridden)
    name: str = ""
    description: str = ""
    
    # Optional class attributes
    version: str = "1.0.0"
    parameters: Optional[Dict[str, Any]] = None  # JSON Schema, auto-generated if None
    
    def __init__(self):
        """Initialize the tool and validate configuration."""
        if not self.name:
            # Use class name as default
            self.name = self.__class__.__name__.lower().replace("tool", "")
        
        if not self.description:
            # Use docstring as default
            self.description = self.__class__.__doc__ or f"Tool: {self.name}"
        
        # Auto-generate parameters schema if not provided
        if self.parameters is None:
            self.parameters = self._generate_parameters_schema()
    
    def _generate_parameters_schema(self) -> Dict[str, Any]:
        """Generate JSON Schema from run() method signature."""
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        try:
            sig = inspect.signature(self.run)
            hints = get_type_hints(self.run) if hasattr(self.run, '__annotations__') else {}
            
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                
                # Get type hint
                param_type = hints.get(param_name, Any)
                json_type = self._python_type_to_json(param_type)
                
                # Build property schema
                prop_schema = {"type": json_type}
                
                # Add description from docstring if available
                # (Could parse docstring for param descriptions)
                
                schema["properties"][param_name] = prop_schema
                
                # Check if required (no default value)
                if param.default is inspect.Parameter.empty:
                    schema["required"].append(param_name)
        except Exception as e:
            logging.debug(f"Could not generate schema for {self.name}: {e}")
        
        return schema
    
    @staticmethod
    def _python_type_to_json(python_type: Type) -> str:
        """Convert Python type to JSON Schema type."""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
            type(None): "null"
        }
        
        # Handle Optional, Union, etc.
        origin = getattr(python_type, '__origin__', None)
        if origin is not None:
            # For List[X], return "array"
            if origin is list:
                return "array"
            # For Dict[X, Y], return "object"
            if origin is dict:
                return "object"
        
        return type_map.get(python_type, "string")
    
    @abstractmethod
    def run(self, **kwargs) -> Any:
        """Execute the tool with given arguments.
        
        This method must be implemented by subclasses.
        
        Args:
            **kwargs: Tool-specific arguments
            
        Returns:
            Tool output (any type, will be converted to string for LLM)
        """
        pass
    
    def __call__(self, **kwargs) -> Any:
        """Allow tool to be called directly like a function."""
        return self.run(**kwargs)
    
    def safe_run(self, **kwargs) -> ToolResult:
        """Execute tool with error handling, returning ToolResult."""
        try:
            output = self.run(**kwargs)
            return ToolResult(output=output, success=True)
        except Exception as e:
            logging.error(f"Tool {self.name} failed: {e}")
            return ToolResult(
                output=None,
                success=False,
                error=str(e)
            )
    
    def get_schema(self) -> Dict[str, Any]:
        """Get OpenAI-compatible function schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', description='{self.description[:50]}...')"
    
    def validate(self) -> bool:
        """Validate the tool configuration.
        
        Raises:
            ToolValidationError: If validation fails
            
        Returns:
            True if validation passes
        """
        errors = []
        
        # Check required fields
        if not self.name or not isinstance(self.name, str):
            errors.append("Tool must have a non-empty string 'name'")
        
        if not self.description or not isinstance(self.description, str):
            errors.append("Tool must have a non-empty string 'description'")
        
        # Check that run() is implemented (not abstract)
        if getattr(self.run, '__isabstractmethod__', False):
            errors.append("Tool must implement the 'run()' method")
        
        # Check parameters schema is valid
        if self.parameters:
            if not isinstance(self.parameters, dict):
                errors.append("'parameters' must be a dictionary")
            elif "type" not in self.parameters:
                errors.append("'parameters' must have a 'type' field")
        
        if errors:
            raise ToolValidationError(f"Tool '{self.name}' validation failed: {'; '.join(errors)}")
        
        return True
    
    @classmethod
    def validate_class(cls) -> bool:
        """Validate a tool class before instantiation.
        
        This can be used to check if a class is a valid tool without creating an instance.
        
        Returns:
            True if the class appears to be a valid tool
        """
        # Check it's a subclass of BaseTool
        if not issubclass(cls, BaseTool):
            return False
        
        # Check it has required class attributes or will get them from __init__
        # (name and description can be set in __init__ so we can't strictly require them)
        
        # Check run() is defined (not just inherited abstract)
        if 'run' not in cls.__dict__:
            return False
        
        return True


def validate_tool(tool: Any) -> bool:
    """Validate any tool-like object.
    
    Args:
        tool: Object to validate (BaseTool, callable, etc.)
        
    Returns:
        True if valid
        
    Raises:
        ToolValidationError: If validation fails
    """
    if isinstance(tool, BaseTool):
        return tool.validate()
    
    if callable(tool):
        # For plain functions, check they have a name
        name = getattr(tool, '__name__', None) or getattr(tool, 'name', None)
        if not name:
            raise ToolValidationError("Callable tool must have a __name__ or name attribute")
        return True
    
    raise ToolValidationError(f"Invalid tool type: {type(tool)}")


# For backward compatibility - tools can also just be functions
# The @tool decorator (in decorator.py) wraps functions into BaseTool instances

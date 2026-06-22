"""
Tool execution mixin for the Agent class.

Contains all methods for tool resolution, execution, approval,
cost tracking, and hook integration. Extracted from agent.py
for maintainability.
"""

import os
import time
import json
import logging
import asyncio
import inspect
import contextvars
import concurrent.futures
import random
from typing import List, Optional, Any, Dict, Union, TYPE_CHECKING
from ..errors import ToolExecutionError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class ToolExecutionMixin:
    """Mixin providing tool execution methods for the Agent class."""

    def _get_existing_stream_emitter(self):
        """Return an already-initialized stream emitter without creating one."""
        emitter = getattr(self, "_stream_emitter", None)
        if emitter is not None:
            return emitter

        # Support name-mangled private attributes across class renames/inheritance.
        for cls in type(self).mro():
            mangled = f"_{cls.__name__}__stream_emitter"
            if hasattr(self, mangled):
                emitter = getattr(self, mangled, None)
                if emitter is not None:
                    return emitter
        return None

    def _resolve_tool_names(self, tool_names):
        """Resolve tool names to actual tool instances from registry.
        
        Args:
            tool_names: List of tool name strings
            
        Returns:
            List of resolved tool instances
        """
        resolved = []
        try:
            from ..tools.registry import get_registry
            registry = get_registry()
            
            for name in tool_names:
                tool = registry.get(name)
                if tool is not None:
                    resolved.append(tool)
                else:
                    logging.warning(f"Tool '{name}' not found in registry")
        except ImportError:
            logging.warning("Tool registry not available, cannot resolve tool names")
        
        return resolved

    def _cast_arguments(self, func, arguments):
        """Cast arguments to their expected types based on function signature."""
        if not callable(func) or not arguments:
            return arguments
        
        try:
            sig = inspect.signature(func)
            valid_params = set(sig.parameters.keys()) - {'self'}
            casted_args = {}
            
            # Sanitize argument names: strip trailing '=', whitespace, and
            # other invalid chars that LLMs sometimes hallucinate in kwarg names
            sanitized = {}
            for raw_name, arg_value in arguments.items():
                clean = raw_name.strip().rstrip('=').strip()
                # If the cleaned name matches a valid param, use it;
                # otherwise try case-insensitive match
                if clean in valid_params:
                    sanitized[clean] = arg_value
                elif clean.lower() in {p.lower() for p in valid_params}:
                    # Case-insensitive fuzzy match
                    matched = next(p for p in valid_params if p.lower() == clean.lower())
                    sanitized[matched] = arg_value
                else:
                    sanitized[clean] = arg_value
            arguments = sanitized
            
            for param_name, arg_value in arguments.items():
                if param_name in sig.parameters:
                    param = sig.parameters[param_name]
                    if param.annotation != inspect.Parameter.empty:
                        # Try to cast to the expected type
                        annotation = param.annotation
                        # Handle Optional types
                        if hasattr(annotation, '__origin__'):
                            if annotation.__origin__ is Union:
                                # Get non-None type from Union
                                types = [t for t in annotation.__args__ if t != type(None)]
                                if types:
                                    annotation = types[0]
                        
                        # Cast if it's a basic type
                        if annotation in (int, float, str, bool):
                            try:
                                if annotation is bool and isinstance(arg_value, str):
                                    # Special handling for bool strings
                                    casted_args[param_name] = arg_value.lower() in ('true', '1', 'yes')
                                else:
                                    casted_args[param_name] = annotation(arg_value)
                            except (ValueError, TypeError):
                                casted_args[param_name] = arg_value
                        else:
                            casted_args[param_name] = arg_value
                    else:
                        casted_args[param_name] = arg_value
                else:
                    # Keep unexpected parameters as is (function may use **kwargs)
                    casted_args[param_name] = arg_value
            
            return casted_args
        except Exception:
            # If signature inspection fails, return arguments as is
            return arguments
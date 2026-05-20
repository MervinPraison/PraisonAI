"""
Tool whitelist filter module with diagnostics.

This module provides a canonical implementation of the ALLOWED_TOOLS filter
that prevents tool name collisions in multi-environment agent systems by 
whitelisting only specified tools.

The filter is designed to solve the "tool shadowing" problem where multiple
modules register tools with overlapping or ambiguous names, causing agents
to invoke the wrong implementation.

Environment Variables:
    ALLOWED_TOOLS: Primary variable (comma-separated tool names)
    HERMES_ONLY_TOOLS: Backward compatibility alias for ALLOWED_TOOLS

Usage:
    from praisonaiagents.hermes_filter import AllowedToolsFilter
    
    # Create filter from environment variable  
    filter = AllowedToolsFilter()
    
    # Filter tools
    available_tools = {"search", "send_message", "extract_pdf"}
    filtered_tools = filter.filter_tools(available_tools)
    
    # Get diagnostics
    filter.log_diagnostics()
"""

import os
import logging
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


class AllowedToolsFilter:
    """
    Canonical tool whitelist filter with diagnostics and backward compatibility.
    
    This filter implements the semantics for tool filtering:
    - ALLOWED_TOOLS unset (or HERMES_ONLY_TOOLS): all tools visible (with warning about collisions)
    - ALLOWED_TOOLS empty string: error - must specify tools or unset
    - ALLOWED_TOOLS with values: only whitelisted tools visible
    - Unknown tools in list: warn and strip in dev, strict fail in CI
    
    Backward Compatibility:
    - Supports both ALLOWED_TOOLS and HERMES_ONLY_TOOLS
    - ALLOWED_TOOLS takes precedence if both are set
    """
    
    def __init__(self, env_var_name: str = "ALLOWED_TOOLS"):
        """
        Initialize the filter with backward compatibility support.
        
        Args:
            env_var_name: Primary environment variable name (default: "ALLOWED_TOOLS")
        """
        # Support both new (ALLOWED_TOOLS) and legacy (HERMES_ONLY_TOOLS) naming
        self.primary_var = env_var_name
        self.legacy_var = "HERMES_ONLY_TOOLS"
        
        # ALLOWED_TOOLS takes precedence over HERMES_ONLY_TOOLS for backward compatibility
        self.env_value = os.environ.get(self.primary_var) or os.environ.get(self.legacy_var)
        self.env_var_name = self.primary_var if os.environ.get(self.primary_var) else self.legacy_var
        
        self.is_ci = os.environ.get("CI", "").lower() in ("true", "1", "yes")
        self._whitelist: Optional[Set[str]] = self._parse_whitelist()
        self._diagnostics: Dict[str, Any] = {}
        
    def _parse_whitelist(self) -> Optional[Set[str]]:
        """
        Parse the environment variable value into a whitelist set.
        
        Returns:
            None if unset, Set of tool names if set, raises ValueError for empty string
        """
        if self.env_value is None:
            return None
        
        # Empty string is an error - must be explicit
        if self.env_value.strip() == "":
            raise ValueError(
                f"{self.env_var_name} cannot be empty. Either unset it for all tools "
                "or provide a comma-separated list of tool names."
            )
        
        # Parse comma-separated values, strip whitespace
        tools = {name.strip() for name in self.env_value.split(",") if name.strip()}
        
        if not tools:
            raise ValueError(
                f"{self.env_var_name} contains no valid tool names. "
                "Provide comma-separated tool names or unset the variable."
            )
        
        return tools
    
    def filter_tools(self, available_tools: Union[Set[str], List[str], Dict[str, Any]]) -> Set[str]:
        """
        Filter tools based on HERMES_ONLY_TOOLS whitelist.
        
        Args:
            available_tools: Available tools as set, list, or dict with tool names as keys
            
        Returns:
            Filtered set of tool names
            
        Raises:
            ValueError: If unknown tools in CI mode or configuration errors
        """
        # Convert input to set of tool names
        if isinstance(available_tools, dict):
            tool_names = set(available_tools.keys())
        else:
            tool_names = set(available_tools)
        
        # Store for diagnostics
        self._diagnostics["registered_before_filter"] = sorted(tool_names)
        
        # If no whitelist, return all tools (with warning)
        if self._whitelist is None:
            logger.warning(
                "Tool whitelist is unset. All %d tools are visible. "
                "Consider using ALLOWED_TOOLS to prevent tool name collisions.",
                len(tool_names)
            )
            self._diagnostics["registered_after_filter"] = sorted(tool_names)
            self._diagnostics["dropped_tools"] = []
            self._diagnostics["unknown_tools"] = []
            return tool_names
        
        # Find intersection and unknown tools
        available_whitelisted = tool_names.intersection(self._whitelist)
        unknown_tools = self._whitelist.difference(tool_names)
        dropped_tools = tool_names.difference(self._whitelist)
        
        # Store for diagnostics
        self._diagnostics["registered_after_filter"] = sorted(available_whitelisted)
        self._diagnostics["dropped_tools"] = sorted(dropped_tools)
        self._diagnostics["unknown_tools"] = sorted(unknown_tools)
        
        # Handle unknown tools based on environment
        if unknown_tools:
            unknown_list = sorted(unknown_tools)
            if self.is_ci:
                raise ValueError(
                    f"Unknown tools in {self.env_var_name}: {unknown_list}. "
                    "All specified tools must be available in CI mode."
                )
            else:
                logger.warning(
                    "Unknown tools in %s will be ignored: %s",
                    self.env_var_name,
                    unknown_list
                )
        
        if dropped_tools:
            logger.info(
                "Dropped %d tools not in %s whitelist: %s",
                len(dropped_tools),
                self.env_var_name,
                sorted(dropped_tools)
            )
        
        logger.info(
            "%s filtered tools: %d available, %d after filter",
            self.env_var_name,
            len(tool_names),
            len(available_whitelisted)
        )
        
        return available_whitelisted
    
    def log_diagnostics(self) -> None:
        """Log startup diagnostics section as specified in the issue."""
        if not self._diagnostics:
            logger.warning("No diagnostics available. Call filter_tools() first.")
            return
        
        logger.info("=" * 50)
        logger.info("ALLOWED_TOOLS FILTER DIAGNOSTICS")
        logger.info("=" * 50)
        logger.info("%s=%s", self.env_var_name, self.env_value or "<unset>")
        logger.info("RegisteredBeforeFilter=%s", self._diagnostics.get("registered_before_filter", []))
        logger.info("RegisteredAfterFilter=%s", self._diagnostics.get("registered_after_filter", []))
        logger.info("DroppedTools=%s", self._diagnostics.get("dropped_tools", []))
        logger.info("UnknownTools=%s", self._diagnostics.get("unknown_tools", []))
        logger.info("IsCI=%s", self.is_ci)
        logger.info("=" * 50)
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Get diagnostics data as a dictionary.
        
        Returns:
            Dictionary with diagnostics information
        """
        return {
            "env_var_name": self.env_var_name,
            "env_value": self.env_value,
            "is_ci": self.is_ci,
            "whitelist": list(self._whitelist) if self._whitelist else None,
            **self._diagnostics
        }
    
    def is_enabled(self) -> bool:
        """
        Check if filtering is enabled.
        
        Returns:
            True if tool whitelist is set and filtering is active
        """
        return self._whitelist is not None
    
    def get_whitelist(self) -> Optional[Set[str]]:
        """
        Get the current whitelist.
        
        Returns:
            Set of whitelisted tool names, or None if not set
        """
        return self._whitelist.copy() if self._whitelist else None


def filter_tools_with_allowed_tools(
    available_tools: Union[Set[str], List[str], Dict[str, Any]],
    env_var_name: str = "ALLOWED_TOOLS",
    log_diagnostics: bool = True
) -> Set[str]:
    """
    Convenience function to filter tools with ALLOWED_TOOLS.
    
    Args:
        available_tools: Available tools to filter
        env_var_name: Environment variable name (default: "ALLOWED_TOOLS")
        log_diagnostics: Whether to log diagnostics (default: True)
        
    Returns:
        Filtered set of tool names
    """
    filter_instance = AllowedToolsFilter(env_var_name)
    filtered = filter_instance.filter_tools(available_tools)
    
    if log_diagnostics:
        filter_instance.log_diagnostics()
    
    return filtered


# Backward compatibility aliases
filter_tools_with_hermes = filter_tools_with_allowed_tools
hermes_filter = filter_tools_with_allowed_tools
apply_hermes_filter = filter_tools_with_allowed_tools

# Legacy class alias for backward compatibility
HermesToolFilter = AllowedToolsFilter

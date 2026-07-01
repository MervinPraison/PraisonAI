"""
Telemetry Handler for CLI.

Provides usage monitoring and analytics.
Usage: praisonai "prompt" --telemetry
"""

from typing import Any, Dict, Tuple
from .base import FlagHandler

# Lazy imports
enable_telemetry = None
disable_telemetry = None
get_telemetry = None


def _load_telemetry():
    """Load telemetry functions lazily."""
    global enable_telemetry, disable_telemetry, get_telemetry
    try:
        from praisonaiagents import (
            enable_telemetry as _enable,
            disable_telemetry as _disable,
            get_telemetry as _get
        )
        enable_telemetry = _enable
        disable_telemetry = _disable
        get_telemetry = _get
        return True
    except ImportError:
        return False


class TelemetryHandler(FlagHandler):
    """
    Handler for --telemetry flag.
    
    Enables usage monitoring and analytics for agent executions.
    
    Example:
        praisonai "Task" --telemetry
    """
    
    @property
    def feature_name(self) -> str:
        return "telemetry"
    
    @property
    def flag_name(self) -> str:
        return "telemetry"
    
    @property
    def flag_help(self) -> str:
        return "Enable usage monitoring and analytics"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if telemetry is available."""
        if _load_telemetry():
            return True, ""
        return False, "Telemetry requires praisonaiagents[telemetry]. Install with: pip install praisonaiagents[telemetry]"
    
    def enable(self, **kwargs) -> bool:
        """
        Enable telemetry.
        
        Args:
            **kwargs: Additional telemetry configuration
            
        Returns:
            True if enabled successfully
        """
        if not _load_telemetry():
            self.print_status(
                "Telemetry not available. Install with: pip install praisonaiagents[telemetry]",
                "warning"
            )
            return False
        
        try:
            enable_telemetry(**kwargs)
            self.print_status("📊 Telemetry enabled", "success")
            return True
        except Exception as e:
            self.log(f"Failed to enable telemetry: {e}", "error")
            return False
    
    def disable(self) -> bool:
        """
        Disable telemetry.
        
        Returns:
            True if disabled successfully
        """
        if not _load_telemetry():
            return True  # Already disabled
        
        try:
            disable_telemetry()
            self.print_status("📊 Telemetry disabled", "info")
            return True
        except Exception as e:
            self.log(f"Failed to disable telemetry: {e}", "error")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get telemetry statistics.
        
        Returns:
            Dictionary of telemetry stats
        """
        if not _load_telemetry():
            return {}
        
        try:
            telemetry = get_telemetry()
            if telemetry and hasattr(telemetry, 'get_stats'):
                return telemetry.get_stats()
        except Exception as e:
            self.log(f"Failed to get telemetry stats: {e}", "warning")
        
        return {}
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply telemetry configuration.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Boolean indicating if telemetry should be enabled
            
        Returns:
            Modified configuration
        """
        if flag_value:
            self.enable()
        return config
    
    def post_process_result(self, result: Any, flag_value: Any) -> Any:
        """
        Post-process result to show telemetry summary.
        
        Args:
            result: Agent output
            flag_value: Boolean indicating if telemetry is enabled
            
        Returns:
            Original result (telemetry summary is printed)
        """
        if not flag_value:
            return result
        
        stats = self.get_stats()
        if stats:
            self.print_status("\n📊 Telemetry Summary:", "info")
            for key, value in stats.items():
                self.print_status(f"  {key}: {value}", "info")
        
        return result
    
    def execute(self, action: str = "enable", **kwargs) -> Any:
        """
        Execute telemetry action.
        
        Args:
            action: Action to perform (enable, disable, stats)
            
        Returns:
            Result of the action
        """
        if action == "enable":
            return self.enable(**kwargs)
        elif action == "disable":
            return self.disable()
        elif action == "stats":
            return self.get_stats()
        else:
            self.print_status(f"Unknown telemetry action: {action}", "error")
            return None

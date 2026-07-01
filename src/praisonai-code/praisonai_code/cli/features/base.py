"""
Base handler class for CLI features.

All CLI feature handlers inherit from this base class to ensure
consistent interface and behavior.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """
    Base class for all CLI feature handlers.
    
    Provides common functionality and interface for feature handlers.
    Each handler is responsible for a specific CLI feature.
    """
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the handler.
        
        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
        self._initialized = False
    
    @property
    @abstractmethod
    def feature_name(self) -> str:
        """Return the name of this feature."""
        pass
    
    @property
    def is_available(self) -> bool:
        """Check if the feature dependencies are available."""
        return True
    
    def log(self, message: str, level: str = "info"):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            getattr(logger, level)(f"[{self.feature_name}] {message}")
    
    def print_status(self, message: str, status: str = "info"):
        """Print a status message with color coding."""
        from rich import print as rprint
        
        colors = {
            "info": "cyan",
            "success": "green", 
            "warning": "yellow",
            "error": "red"
        }
        color = colors.get(status, "white")
        rprint(f"[{color}]{message}[/{color}]")
    
    def check_dependencies(self) -> tuple[bool, str]:
        """
        Check if required dependencies are installed.
        
        Returns:
            Tuple of (available, error_message)
        """
        return True, ""
    
    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        """
        Execute the feature's main functionality.
        
        This method must be implemented by each handler.
        """
        pass


class CommandHandler(BaseHandler):
    """
    Base class for CLI command handlers (e.g., 'praisonai knowledge').
    
    Command handlers process subcommands like:
    - praisonai <command> <action> [args]
    """
    
    @abstractmethod
    def get_actions(self) -> List[str]:
        """Return list of supported actions for this command."""
        pass
    
    def get_help_text(self) -> str:
        """Return help text for this command."""
        return f"Available actions: {', '.join(self.get_actions())}"
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> Any:
        """
        Execute a command action.
        
        Args:
            action: The action to perform
            action_args: Arguments for the action
            **kwargs: Additional keyword arguments
        """
        if action == 'help' or action == '--help':
            self.print_help()
            return
        
        method_name = f"action_{action.replace('-', '_')}"
        if hasattr(self, method_name):
            return getattr(self, method_name)(action_args, **kwargs)
        else:
            self.print_status(f"Unknown action: {action}", "error")
            self.print_help()
    
    def print_help(self):
        """Print help for this command."""
        from rich import print as rprint
        rprint(f"[bold]{self.feature_name.title()} Commands:[/bold]")
        rprint(self.get_help_text())


class FlagHandler(BaseHandler):
    """
    Base class for CLI flag handlers (e.g., '--guardrail').
    
    Flag handlers modify agent behavior or add functionality
    when a specific flag is provided.
    """
    
    @property
    @abstractmethod
    def flag_name(self) -> str:
        """Return the flag name (without --)."""
        pass
    
    @property
    def flag_help(self) -> str:
        """Return help text for this flag."""
        return f"Enable {self.feature_name}"
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply this flag's configuration to an agent config.
        
        Args:
            config: The agent configuration dictionary
            flag_value: The value of the flag
            
        Returns:
            Modified agent configuration
        """
        return config
    
    def post_process_result(self, result: Any, flag_value: Any) -> Any:
        """
        Post-process the agent result.
        
        Args:
            result: The agent's output
            flag_value: The value of the flag
            
        Returns:
            Processed result
        """
        return result

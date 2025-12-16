"""
Flow Display Handler for CLI.

Provides visual workflow tracking.
Usage: praisonai agents.yaml --flow-display
"""

from typing import Any, Dict, Tuple, List
from .base import FlagHandler


class FlowDisplayHandler(FlagHandler):
    """
    Handler for --flow-display flag.
    
    Enables visual workflow tracking for multi-agent executions.
    
    Example:
        praisonai agents.yaml --flow-display
        praisonai "Complex task" --flow-display
    """
    
    @property
    def feature_name(self) -> str:
        return "flow_display"
    
    @property
    def flag_name(self) -> str:
        return "flow-display"
    
    @property
    def flag_help(self) -> str:
        return "Enable visual workflow tracking"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if FlowDisplay is available."""
        try:
            import importlib.util
            if importlib.util.find_spec("praisonaiagents") is not None:
                return True, ""
            return False, "praisonaiagents not installed"
        except ImportError:
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
    
    def _get_flow_display(self):
        """Get FlowDisplay class lazily."""
        try:
            from praisonaiagents import FlowDisplay
            return FlowDisplay
        except ImportError:
            return None
    
    def create_flow_display(self, title: str = "Workflow") -> Any:
        """
        Create a FlowDisplay instance.
        
        Args:
            title: Title for the workflow display
            
        Returns:
            FlowDisplay instance or None
        """
        FlowDisplay = self._get_flow_display()
        if not FlowDisplay:
            self.print_status(
                "FlowDisplay requires praisonaiagents. Install with: pip install praisonaiagents",
                "error"
            )
            return None
        
        try:
            return FlowDisplay(title=title)
        except Exception as e:
            self.log(f"Failed to create FlowDisplay: {e}", "error")
            return None
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply flow display configuration.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Boolean indicating flow display
            
        Returns:
            Modified configuration
        """
        if flag_value:
            config['flow_display'] = True
        return config
    
    def display_workflow_start(self, workflow_name: str, agents: List[str] = None):
        """
        Display workflow start.
        
        Args:
            workflow_name: Name of the workflow
            agents: List of agent names
        """
        self.print_status(f"\n🚀 Starting Workflow: {workflow_name}", "info")
        self.print_status("=" * 50, "info")
        
        if agents:
            self.print_status("Agents:", "info")
            for i, agent in enumerate(agents, 1):
                self.print_status(f"  {i}. {agent}", "info")
        
        self.print_status("=" * 50, "info")
    
    def display_step(self, step_num: int, step_name: str, status: str = "running"):
        """
        Display a workflow step.
        
        Args:
            step_num: Step number
            step_name: Name of the step
            status: Step status (running, completed, failed)
        """
        icons = {
            'running': '⏳',
            'completed': '✅',
            'failed': '❌',
            'pending': '⬜'
        }
        icon = icons.get(status, '•')
        self.print_status(f"  {icon} Step {step_num}: {step_name}", "info")
    
    def display_workflow_end(self, success: bool = True, duration: float = None):
        """
        Display workflow end.
        
        Args:
            success: Whether workflow completed successfully
            duration: Workflow duration in seconds
        """
        self.print_status("=" * 50, "info")
        
        if success:
            msg = "✅ Workflow completed successfully"
        else:
            msg = "❌ Workflow failed"
        
        if duration:
            msg += f" ({duration:.2f}s)"
        
        self.print_status(msg, "success" if success else "error")
    
    def track_execution(self, func):
        """
        Decorator to track function execution in flow display.
        
        Args:
            func: Function to track
            
        Returns:
            Wrapped function
        """
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            
            self.display_step(1, func_name, "running")
            
            try:
                result = func(*args, **kwargs)
                self.display_step(1, func_name, "completed")
                return result
            except Exception:
                self.display_step(1, func_name, "failed")
                raise
        
        return wrapper
    
    def execute(self, workflow_name: str = None, **kwargs) -> Any:
        """
        Execute flow display setup.
        
        Args:
            workflow_name: Name of the workflow
            
        Returns:
            FlowDisplay instance or None
        """
        if workflow_name:
            self.display_workflow_start(workflow_name)
        
        return self.create_flow_display(workflow_name or "Workflow")

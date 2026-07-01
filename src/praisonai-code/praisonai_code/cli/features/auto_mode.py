"""
Auto Mode Handler for PraisonAI CLI.

Provides CLI flags and controls for auto-mode execution with progressive escalation.
Implements the "advanced-by-default, fast-by-default" strategy.

CLI Flags:
    --auto / --no-auto          Enable/disable auto mode (default: auto)
    --dry-run                   Show what would be done without executing
    --apply                     Apply changes (opposite of dry-run)
    --budget-steps N            Maximum steps budget
    --budget-time N             Maximum time budget in seconds
    --budget-tokens N           Maximum tokens budget
    --allow-tools TOOLS         Comma-separated list of allowed tools
    --deny-tools TOOLS          Comma-separated list of denied tools
    --checkpoint / --no-checkpoint  Enable/disable checkpoints
    --router MODE               Router mode: heuristic, trained, off
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class AutoModeLevel(Enum):
    """Auto mode levels for CLI."""
    OFF = "off"              # Manual mode - ask for everything
    SUGGEST = "suggest"      # Suggest actions, require approval
    AUTO = "auto"            # Auto-approve safe actions
    FULL_AUTO = "full_auto"  # Auto-approve everything (YOLO)


class RouterMode(Enum):
    """Router modes for model selection."""
    HEURISTIC = "heuristic"  # Fast keyword-based routing (default)
    TRAINED = "trained"      # ML-based routing (optional plugin)
    OFF = "off"              # No routing, use default model


@dataclass
class AutoModeConfig:
    """Configuration for auto mode execution."""
    # Mode settings
    mode: AutoModeLevel = AutoModeLevel.AUTO
    dry_run: bool = False
    
    # Budgets
    budget_steps: int = 50
    budget_time_seconds: int = 300
    budget_tokens: int = 100000
    budget_tool_calls: int = 100
    
    # Tool controls
    allow_tools: Set[str] = field(default_factory=set)
    deny_tools: Set[str] = field(default_factory=set)
    
    # Checkpoint settings
    enable_checkpoints: bool = True
    auto_checkpoint_on_write: bool = True
    
    # Router settings
    router_mode: RouterMode = RouterMode.HEURISTIC
    
    # Escalation settings
    auto_escalate: bool = True
    auto_deescalate: bool = True
    
    # Approval settings
    require_approval_for_writes: bool = True
    require_approval_for_commands: bool = True
    require_approval_for_deletes: bool = True
    
    # Display settings
    show_stage: bool = True
    show_budgets: bool = True
    show_checkpoints: bool = True
    verbose: bool = False
    
    @classmethod
    def from_cli_args(cls, **kwargs) -> "AutoModeConfig":
        """Create config from CLI arguments."""
        config = cls()
        
        # Mode
        if kwargs.get("auto") is False:
            config.mode = AutoModeLevel.OFF
        elif kwargs.get("full_auto"):
            config.mode = AutoModeLevel.FULL_AUTO
        elif kwargs.get("suggest"):
            config.mode = AutoModeLevel.SUGGEST
        
        # Dry run
        if kwargs.get("dry_run"):
            config.dry_run = True
        elif kwargs.get("apply"):
            config.dry_run = False
        
        # Budgets
        if kwargs.get("budget_steps"):
            config.budget_steps = kwargs["budget_steps"]
        if kwargs.get("budget_time"):
            config.budget_time_seconds = kwargs["budget_time"]
        if kwargs.get("budget_tokens"):
            config.budget_tokens = kwargs["budget_tokens"]
        
        # Tools
        if kwargs.get("allow_tools"):
            config.allow_tools = set(kwargs["allow_tools"].split(","))
        if kwargs.get("deny_tools"):
            config.deny_tools = set(kwargs["deny_tools"].split(","))
        
        # Checkpoints
        if kwargs.get("checkpoint") is False:
            config.enable_checkpoints = False
        elif kwargs.get("no_checkpoint"):
            config.enable_checkpoints = False
        
        # Router
        if kwargs.get("router"):
            try:
                config.router_mode = RouterMode(kwargs["router"])
            except ValueError:
                logger.warning(f"Unknown router mode: {kwargs['router']}")
        
        # Verbose
        config.verbose = kwargs.get("verbose", False)
        
        return config


@dataclass
class AutoModeState:
    """Runtime state for auto mode execution."""
    # Current execution
    current_stage: int = 0
    steps_taken: int = 0
    tokens_used: int = 0
    tool_calls: int = 0
    time_elapsed: float = 0.0
    
    # Checkpoints
    checkpoint_ids: List[str] = field(default_factory=list)
    files_modified: Set[str] = field(default_factory=set)
    
    # Approvals
    pending_approvals: List[Dict[str, Any]] = field(default_factory=list)
    approved_actions: int = 0
    denied_actions: int = 0
    
    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def is_within_budget(self, config: AutoModeConfig) -> bool:
        """Check if execution is within budget."""
        if self.steps_taken >= config.budget_steps:
            return False
        if self.time_elapsed >= config.budget_time_seconds:
            return False
        if self.tokens_used >= config.budget_tokens:
            return False
        if self.tool_calls >= config.budget_tool_calls:
            return False
        return True
    
    def get_budget_status(self, config: AutoModeConfig) -> Dict[str, Any]:
        """Get budget utilization status."""
        return {
            "steps": {
                "used": self.steps_taken,
                "limit": config.budget_steps,
                "percent": (self.steps_taken / config.budget_steps * 100) if config.budget_steps > 0 else 0,
            },
            "time": {
                "used": self.time_elapsed,
                "limit": config.budget_time_seconds,
                "percent": (self.time_elapsed / config.budget_time_seconds * 100) if config.budget_time_seconds > 0 else 0,
            },
            "tokens": {
                "used": self.tokens_used,
                "limit": config.budget_tokens,
                "percent": (self.tokens_used / config.budget_tokens * 100) if config.budget_tokens > 0 else 0,
            },
            "tool_calls": {
                "used": self.tool_calls,
                "limit": config.budget_tool_calls,
                "percent": (self.tool_calls / config.budget_tool_calls * 100) if config.budget_tool_calls > 0 else 0,
            },
        }


class AutoModeHandler:
    """
    Handler for auto mode CLI integration.
    
    Provides:
    - CLI flag parsing
    - Escalation pipeline integration
    - Budget tracking
    - Checkpoint management
    - Status display
    
    Example:
        handler = AutoModeHandler()
        config = handler.parse_args(auto=True, budget_steps=20)
        
        # Execute with auto mode
        result = await handler.execute(prompt, config)
    """
    
    def __init__(
        self,
        verbose: bool = False,
        on_stage_change: Optional[Callable[[int, int], None]] = None,
        on_checkpoint: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the handler.
        
        Args:
            verbose: Enable verbose output
            on_stage_change: Callback for stage transitions
            on_checkpoint: Callback for checkpoint creation
        """
        self.verbose = verbose
        self.on_stage_change = on_stage_change
        self.on_checkpoint = on_checkpoint
        
        self._config: Optional[AutoModeConfig] = None
        self._state: Optional[AutoModeState] = None
        self._pipeline = None
        self._checkpoint_service = None
    
    @property
    def feature_name(self) -> str:
        return "auto_mode"
    
    def parse_args(self, **kwargs) -> AutoModeConfig:
        """
        Parse CLI arguments into config.
        
        Args:
            **kwargs: CLI arguments
            
        Returns:
            AutoModeConfig
        """
        self._config = AutoModeConfig.from_cli_args(**kwargs)
        self._state = AutoModeState()
        return self._config
    
    def get_config(self) -> Optional[AutoModeConfig]:
        """Get current configuration."""
        return self._config
    
    def get_state(self) -> Optional[AutoModeState]:
        """Get current state."""
        return self._state
    
    async def execute(
        self,
        prompt: str,
        agent: Optional[Any] = None,
        tools: Optional[List[Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute prompt with auto mode.
        
        Args:
            prompt: User prompt
            agent: Agent instance
            tools: Available tools
            context: Execution context
            
        Returns:
            Execution result
        """
        if not self._config:
            self._config = AutoModeConfig()
        if not self._state:
            self._state = AutoModeState()
        
        import time
        start_time = time.time()
        
        # Filter tools based on config
        filtered_tools = self._filter_tools(tools or [])
        
        # Initialize escalation pipeline
        try:
            from praisonaiagents.escalation import EscalationPipeline, EscalationConfig
            
            escalation_config = EscalationConfig(
                max_steps=self._config.budget_steps,
                max_time_seconds=self._config.budget_time_seconds,
                max_tokens=self._config.budget_tokens,
                auto_escalate=self._config.auto_escalate,
                auto_deescalate=self._config.auto_deescalate,
                enable_checkpoints=self._config.enable_checkpoints,
                require_approval_for_writes=self._config.require_approval_for_writes,
            )
            
            self._pipeline = EscalationPipeline(
                config=escalation_config,
                agent=agent,
                tools=filtered_tools,
                checkpoint_service=self._checkpoint_service,
                on_stage_change=self._handle_stage_change,
            )
            
            # Execute
            result = await self._pipeline.execute(prompt, context)
            
            # Update state
            self._state.steps_taken = result.steps_taken
            self._state.tokens_used = result.tokens_used
            self._state.tool_calls = result.tool_calls
            self._state.time_elapsed = time.time() - start_time
            self._state.current_stage = result.final_stage.value
            
            if result.checkpoint_id:
                self._state.checkpoint_ids.append(result.checkpoint_id)
            
            self._state.files_modified.update(result.files_modified)
            self._state.errors.extend(result.errors)
            self._state.warnings.extend(result.warnings)
            
            return {
                "success": result.success,
                "response": result.response,
                "stage": result.final_stage.name,
                "escalations": result.escalations,
                "state": self._state,
            }
            
        except ImportError:
            # Fallback if escalation module not available
            logger.warning("Escalation module not available, using basic execution")
            
            if agent and hasattr(agent, 'chat'):
                response = agent.chat(prompt)
                self._state.time_elapsed = time.time() - start_time
                
                return {
                    "success": True,
                    "response": response,
                    "stage": "DIRECT",
                    "escalations": 0,
                    "state": self._state,
                }
            
            return {
                "success": False,
                "response": "No agent available",
                "stage": "DIRECT",
                "escalations": 0,
                "state": self._state,
            }
    
    def _filter_tools(self, tools: List[Any]) -> List[Any]:
        """Filter tools based on allow/deny lists."""
        if not self._config:
            return tools
        
        filtered = []
        for tool in tools:
            tool_name = getattr(tool, '__name__', str(tool)).lower()
            
            # Check deny list first
            if self._config.deny_tools:
                if any(d.lower() in tool_name for d in self._config.deny_tools):
                    continue
            
            # Check allow list
            if self._config.allow_tools:
                if not any(a.lower() in tool_name for a in self._config.allow_tools):
                    continue
            
            filtered.append(tool)
        
        return filtered
    
    def _handle_stage_change(self, old_stage, new_stage):
        """Handle stage change event."""
        if self._state:
            self._state.current_stage = new_stage.value
        
        if self.on_stage_change:
            self.on_stage_change(old_stage.value, new_stage.value)
        
        if self.verbose:
            self._display_stage_change(old_stage, new_stage)
    
    def _display_stage_change(self, old_stage, new_stage):
        """Display stage change to user."""
        try:
            from rich import print as rprint
            
            direction = "⬆️" if new_stage > old_stage else "⬇️"
            rprint(f"[cyan]{direction} Stage: {old_stage.name} → {new_stage.name}[/cyan]")
        except ImportError:
            print(f"Stage: {old_stage.name} -> {new_stage.name}")
    
    def display_status(self):
        """Display current status."""
        if not self._config or not self._state:
            return
        
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            
            console = Console()
            
            # Budget table
            budget = self._state.get_budget_status(self._config)
            
            table = Table(title="Auto Mode Status")
            table.add_column("Metric", style="cyan")
            table.add_column("Used", style="green")
            table.add_column("Limit", style="yellow")
            table.add_column("Usage", style="magenta")
            
            for name, data in budget.items():
                table.add_row(
                    name.replace("_", " ").title(),
                    str(data["used"]),
                    str(data["limit"]),
                    f"{data['percent']:.1f}%"
                )
            
            console.print(table)
            
            # Stage info
            stage_names = ["DIRECT", "HEURISTIC", "PLANNED", "AUTONOMOUS"]
            current = stage_names[self._state.current_stage] if self._state.current_stage < len(stage_names) else "UNKNOWN"
            console.print(f"\n[bold]Current Stage:[/bold] {current}")
            
            # Checkpoints
            if self._state.checkpoint_ids:
                console.print(f"[bold]Checkpoints:[/bold] {len(self._state.checkpoint_ids)}")
            
            # Files modified
            if self._state.files_modified:
                console.print(f"[bold]Files Modified:[/bold] {len(self._state.files_modified)}")
            
        except ImportError:
            # Fallback to basic output
            print(f"Steps: {self._state.steps_taken}/{self._config.budget_steps}")
            print(f"Time: {self._state.time_elapsed:.1f}s/{self._config.budget_time_seconds}s")
    
    def get_cli_options(self) -> List[Dict[str, Any]]:
        """
        Get CLI option definitions for integration.
        
        Returns:
            List of option definitions
        """
        return [
            {
                "name": "--auto/--no-auto",
                "default": True,
                "help": "Enable/disable auto mode",
            },
            {
                "name": "--dry-run",
                "is_flag": True,
                "help": "Show what would be done without executing",
            },
            {
                "name": "--apply",
                "is_flag": True,
                "help": "Apply changes (opposite of dry-run)",
            },
            {
                "name": "--budget-steps",
                "type": int,
                "default": 50,
                "help": "Maximum steps budget",
            },
            {
                "name": "--budget-time",
                "type": int,
                "default": 300,
                "help": "Maximum time budget in seconds",
            },
            {
                "name": "--budget-tokens",
                "type": int,
                "default": 100000,
                "help": "Maximum tokens budget",
            },
            {
                "name": "--allow-tools",
                "type": str,
                "help": "Comma-separated list of allowed tools",
            },
            {
                "name": "--deny-tools",
                "type": str,
                "help": "Comma-separated list of denied tools",
            },
            {
                "name": "--checkpoint/--no-checkpoint",
                "default": True,
                "help": "Enable/disable checkpoints",
            },
            {
                "name": "--router",
                "type": str,
                "default": "heuristic",
                "help": "Router mode: heuristic, trained, off",
            },
        ]


# Convenience function for quick auto mode execution
async def auto_execute(
    prompt: str,
    agent: Optional[Any] = None,
    budget_steps: int = 50,
    budget_time: int = 300,
    dry_run: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Quick auto mode execution.
    
    Args:
        prompt: User prompt
        agent: Agent instance
        budget_steps: Max steps
        budget_time: Max time in seconds
        dry_run: Dry run mode
        verbose: Verbose output
        
    Returns:
        Execution result
    """
    handler = AutoModeHandler(verbose=verbose)
    handler.parse_args(
        budget_steps=budget_steps,
        budget_time=budget_time,
        dry_run=dry_run,
    )
    
    return await handler.execute(prompt, agent=agent)

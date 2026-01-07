"""
Context Management CLI Feature for PraisonAI.

Provides CLI commands and integration for context budgeting,
optimization, and monitoring.
"""

import os
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass


@dataclass
class ContextManagerConfig:
    """Configuration for context management."""
    # Auto-compaction
    auto_compact: bool = True
    compact_threshold: float = 0.8
    strategy: str = "smart"
    
    # Output reserve
    output_reserve: int = 8000
    
    # Monitoring
    monitor_enabled: bool = False
    monitor_path: str = "./context.txt"
    monitor_format: Literal["human", "json"] = "human"
    monitor_frequency: Literal["turn", "tool_call", "manual", "overflow"] = "turn"
    redact_sensitive: bool = True
    
    @classmethod
    def from_env(cls) -> "ContextManagerConfig":
        """Load config from environment variables."""
        return cls(
            auto_compact=os.getenv("PRAISONAI_CONTEXT_AUTO_COMPACT", "true").lower() == "true",
            compact_threshold=float(os.getenv("PRAISONAI_CONTEXT_THRESHOLD", "0.8")),
            strategy=os.getenv("PRAISONAI_CONTEXT_STRATEGY", "smart"),
            output_reserve=int(os.getenv("PRAISONAI_CONTEXT_OUTPUT_RESERVE", "8000")),
            monitor_enabled=os.getenv("PRAISONAI_CONTEXT_MONITOR", "false").lower() == "true",
            monitor_path=os.getenv("PRAISONAI_CONTEXT_MONITOR_PATH", "./context.txt"),
            monitor_format=os.getenv("PRAISONAI_CONTEXT_MONITOR_FORMAT", "human"),
            monitor_frequency=os.getenv("PRAISONAI_CONTEXT_MONITOR_FREQUENCY", "turn"),
            redact_sensitive=os.getenv("PRAISONAI_CONTEXT_REDACT", "true").lower() == "true",
        )
    
    def merge_cli_args(
        self,
        auto_compact: Optional[bool] = None,
        strategy: Optional[str] = None,
        threshold: Optional[float] = None,
        monitor: Optional[bool] = None,
        monitor_path: Optional[str] = None,
        monitor_format: Optional[str] = None,
        monitor_frequency: Optional[str] = None,
        redact: Optional[bool] = None,
        output_reserve: Optional[int] = None,
    ) -> "ContextManagerConfig":
        """Merge CLI arguments (highest precedence)."""
        return ContextManagerConfig(
            auto_compact=auto_compact if auto_compact is not None else self.auto_compact,
            compact_threshold=threshold if threshold is not None else self.compact_threshold,
            strategy=strategy if strategy is not None else self.strategy,
            output_reserve=output_reserve if output_reserve is not None else self.output_reserve,
            monitor_enabled=monitor if monitor is not None else self.monitor_enabled,
            monitor_path=monitor_path if monitor_path is not None else self.monitor_path,
            monitor_format=monitor_format if monitor_format is not None else self.monitor_format,
            monitor_frequency=monitor_frequency if monitor_frequency is not None else self.monitor_frequency,
            redact_sensitive=redact if redact is not None else self.redact_sensitive,
        )


class ContextManagerHandler:
    """
    Handles context management for interactive CLI sessions.
    
    Integrates budgeting, composition, optimization, and monitoring.
    """
    
    def __init__(
        self,
        config: Optional[ContextManagerConfig] = None,
        model: str = "gpt-4o-mini",
        session_id: str = "",
        agent_name: str = "Assistant",
    ):
        """
        Initialize context manager.
        
        Args:
            config: Context management configuration
            model: Model name for budget calculation
            session_id: Session identifier
            agent_name: Agent name for monitoring
        """
        self.config = config or ContextManagerConfig.from_env()
        self.model = model
        self.session_id = session_id
        self.agent_name = agent_name
        
        # Lazy-loaded components
        self._budgeter = None
        self._composer = None
        self._monitor = None
        self._ledger = None
    
    @property
    def budgeter(self):
        """Get or create budgeter."""
        if self._budgeter is None:
            from praisonaiagents.context import ContextBudgeter
            self._budgeter = ContextBudgeter(
                model=self.model,
                output_reserve=self.config.output_reserve,
            )
        return self._budgeter
    
    @property
    def composer(self):
        """Get or create composer."""
        if self._composer is None:
            from praisonaiagents.context import ContextComposer
            self._composer = ContextComposer(
                budget=self.budgeter.allocate(),
            )
        return self._composer
    
    @property
    def monitor(self):
        """Get or create monitor."""
        if self._monitor is None:
            from praisonaiagents.context import ContextMonitor
            self._monitor = ContextMonitor(
                enabled=self.config.monitor_enabled,
                path=self.config.monitor_path,
                format=self.config.monitor_format,
                frequency=self.config.monitor_frequency,
                redact_sensitive=self.config.redact_sensitive,
            )
        return self._monitor
    
    @property
    def ledger(self):
        """Get or create ledger manager."""
        if self._ledger is None:
            from praisonaiagents.context import ContextLedgerManager
            self._ledger = ContextLedgerManager(agent_id=self.agent_name)
            self._ledger.set_budget(self.budgeter.allocate())
        return self._ledger
    
    def set_model(self, model: str) -> None:
        """Update model and reset budgeter."""
        self.model = model
        self._budgeter = None
        self._composer = None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current context statistics."""
        budget = self.budgeter.allocate()
        ledger_data = self.ledger.to_dict()
        
        return {
            "model": self.model,
            "model_limit": budget.model_limit,
            "output_reserve": budget.output_reserve,
            "usable": budget.usable,
            "total_tokens": self.ledger.get_total(),
            "utilization": self.ledger.get_utilization(),
            "turn_count": self.ledger.get_ledger().turn_count,
            "message_count": self.ledger.get_ledger().message_count,
            "segments": ledger_data.get("segments", {}),
            "warnings": self.ledger.get_warnings(),
            "auto_compact": self.config.auto_compact,
            "monitor_enabled": self.config.monitor_enabled,
        }
    
    def track_history(self, messages: List[Dict[str, Any]]) -> int:
        """Track conversation history tokens."""
        return self.ledger.track_history(messages)
    
    def track_system_prompt(self, content: str) -> int:
        """Track system prompt tokens."""
        return self.ledger.track_system_prompt(content)
    
    def track_tools(self, tools: List[Dict[str, Any]]) -> int:
        """Track tool schema tokens."""
        return self.ledger.track_tools(tools)
    
    def check_overflow(self) -> bool:
        """Check if context is approaching limit."""
        return self.budgeter.check_overflow(
            self.ledger.get_total(),
            threshold=self.config.compact_threshold,
        )
    
    def should_auto_compact(self) -> bool:
        """Check if auto-compaction should trigger."""
        return self.config.auto_compact and self.check_overflow()
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        strategy: Optional[str] = None,
    ) -> tuple:
        """
        Optimize messages using configured strategy.
        
        Args:
            messages: Messages to optimize
            strategy: Override strategy
            
        Returns:
            Tuple of (optimized_messages, result)
        """
        from praisonaiagents.context import get_optimizer, OptimizerStrategy
        
        strategy_name = strategy or self.config.strategy
        try:
            strategy_enum = OptimizerStrategy(strategy_name)
        except ValueError:
            strategy_enum = OptimizerStrategy.SMART
        
        optimizer = get_optimizer(strategy_enum)
        target = int(self.budgeter.usable * self.config.compact_threshold)
        
        return optimizer.optimize(messages, target, self.ledger.get_ledger())
    
    def write_snapshot(
        self,
        messages: List[Dict[str, Any]],
        trigger: str = "manual",
    ) -> Optional[str]:
        """
        Write context snapshot to disk.
        
        Args:
            messages: Current messages
            trigger: What triggered the snapshot
            
        Returns:
            Path to written file, or None
        """
        return self.monitor.snapshot(
            ledger=self.ledger.get_ledger(),
            budget=self.budgeter.allocate(),
            messages=messages,
            session_id=self.session_id,
            agent_name=self.agent_name,
            model_name=self.model,
            trigger=trigger,
        )
    
    def enable_monitor(self) -> None:
        """Enable context monitoring."""
        self.config.monitor_enabled = True
        self.monitor.enable()
    
    def disable_monitor(self) -> None:
        """Disable context monitoring."""
        self.config.monitor_enabled = False
        self.monitor.disable()
    
    def set_monitor_path(self, path: str) -> None:
        """Set monitor output path."""
        self.config.monitor_path = path
        self.monitor.set_path(path)
    
    def set_monitor_format(self, format: str) -> None:
        """Set monitor output format."""
        self.config.monitor_format = format
        self.monitor.set_format(format)
    
    def set_monitor_frequency(self, frequency: str) -> None:
        """Set monitor update frequency."""
        self.config.monitor_frequency = frequency
        self.monitor.set_frequency(frequency)


def handle_context_command(
    console,
    args: str,
    session_state: Dict[str, Any],
    context_manager: Optional[ContextManagerHandler] = None,
) -> None:
    """
    Handle /context command and subcommands.
    
    Usage:
        /context              - Show context stats
        /context show         - Show summary + budgets
        /context stats        - Token ledger table
        /context budget       - Budget allocation details
        /context dump         - Write snapshot now
        /context on           - Enable monitoring
        /context off          - Disable monitoring
        /context path <path>  - Set snapshot path
        /context format <fmt> - Set format (human/json)
        /context frequency <f>- Set frequency
        /context compact      - Trigger optimization
    """
    args = args.strip().lower() if args else ""
    parts = args.split(maxsplit=1)
    subcommand = parts[0] if parts else ""
    subargs = parts[1] if len(parts) > 1 else ""
    
    # Get or create context manager
    if context_manager is None:
        context_manager = session_state.get("context_manager")
        if context_manager is None:
            context_manager = ContextManagerHandler(
                model=session_state.get("current_model", "gpt-4o-mini"),
                session_id=session_state.get("session_id", ""),
            )
            session_state["context_manager"] = context_manager
    
    # Update history tracking
    history = session_state.get("conversation_history", [])
    context_manager.track_history(history)
    
    if subcommand in ("", "show"):
        _show_context_summary(console, context_manager)
    elif subcommand == "stats":
        _show_context_stats(console, context_manager)
    elif subcommand == "budget":
        _show_budget_details(console, context_manager)
    elif subcommand == "dump":
        _dump_context(console, context_manager, history)
    elif subcommand == "on":
        context_manager.enable_monitor()
        console.print("[green]✓ Context monitoring enabled[/green]")
        console.print(f"[dim]Output: {context_manager.config.monitor_path}[/dim]")
    elif subcommand == "off":
        context_manager.disable_monitor()
        console.print("[yellow]Context monitoring disabled[/yellow]")
    elif subcommand == "path":
        if subargs:
            context_manager.set_monitor_path(subargs)
            console.print(f"[green]✓ Monitor path set to: {subargs}[/green]")
        else:
            console.print(f"[cyan]Current path: {context_manager.config.monitor_path}[/cyan]")
    elif subcommand == "format":
        if subargs in ("human", "json"):
            context_manager.set_monitor_format(subargs)
            console.print(f"[green]✓ Monitor format set to: {subargs}[/green]")
        else:
            console.print("[yellow]Format must be 'human' or 'json'[/yellow]")
    elif subcommand == "frequency":
        valid = ("turn", "tool_call", "manual", "overflow")
        if subargs in valid:
            context_manager.set_monitor_frequency(subargs)
            console.print(f"[green]✓ Monitor frequency set to: {subargs}[/green]")
        else:
            console.print(f"[yellow]Frequency must be one of: {', '.join(valid)}[/yellow]")
    elif subcommand == "compact":
        _compact_context(console, context_manager, session_state)
    else:
        console.print("[yellow]Unknown subcommand. Use: show, stats, budget, dump, on, off, path, format, frequency, compact[/yellow]")


def _show_context_summary(console, manager: ContextManagerHandler) -> None:
    """Show context summary."""
    stats = manager.get_stats()
    
    console.print("\n[bold cyan]Context Summary[/bold cyan]")
    console.print(f"  Model:          {stats['model']}")
    console.print(f"  Model Limit:    {stats['model_limit']:,} tokens")
    console.print(f"  Output Reserve: {stats['output_reserve']:,} tokens")
    console.print(f"  Usable Budget:  {stats['usable']:,} tokens")
    console.print(f"  Current Usage:  {stats['total_tokens']:,} tokens ({stats['utilization']*100:.1f}%)")
    console.print(f"  Turns:          {stats['turn_count']}")
    console.print(f"  Messages:       {stats['message_count']}")
    console.print(f"  Auto-Compact:   {'enabled' if stats['auto_compact'] else 'disabled'}")
    console.print(f"  Monitoring:     {'enabled' if stats['monitor_enabled'] else 'disabled'}")
    
    if stats['warnings']:
        console.print("\n[yellow]Warnings:[/yellow]")
        for warning in stats['warnings']:
            console.print(f"  ⚠ {warning}")
    console.print("")


def _show_context_stats(console, manager: ContextManagerHandler) -> None:
    """Show detailed token stats."""
    stats = manager.get_stats()
    segments = stats.get("segments", {})
    
    console.print("\n[bold cyan]Token Ledger[/bold cyan]")
    console.print(f"{'Segment':<20} {'Tokens':>10} {'Budget':>10} {'Used':>8}")
    console.print("-" * 50)
    
    for name, data in segments.items():
        tokens = data.get("tokens", 0)
        budget = data.get("budget", 0)
        util = data.get("utilization", 0) * 100
        console.print(f"{name:<20} {tokens:>10,} {budget:>10,} {util:>7.1f}%")
    
    console.print("-" * 50)
    console.print(f"{'TOTAL':<20} {stats['total_tokens']:>10,} {stats['usable']:>10,} {stats['utilization']*100:>7.1f}%")
    console.print("")


def _show_budget_details(console, manager: ContextManagerHandler) -> None:
    """Show budget allocation details."""
    budget = manager.budgeter.allocate()
    
    console.print("\n[bold cyan]Budget Allocation[/bold cyan]")
    console.print(f"  Model Limit:     {budget.model_limit:,}")
    console.print(f"  Output Reserve:  {budget.output_reserve:,}")
    console.print(f"  Usable:          {budget.usable:,}")
    console.print("")
    console.print("  Segment Budgets:")
    console.print(f"    System Prompt: {budget.system_prompt:,}")
    console.print(f"    Rules:         {budget.rules:,}")
    console.print(f"    Skills:        {budget.skills:,}")
    console.print(f"    Memory:        {budget.memory:,}")
    console.print(f"    Tool Schemas:  {budget.tools_schema:,}")
    console.print(f"    Tool Outputs:  {budget.tool_outputs:,}")
    console.print(f"    History:       {budget.history_budget:,}")
    console.print(f"    Buffer:        {budget.buffer:,}")
    console.print("")


def _dump_context(console, manager: ContextManagerHandler, messages: List[Dict[str, Any]]) -> None:
    """Dump context snapshot to file."""
    # Temporarily enable if needed
    was_enabled = manager.config.monitor_enabled
    if not was_enabled:
        manager.enable_monitor()
    
    path = manager.write_snapshot(messages, trigger="manual")
    
    if not was_enabled:
        manager.disable_monitor()
    
    if path:
        console.print(f"[green]✓ Context snapshot written to: {path}[/green]")
    else:
        console.print("[yellow]Failed to write context snapshot[/yellow]")


def _compact_context(console, manager: ContextManagerHandler, session_state: Dict[str, Any]) -> None:
    """Trigger context compaction."""
    history = session_state.get("conversation_history", [])
    
    if len(history) < 4:
        console.print("[yellow]Not enough history to compact (need at least 4 messages)[/yellow]")
        return
    
    console.print("[dim]Optimizing context...[/dim]")
    
    optimized, result = manager.optimize(history)
    
    if result.tokens_saved > 0:
        session_state["conversation_history"] = optimized
        console.print(f"[green]✓ Optimized: {result.original_tokens:,} → {result.optimized_tokens:,} tokens[/green]")
        console.print(f"[dim]Saved {result.tokens_saved:,} tokens ({result.reduction_percent:.1f}%)[/dim]")
        console.print(f"[dim]Strategy: {result.strategy_used.value}[/dim]")
    else:
        console.print("[yellow]No optimization needed[/yellow]")


# CLI argument definitions for argparse integration
CONTEXT_CLI_ARGS = [
    {
        "flags": ["--context-auto-compact", "--no-context-auto-compact"],
        "dest": "context_auto_compact",
        "action": "store_true",
        "default": None,
        "help": "Enable/disable auto-compaction",
    },
    {
        "flags": ["--context-strategy"],
        "dest": "context_strategy",
        "choices": ["smart", "truncate", "sliding_window", "summarize", "prune_tools"],
        "default": None,
        "help": "Context optimization strategy",
    },
    {
        "flags": ["--context-threshold"],
        "dest": "context_threshold",
        "type": float,
        "default": None,
        "help": "Auto-compact threshold (0.0-1.0)",
    },
    {
        "flags": ["--context-monitor"],
        "dest": "context_monitor",
        "action": "store_true",
        "default": None,
        "help": "Enable context monitoring",
    },
    {
        "flags": ["--context-monitor-path"],
        "dest": "context_monitor_path",
        "default": None,
        "help": "Context monitor output path",
    },
    {
        "flags": ["--context-monitor-format"],
        "dest": "context_monitor_format",
        "choices": ["human", "json"],
        "default": None,
        "help": "Context monitor output format",
    },
    {
        "flags": ["--context-monitor-frequency"],
        "dest": "context_monitor_frequency",
        "choices": ["turn", "tool_call", "manual", "overflow"],
        "default": None,
        "help": "Context monitor update frequency",
    },
    {
        "flags": ["--context-redact", "--no-context-redact"],
        "dest": "context_redact",
        "action": "store_true",
        "default": None,
        "help": "Enable/disable sensitive data redaction",
    },
    {
        "flags": ["--context-output-reserve"],
        "dest": "context_output_reserve",
        "type": int,
        "default": None,
        "help": "Output token reserve",
    },
]

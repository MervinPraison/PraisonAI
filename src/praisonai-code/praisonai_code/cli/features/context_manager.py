"""
Context Management CLI Feature for PraisonAI.

Provides CLI commands and integration for context budgeting,
optimization, and monitoring.

This module uses the SDK ContextManager facade to ensure DRY
and CLI/SDK parity.
"""

from typing import Dict, List, Any, Optional


# Lazy import SDK components to avoid import overhead
def _get_sdk_manager():
    """Lazy import SDK ContextManager."""
    from praisonaiagents.context import ContextManager
    return ContextManager


def _get_sdk_config():
    """Lazy import SDK ManagerConfig."""
    from praisonaiagents.context import ManagerConfig
    return ManagerConfig


def _get_create_manager():
    """Lazy import create_context_manager factory."""
    from praisonaiagents.context import create_context_manager
    return create_context_manager


class ContextManagerHandler:
    """
    Handles context management for interactive CLI sessions.
    
    This is a thin wrapper around the SDK ContextManager facade.
    All core logic is in the SDK to ensure DRY and parity.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        session_id: str = "",
        agent_name: str = "Assistant",
        config_file: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize context manager handler.
        
        Args:
            model: Model name for budget calculation
            session_id: Session identifier
            agent_name: Agent name for monitoring
            config_file: Path to config.yaml
            cli_overrides: CLI argument overrides
        """
        # Use SDK factory with proper precedence
        create_manager = _get_create_manager()
        self._manager = create_manager(
            model=model,
            session_id=session_id,
            agent_name=agent_name,
            config_file=config_file,
            cli_overrides=cli_overrides,
        )
        
        # Expose model for compatibility
        self.model = model
        self.session_id = session_id
        self.agent_name = agent_name
    
    @property
    def config(self):
        """Get SDK config for compatibility."""
        return self._manager.config
    
    def set_model(self, model: str) -> None:
        """Update model and reset manager."""
        self.model = model
        create_manager = _get_create_manager()
        self._manager = create_manager(
            model=model,
            session_id=self.session_id,
            agent_name=self.agent_name,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current context statistics."""
        stats = self._manager.get_stats()
        # Add CLI-specific fields for compatibility
        stats["auto_compact"] = self._manager.config.auto_compact
        stats["monitor_enabled"] = self._manager.config.monitor_enabled
        return stats
    
    def track_history(self, messages: List[Dict[str, Any]]) -> int:
        """Track conversation history tokens."""
        return self._manager._ledger.track_history(messages)
    
    def track_system_prompt(self, content: str) -> int:
        """Track system prompt tokens."""
        return self._manager._ledger.track_system_prompt(content)
    
    def track_tools(self, tools: List[Dict[str, Any]]) -> int:
        """Track tool schema tokens."""
        return self._manager._ledger.track_tools(tools)
    
    def check_overflow(self) -> bool:
        """Check if context is approaching limit."""
        return self._manager._ledger.get_utilization() >= self._manager.config.compact_threshold
    
    def should_auto_compact(self) -> bool:
        """Check if auto-compaction should trigger."""
        return self._manager.config.auto_compact and self.check_overflow()
    
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
        
        strategy_name = strategy or self._manager.config.strategy.value
        try:
            strategy_enum = OptimizerStrategy(strategy_name)
        except ValueError:
            strategy_enum = OptimizerStrategy.SMART
        
        optimizer = get_optimizer(strategy_enum)
        target = int(self._manager._budget.usable * self._manager.config.compact_threshold)
        
        return optimizer.optimize(messages, target, self._manager._ledger.get_ledger())
    
    def process(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str = "",
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Process messages through context pipeline.
        
        Uses SDK ContextManager.process() for full pipeline.
        """
        return self._manager.process(
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
        )
    
    def write_snapshot(
        self,
        messages: List[Dict[str, Any]],
        trigger: str = "manual",
    ) -> Optional[str]:
        """Write context snapshot to disk."""
        return self._manager._monitor.snapshot(
            ledger=self._manager._ledger.get_ledger(),
            budget=self._manager._budget,
            messages=messages,
            session_id=self.session_id,
            agent_name=self.agent_name,
            model_name=self.model,
            trigger=trigger,
        )
    
    def enable_monitor(self) -> None:
        """Enable context monitoring."""
        self._manager.config.monitor_enabled = True
        self._manager._monitor.enable()
    
    def disable_monitor(self) -> None:
        """Disable context monitoring."""
        self._manager.config.monitor_enabled = False
        self._manager._monitor.disable()
    
    def set_monitor_path(self, path: str) -> None:
        """Set monitor output path."""
        self._manager.config.monitor_path = path
        self._manager._monitor.set_path(path)
    
    def set_monitor_format(self, format: str) -> None:
        """Set monitor output format."""
        self._manager.config.monitor_format = format
        self._manager._monitor.set_format(format)
    
    def set_monitor_frequency(self, frequency: str) -> None:
        """Set monitor update frequency."""
        self._manager.config.monitor_frequency = frequency
        self._manager._monitor.set_frequency(frequency)
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get optimization history."""
        return self._manager.get_history()
    
    def get_resolved_config(self) -> Dict[str, Any]:
        """Get resolved configuration with precedence info."""
        return self._manager.get_resolved_config()
    
    def capture_llm_boundary(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ):
        """Capture exact state at LLM call boundary."""
        return self._manager.capture_llm_boundary(messages, tools)
    
    # Compatibility properties for legacy code
    @property
    def budgeter(self):
        """Get budgeter for compatibility."""
        return self._manager._budgeter
    
    @property
    def ledger(self):
        """Get ledger for compatibility."""
        return self._manager._ledger
    
    @property
    def monitor(self):
        """Get monitor for compatibility."""
        return self._manager._monitor


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
        /context history      - Show optimization history
        /context config       - Show resolved configuration
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
    elif subcommand == "history":
        _show_optimization_history(console, context_manager)
    elif subcommand == "config":
        _show_resolved_config(console, context_manager)
    else:
        console.print("[yellow]Unknown subcommand. Use: show, stats, budget, dump, on, off, path, format, frequency, compact, history, config[/yellow]")


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


def _show_optimization_history(console, manager: ContextManagerHandler) -> None:
    """Show optimization history."""
    history = manager.get_history()
    
    if not history:
        console.print("[dim]No optimization events recorded yet.[/dim]")
        return
    
    console.print("\n[bold cyan]Optimization History[/bold cyan]")
    console.print(f"{'Time':<24} {'Event':<20} {'Tokens':>12} {'Saved':>10}")
    console.print("-" * 70)
    
    for event in history[-20:]:  # Show last 20 events
        timestamp = event.get("timestamp", "")[:19]  # Trim to datetime
        event_type = event.get("event_type", "unknown")
        tokens_before = event.get("tokens_before", 0)
        tokens_saved = event.get("tokens_saved", 0)
        
        tokens_str = f"{tokens_before:,}" if tokens_before else "-"
        saved_str = f"-{tokens_saved:,}" if tokens_saved else "-"
        
        console.print(f"{timestamp:<24} {event_type:<20} {tokens_str:>12} {saved_str:>10}")
    
    console.print("")
    console.print(f"[dim]Showing last {min(20, len(history))} of {len(history)} events[/dim]")


def _show_resolved_config(console, manager: ContextManagerHandler) -> None:
    """Show resolved configuration with precedence info."""
    resolved = manager.get_resolved_config()
    config = resolved.get("config", {})
    
    console.print("\n[bold cyan]Resolved Configuration[/bold cyan]")
    console.print(f"[dim]Precedence: {resolved.get('precedence', 'CLI > ENV > config.yaml > defaults')}[/dim]")
    console.print(f"[dim]Source: {config.get('source', 'defaults')}[/dim]")
    console.print("")
    
    console.print("[bold]Auto-Compaction:[/bold]")
    console.print(f"  auto_compact:           {config.get('auto_compact', True)}")
    console.print(f"  compact_threshold:      {config.get('compact_threshold', 0.8)}")
    console.print(f"  strategy:               {config.get('strategy', 'smart')}")
    console.print(f"  compression_min_gain:   {config.get('compression_min_gain_pct', 5.0)}%")
    console.print("")
    
    console.print("[bold]Budget:[/bold]")
    console.print(f"  output_reserve:         {config.get('output_reserve', 8000):,}")
    console.print(f"  default_tool_max:       {config.get('default_tool_output_max', 10000):,}")
    console.print("")
    
    console.print("[bold]Estimation:[/bold]")
    console.print(f"  estimation_mode:        {config.get('estimation_mode', 'heuristic')}")
    console.print(f"  log_mismatch:           {config.get('log_estimation_mismatch', False)}")
    console.print("")
    
    console.print("[bold]Monitoring:[/bold]")
    console.print(f"  monitor_enabled:        {config.get('monitor_enabled', False)}")
    console.print(f"  monitor_path:           {config.get('monitor_path', './context.txt')}")
    console.print(f"  monitor_format:         {config.get('monitor_format', 'human')}")
    console.print(f"  monitor_frequency:      {config.get('monitor_frequency', 'turn')}")
    console.print(f"  monitor_write_mode:     {config.get('monitor_write_mode', 'sync')}")
    console.print(f"  redact_sensitive:       {config.get('redact_sensitive', True)}")
    console.print("")
    
    # Show effective budget
    budget = resolved.get("effective_budget", {})
    if budget:
        console.print("[bold]Effective Budget:[/bold]")
        console.print(f"  model_limit:            {budget.get('model_limit', 0):,}")
        console.print(f"  usable:                 {budget.get('usable', 0):,}")
        console.print(f"  history_budget:         {budget.get('history_budget', 0):,}")
    console.print("")


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
    {
        "flags": ["--context-estimation-mode"],
        "dest": "context_estimation_mode",
        "choices": ["heuristic", "accurate", "validated"],
        "default": None,
        "help": "Token estimation mode",
    },
    {
        "flags": ["--context-log-mismatch"],
        "dest": "context_log_mismatch",
        "action": "store_true",
        "default": None,
        "help": "Log token estimation mismatches",
    },
    {
        "flags": ["--context-snapshot-timing"],
        "dest": "context_snapshot_timing",
        "choices": ["pre_optimization", "post_optimization", "both"],
        "default": None,
        "help": "When to capture context snapshots",
    },
    {
        "flags": ["--context-write-mode"],
        "dest": "context_write_mode",
        "choices": ["sync", "async"],
        "default": None,
        "help": "Monitor write mode (sync or async)",
    },
    {
        "flags": ["--context-show-config"],
        "dest": "context_show_config",
        "action": "store_true",
        "default": False,
        "help": "Show resolved context configuration and exit",
    },
]

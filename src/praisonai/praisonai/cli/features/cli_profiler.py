"""
CLI Profiler - Unified profiling for terminal-native CLI commands.

Provides --profile and --profile-deep flags for eligible commands:
- praisonai "prompt"
- praisonai chat
- praisonai chat "prompt"
- praisonai code
- praisonai code "prompt"
- praisonai run agents.yaml

NOT supported for:
- praisonai ui ... (browser-based)
- praisonai tui (Textual TUI)
- praisonai call (long-running server)
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import typer


# Commands that support profiling
PROFILING_ELIGIBLE_COMMANDS = frozenset({
    "chat",
    "code",
    "run",
    # Direct prompt is handled separately in main.py
})

# Commands that explicitly reject profiling
PROFILING_INELIGIBLE_COMMANDS = frozenset({
    "ui",
    "tui",
    "call",
    "realtime",
    "serve",
    "schedule",
    "acp",
    "mcp",
    "lsp",
})


@dataclass
class CLIProfileConfig:
    """Configuration for CLI profiling."""
    enabled: bool = False
    deep: bool = False
    output_format: str = "text"  # text or json
    save_path: Optional[str] = None
    
    @classmethod
    def from_flags(cls, profile: bool = False, profile_deep: bool = False) -> 'CLIProfileConfig':
        """Create config from CLI flags."""
        return cls(
            enabled=profile or profile_deep,
            deep=profile_deep,
        )


@dataclass
class CLIProfileResult:
    """Result from CLI profiling."""
    import_time_ms: float = 0.0
    agent_init_time_ms: float = 0.0
    execution_time_ms: float = 0.0
    total_time_ms: float = 0.0
    response: str = ""
    
    # Deep profiling data (only if deep=True)
    function_stats: Optional[list] = None
    call_graph: Optional[dict] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "import_time_ms": self.import_time_ms,
            "agent_init_time_ms": self.agent_init_time_ms,
            "execution_time_ms": self.execution_time_ms,
            "total_time_ms": self.total_time_ms,
        }
        if self.function_stats:
            result["function_stats"] = self.function_stats
        if self.call_graph:
            result["call_graph"] = self.call_graph
        return result


def print_profile_report(result: CLIProfileResult, config: CLIProfileConfig):
    """Print profiling report to console."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        console = Console()
    except ImportError:
        # Fallback to simple output
        print("\n─── Profiling ───")
        print(f"Import:      {result.import_time_ms:.1f}ms")
        print(f"Agent setup: {result.agent_init_time_ms:.1f}ms")
        print(f"Execution:   {result.execution_time_ms:.1f}ms")
        print(f"Total:       {result.total_time_ms:.1f}ms")
        return
    
    # Create timing table
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Phase", style="cyan")
    table.add_column("Time", style="green", justify="right")
    
    table.add_row("Import", f"{result.import_time_ms:.1f}ms")
    table.add_row("Agent setup", f"{result.agent_init_time_ms:.1f}ms")
    table.add_row("Execution", f"{result.execution_time_ms:.1f}ms")
    table.add_row("─" * 12, "─" * 10)
    table.add_row("Total", f"{result.total_time_ms:.1f}ms")
    
    console.print("\n")
    console.print(Panel(table, title="[bold]Profiling[/bold]", border_style="dim"))
    
    # Deep profiling output
    if config.deep and result.function_stats:
        console.print("\n[bold yellow]⚠️  Deep profiling enabled - overhead included in measurements[/bold yellow]")
        
        func_table = Table(title="Top Functions by Cumulative Time")
        func_table.add_column("Function", style="cyan")
        func_table.add_column("Calls", justify="right")
        func_table.add_column("Cumul (ms)", justify="right", style="green")
        
        for func in result.function_stats[:15]:
            name = func.get("name", "")[:40]
            calls = func.get("calls", 0)
            cumtime = func.get("cumulative_time_ms", 0)
            func_table.add_row(name, str(calls), f"{cumtime:.2f}")
        
        console.print(func_table)


def reject_profiling_for_command(command_name: str):
    """Raise error if profiling is attempted on ineligible command."""
    if command_name in PROFILING_INELIGIBLE_COMMANDS:
        raise typer.BadParameter(
            f"Profiling is not supported for '{command_name}' command.\n"
            f"Profiling is only available for terminal-native execution commands:\n"
            f"  praisonai \"prompt\" --profile\n"
            f"  praisonai chat \"prompt\" --profile\n"
            f"  praisonai code \"prompt\" --profile\n"
            f"  praisonai run agents.yaml --profile"
        )


class CLIProfiler:
    """
    CLI Profiler for wrapping command execution.
    
    Usage:
        profiler = CLIProfiler(config)
        with profiler.profile():
            # execution code
        profiler.print_report()
    """
    
    def __init__(self, config: CLIProfileConfig):
        self.config = config
        self._result = CLIProfileResult()
        self._start_time: float = 0.0
        self._cprofile = None
        
        # Phase timestamps
        self._import_start: float = 0.0
        self._import_end: float = 0.0
        self._init_start: float = 0.0
        self._init_end: float = 0.0
        self._exec_start: float = 0.0
        self._exec_end: float = 0.0
    
    def start(self):
        """Start profiling."""
        if not self.config.enabled:
            return
        
        self._start_time = time.perf_counter()
        
        if self.config.deep:
            import cProfile
            self._cprofile = cProfile.Profile()
            self._cprofile.enable()
    
    def stop(self):
        """Stop profiling and compute results."""
        if not self.config.enabled:
            return
        
        end_time = time.perf_counter()
        
        if self._cprofile:
            self._cprofile.disable()
            self._extract_cprofile_stats()
        
        self._result.total_time_ms = (end_time - self._start_time) * 1000
    
    def mark_import_start(self):
        """Mark start of import phase."""
        if self.config.enabled:
            self._import_start = time.perf_counter()
    
    def mark_import_end(self):
        """Mark end of import phase."""
        if self.config.enabled:
            self._import_end = time.perf_counter()
            self._result.import_time_ms = (self._import_end - self._import_start) * 1000
    
    def mark_init_start(self):
        """Mark start of agent initialization."""
        if self.config.enabled:
            self._init_start = time.perf_counter()
    
    def mark_init_end(self):
        """Mark end of agent initialization."""
        if self.config.enabled:
            self._init_end = time.perf_counter()
            self._result.agent_init_time_ms = (self._init_end - self._init_start) * 1000
    
    def mark_exec_start(self):
        """Mark start of execution."""
        if self.config.enabled:
            self._exec_start = time.perf_counter()
    
    def mark_exec_end(self):
        """Mark end of execution."""
        if self.config.enabled:
            self._exec_end = time.perf_counter()
            self._result.execution_time_ms = (self._exec_end - self._exec_start) * 1000
    
    def set_response(self, response: str):
        """Set the response for the profile result."""
        self._result.response = response
    
    def _extract_cprofile_stats(self):
        """Extract statistics from cProfile."""
        if not self._cprofile:
            return
        
        import pstats
        
        stats = pstats.Stats(self._cprofile)
        stats.sort_stats("cumulative")
        
        function_stats = []
        for (filename, line, name), (cc, nc, tt, ct, callers) in stats.stats.items():
            if len(function_stats) >= 100:
                break
            function_stats.append({
                "name": name,
                "file": filename,
                "line": line,
                "calls": nc,
                "total_time_ms": tt * 1000,
                "cumulative_time_ms": ct * 1000,
            })
        
        function_stats.sort(key=lambda x: x["cumulative_time_ms"], reverse=True)
        self._result.function_stats = function_stats[:30]
    
    def get_result(self) -> CLIProfileResult:
        """Get the profiling result."""
        return self._result
    
    def print_report(self):
        """Print the profiling report."""
        if self.config.enabled:
            print_profile_report(self._result, self.config)


def run_with_profiling(
    prompt: str,
    config: CLIProfileConfig,
    model: Optional[str] = None,
    verbose: bool = False,
    tools: Optional[str] = None,
) -> tuple:
    """
    Run a prompt with profiling enabled.
    
    Returns:
        Tuple of (response, CLIProfileResult)
    """
    profiler = CLIProfiler(config)
    profiler.start()
    
    # Import phase
    profiler.mark_import_start()
    try:
        from praisonaiagents import Agent
    except ImportError:
        raise ImportError("praisonaiagents not installed. Install with: pip install praisonaiagents")
    profiler.mark_import_end()
    
    # Agent initialization phase
    profiler.mark_init_start()
    agent_config = {
        "name": "ProfiledAgent",
        "role": "Assistant",
        "goal": "Complete the task",
        "verbose": verbose,
    }
    if model:
        agent_config["llm"] = model
    
    agent = Agent(**agent_config)
    profiler.mark_init_end()
    
    # Execution phase
    profiler.mark_exec_start()
    response = agent.start(prompt)
    profiler.mark_exec_end()
    
    profiler.stop()
    profiler.set_response(str(response) if response else "")
    
    return response, profiler.get_result()


# Export all
__all__ = [
    "CLIProfileConfig",
    "CLIProfileResult",
    "CLIProfiler",
    "PROFILING_ELIGIBLE_COMMANDS",
    "PROFILING_INELIGIBLE_COMMANDS",
    "print_profile_report",
    "reject_profiling_for_command",
    "run_with_profiling",
]

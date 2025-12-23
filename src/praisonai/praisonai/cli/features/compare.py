"""
CLI Compare Feature for PraisonAI.

Compares different CLI command modes without performance impact.
Only loaded when --compare flag is used.
"""

import time
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

COMPARE_MODES = {
    "basic": {},
    "tools": {"tools": "calculator,internet_search"},
    "research": {"research": True},
    "planning": {"planning": True},
    "memory": {"memory": True},
    "router": {"router": True},
    "web_search": {"web_search": True},
    "web_fetch": {"web_fetch": True},
    "query_rewrite": {"query_rewrite": True},
    "expand_prompt": {"expand_prompt": True},
}


def get_mode_config(mode_name: str, custom_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get configuration for a comparison mode.
    
    Args:
        mode_name: Name of the mode
        custom_args: Optional custom arguments to merge
        
    Returns:
        Configuration dictionary for the mode
    """
    config = COMPARE_MODES.get(mode_name, {}).copy()
    if custom_args:
        config.update(custom_args)
    return config


def list_available_modes() -> List[str]:
    """
    List all available comparison modes.
    
    Returns:
        List of mode names
    """
    return list(COMPARE_MODES.keys())


def parse_modes(modes_str: str) -> List[str]:
    """
    Parse comma-separated modes string.
    
    Args:
        modes_str: Comma-separated mode names
        
    Returns:
        List of mode names
    """
    if not modes_str or not modes_str.strip():
        return ["basic"]
    
    modes = [m.strip() for m in modes_str.split(",")]
    return [m for m in modes if m]


@dataclass
class ModeResult:
    """Result from running a single mode."""
    mode: str
    output: str
    execution_time_ms: float
    model_used: str
    tokens: Optional[Dict[str, int]] = None
    cost: Optional[float] = None
    tools_used: List[str] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mode": self.mode,
            "output_preview": self.output[:200] + "..." if len(self.output) > 200 else self.output,
            "execution_time_ms": self.execution_time_ms,
            "model_used": self.model_used,
            "tokens": self.tokens,
            "cost": self.cost,
            "tools_used": self.tools_used,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class CompareResult:
    """Result from comparing multiple modes."""
    query: str
    comparisons: List[ModeResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def get_summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        if not self.comparisons:
            return {}
        
        times = [(c.mode, c.execution_time_ms) for c in self.comparisons if c.error is None]
        if not times:
            return {"error": "All modes failed"}
        
        sorted_by_time = sorted(times, key=lambda x: x[1])
        
        summary = {
            "fastest": sorted_by_time[0][0],
            "slowest": sorted_by_time[-1][0],
            "fastest_time_ms": sorted_by_time[0][1],
            "slowest_time_ms": sorted_by_time[-1][1],
        }
        
        total_tokens = 0
        total_cost = 0.0
        for c in self.comparisons:
            if c.tokens:
                total_tokens += c.tokens.get("input", 0) + c.tokens.get("output", 0)
            if c.cost:
                total_cost += c.cost
        
        if total_tokens > 0:
            summary["total_tokens"] = total_tokens
        if total_cost > 0:
            summary["total_cost"] = total_cost
        
        return summary
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "comparisons": [c.to_dict() for c in self.comparisons],
            "summary": self.get_summary(),
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


def save_compare_result(result: CompareResult, path: str) -> bool:
    """
    Save comparison result to file.
    
    Args:
        result: CompareResult to save
        path: File path
        
    Returns:
        True if successful
    """
    try:
        from pathlib import Path
        
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(result.to_json())
        return True
    except Exception as e:
        logger.error(f"Failed to save comparison result: {e}")
        return False


def format_comparison_table(result: CompareResult, show_responses: bool = True) -> str:
    """
    Format comparison result as a table string with optional response display.
    
    Args:
        result: CompareResult to format
        show_responses: Whether to show actual responses from each mode
        
    Returns:
        Formatted table string
    """
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from io import StringIO
        
        console = Console(file=StringIO(), force_terminal=True)
        
        # Main comparison table
        table = Table(title=f"Comparison: {result.query[:50]}...")
        table.add_column("Mode", style="cyan")
        table.add_column("Time (ms)", style="green")
        table.add_column("Model", style="yellow")
        table.add_column("Tools", style="magenta")
        table.add_column("Status", style="bold")
        
        for c in result.comparisons:
            status = "✅" if c.error is None else f"❌ {c.error[:20]}"
            tools = ", ".join(c.tools_used) if c.tools_used else "-"
            table.add_row(
                c.mode,
                f"{c.execution_time_ms:.1f}",
                c.model_used,
                tools,
                status
            )
        
        summary = result.get_summary()
        if summary.get("fastest"):
            table.add_section()
            table.add_row(
                "Summary",
                f"Fastest: {summary['fastest']}",
                "",
                "",
                f"Δ {summary['slowest_time_ms'] - summary['fastest_time_ms']:.1f}ms"
            )
        
        console.print(table)
        
        # Show responses if enabled
        if show_responses:
            console.print("\n[bold cyan]📝 Responses:[/bold cyan]")
            for c in result.comparisons:
                if c.error is None:
                    # Truncate long responses
                    response_preview = c.output[:500] + "..." if len(c.output) > 500 else c.output
                    console.print(Panel(
                        response_preview,
                        title=f"[bold]{c.mode}[/bold] ({c.execution_time_ms:.0f}ms)",
                        border_style="cyan"
                    ))
                else:
                    console.print(Panel(
                        f"[red]Error: {c.error}[/red]",
                        title=f"[bold]{c.mode}[/bold]",
                        border_style="red"
                    ))
        
        return console.file.getvalue()
    except ImportError:
        lines = [f"Comparison: {result.query}"]
        lines.append("-" * 60)
        for c in result.comparisons:
            status = "OK" if c.error is None else f"ERROR: {c.error}"
            lines.append(f"{c.mode}: {c.execution_time_ms:.1f}ms - {status}")
            if show_responses and c.error is None:
                lines.append(f"  Response: {c.output[:200]}...")
        return "\n".join(lines)


class CompareHandler:
    """
    Handler for CLI compare feature.
    
    Compares different CLI command modes and generates comparison reports.
    """
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the compare handler.
        
        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
        self.results: List[ModeResult] = []
    
    def compare(
        self,
        query: str,
        modes: List[str],
        model: Optional[str] = None,
        **kwargs
    ) -> CompareResult:
        """
        Compare query execution across different modes.
        
        Args:
            query: The query to execute
            modes: List of mode names to compare
            model: Optional model override
            **kwargs: Additional arguments
            
        Returns:
            CompareResult with all comparisons
        """
        result = CompareResult(query=query)
        
        for mode in modes:
            if self.verbose:
                logger.info(f"Running mode: {mode}")
            
            try:
                mode_result = self._run_mode(query, mode, model=model, **kwargs)
                result.comparisons.append(mode_result)
            except Exception as e:
                logger.error(f"Error running mode {mode}: {e}")
                result.comparisons.append(ModeResult(
                    mode=mode,
                    output="",
                    execution_time_ms=0,
                    model_used=model or "unknown",
                    error=str(e)
                ))
        
        return result
    
    def _run_mode(
        self,
        query: str,
        mode: str,
        model: Optional[str] = None,
        **kwargs
    ) -> ModeResult:
        """
        Run a single mode and capture results.
        
        Args:
            query: The query to execute
            mode: Mode name
            model: Optional model override
            **kwargs: Additional arguments
            
        Returns:
            ModeResult with execution details
        """
        config = get_mode_config(mode, kwargs)
        
        if model:
            config["llm"] = model
        
        start_time = time.perf_counter()
        output = ""
        tokens = None
        cost = None
        tools_used = []
        error = None
        model_used = model or "gpt-4o-mini"
        
        try:
            from praisonaiagents import Agent
            
            agent_config = {
                "name": f"CompareAgent_{mode}",
                "role": "Assistant",
                "goal": "Complete the given task",
                "backstory": "You are a helpful AI assistant",
                "verbose": False,
            }
            
            if config.get("llm"):
                agent_config["llm"] = config["llm"]
                model_used = config["llm"]
            
            if config.get("tools"):
                tools_list = self._load_tools(config["tools"])
                if tools_list:
                    agent_config["tools"] = tools_list
            
            if config.get("planning"):
                agent_config["planning"] = True
            
            if config.get("memory"):
                agent_config["memory"] = True
            
            if config.get("web_search"):
                agent_config["web_search"] = True
            
            if config.get("web_fetch"):
                agent_config["web_fetch"] = True
            
            agent = Agent(**agent_config)
            result = agent.start(query)
            
            if hasattr(result, 'raw'):
                output = str(result.raw)
            else:
                output = str(result)
            
            if hasattr(agent, 'tools') and agent.tools:
                for tool in agent.tools:
                    if hasattr(tool, '__name__'):
                        tools_used.append(tool.__name__)
                    elif hasattr(tool, 'name'):
                        tools_used.append(tool.name)
            
        except Exception as e:
            error = str(e)
            logger.error(f"Mode {mode} failed: {e}")
        
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        
        return ModeResult(
            mode=mode,
            output=output,
            execution_time_ms=execution_time_ms,
            model_used=model_used,
            tokens=tokens,
            cost=cost,
            tools_used=tools_used,
            error=error
        )
    
    def _load_tools(self, tools_str: str) -> List:
        """
        Load tools from string specification.
        
        Args:
            tools_str: Comma-separated tool names
            
        Returns:
            List of tool functions
        """
        tools = []
        tool_names = [t.strip() for t in tools_str.split(",")]
        
        for name in tool_names:
            try:
                if name == "internet_search":
                    from praisonaiagents.tools import internet_search
                    tools.append(internet_search)
                elif name == "calculator":
                    tools.append(_calculator_tool)
            except ImportError:
                logger.warning(f"Could not load tool: {name}")
        
        return tools
    
    def print_result(self, result: CompareResult) -> None:
        """
        Print comparison result to console.
        
        Args:
            result: CompareResult to print
        """
        table_str = format_comparison_table(result)
        print(table_str)
    
    def execute(
        self,
        query: str,
        modes_str: str,
        model: Optional[str] = None,
        output_path: Optional[str] = None,
        **kwargs
    ) -> CompareResult:
        """
        Execute comparison from CLI arguments.
        
        Args:
            query: The query to execute
            modes_str: Comma-separated mode names
            model: Optional model override
            output_path: Optional path to save results
            **kwargs: Additional arguments
            
        Returns:
            CompareResult with all comparisons
        """
        modes = parse_modes(modes_str)
        
        if self.verbose:
            print(f"[bold cyan]Comparing modes: {', '.join(modes)}[/bold cyan]")
        
        result = self.compare(query, modes, model=model, **kwargs)
        
        self.print_result(result)
        
        if output_path:
            if save_compare_result(result, output_path):
                print(f"[green]Results saved to: {output_path}[/green]")
            else:
                print(f"[red]Failed to save results to: {output_path}[/red]")
        
        return result


def _calculator_tool(expression: str) -> str:
    """
    Evaluate a mathematical expression safely.
    
    Args:
        expression: Mathematical expression to evaluate (e.g., "2+2", "15*3", "100/4")
        
    Returns:
        The result of the calculation as a string
    """
    import ast
    import operator
    
    # Safe operators
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
        ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
    }
    
    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            return operators[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            return operators[type(node.op)](operand)
        else:
            raise ValueError(f"Unsupported operation: {type(node)}")
    
    try:
        tree = ast.parse(expression, mode='eval')
        result = _eval(tree.body)
        return str(result)
    except Exception as e:
        return f"Error evaluating '{expression}': {e}"

"""Session report generation for browser automation.

Generates detailed Rich-formatted reports showing step-by-step execution.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("praisonai.browser.report")


def generate_session_report(
    action_history: List[Dict[str, Any]],
    goal: str,
    success: bool,
    final_url: str = "",
    duration_seconds: float = 0,
    tech_flags: Optional[Dict[str, bool]] = None,
) -> None:
    """Generate and display a Rich-formatted session report.
    
    Args:
        action_history: List of step dicts from CDPBrowserAgent._action_history
        goal: Original automation goal
        success: Whether the task completed successfully
        final_url: Final page URL
        duration_seconds: Total session duration
        tech_flags: Dict of technologies used {cdp: bool, vision: bool, extension: bool}
    """
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from rich import box
    except ImportError:
        # Fallback: simple text output
        logger.info("Rich not installed - using simple output")
        _print_simple_report(action_history, goal, success)
        return
    
    console = Console()
    tech_flags = tech_flags or {}
    
    # Header panel
    status_icon = "✅" if success else "❌"
    status_text = "COMPLETED" if success else "FAILED"
    
    tech_badges = []
    if tech_flags.get("cdp", True):
        tech_badges.append("[cyan]🔌 CDP[/cyan]")
    if tech_flags.get("vision"):
        tech_badges.append("[yellow]👁️ Vision[/yellow]")
    if tech_flags.get("extension"):
        tech_badges.append("[green]🧩 Extension[/green]")
    
    header = f"""[bold]{status_icon} Session {status_text}[/bold]
    
[dim]Goal:[/dim] {goal[:80]}{'...' if len(goal) > 80 else ''}
[dim]Final URL:[/dim] {final_url[:60]}{'...' if len(final_url) > 60 else ''}
[dim]Duration:[/dim] {duration_seconds:.1f}s | [dim]Steps:[/dim] {len(action_history)} | [dim]Tech:[/dim] {' '.join(tech_badges) or 'CDP'}"""
    
    console.print(Panel(header, title="📋 Session Report", border_style="blue"))
    
    # Steps table
    table = Table(
        title="Step-by-Step Execution",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Action", style="bold", width=10)
    table.add_column("Target/Value", width=30, overflow="fold")
    table.add_column("Result", width=10, justify="center")
    table.add_column("Tech", width=12)
    table.add_column("Thought", width=35, overflow="fold")
    
    for i, step in enumerate(action_history):
        step_num = str(i + 1)
        action_type = step.get("action", "?")
        
        # Target/value
        target = step.get("selector", step.get("text", step.get("url", "")))
        if len(str(target)) > 28:
            target = str(target)[:28] + "..."
        
        # Result
        result_success = step.get("success", True)
        result = "[green]✓[/green]" if result_success else "[red]✗[/red]"
        
        # Tech used this step
        step_tech = []
        if step.get("vision_used"):
            step_tech.append("👁️")
        step_tech.append("🔌")  # CDP always used
        
        # Thought (truncated)
        thought = step.get("thought", "")
        if len(thought) > 33:
            thought = thought[:33] + "..."
        
        table.add_row(
            step_num,
            action_type,
            str(target),
            result,
            " ".join(step_tech),
            thought,
        )
    
    console.print(table)
    console.print()


def _print_simple_report(
    action_history: List[Dict[str, Any]],
    goal: str,
    success: bool,
) -> None:
    """Simple text-based report fallback."""
    print("\n" + "=" * 60)
    print(f"SESSION REPORT: {'SUCCESS' if success else 'FAILED'}")
    print("=" * 60)
    print(f"Goal: {goal}")
    print(f"Steps: {len(action_history)}")
    print("-" * 60)
    
    for i, step in enumerate(action_history):
        action = step.get("action", "?")
        target = step.get("selector", step.get("text", ""))[:30]
        result = "✓" if step.get("success", True) else "✗"
        print(f"  {i+1}. {action:10} | {target:30} | {result}")
    
    print("=" * 60 + "\n")

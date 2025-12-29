"""
Background Agents CLI Feature for PraisonAI.

Provides CLI commands for managing background agent tasks.

Commands:
- praisonai background list              # List background tasks
- praisonai background status <id>       # Get task status
- praisonai background cancel <id>       # Cancel a task
- praisonai background clear             # Clear completed tasks
"""

import asyncio
from typing import Optional, List


class BackgroundHandler:
    """
    Handler for background CLI commands.
    
    Provides functionality to:
    - List running and completed background tasks
    - Check task status
    - Cancel running tasks
    - Clear completed tasks
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._runner = None
    
    @property
    def feature_name(self) -> str:
        return "background"
    
    async def _get_runner(self):
        """Lazy load the background runner."""
        if self._runner is None:
            from praisonaiagents.background import BackgroundRunner
            self._runner = BackgroundRunner()
        return self._runner
    
    async def list_tasks(self, status: Optional[str] = None) -> List[dict]:
        """
        List all background tasks.
        
        Args:
            status: Optional status filter (pending, running, completed, failed)
            
        Returns:
            List of task dictionaries
        """
        runner = await self._get_runner()
        
        status_enum = None
        if status:
            from praisonaiagents.background import TaskStatus
            status_map = {
                "pending": TaskStatus.PENDING,
                "running": TaskStatus.RUNNING,
                "completed": TaskStatus.COMPLETED,
                "failed": TaskStatus.FAILED,
                "cancelled": TaskStatus.CANCELLED
            }
            status_enum = status_map.get(status.lower())
        
        tasks = runner.list_tasks(status=status_enum)
        
        self._print_tasks_table(tasks)
        return tasks
    
    def _print_tasks_table(self, tasks: List[dict]):
        """Print tasks in table format."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            if not tasks:
                console.print("[yellow]No background tasks[/yellow]")
                return
            
            table = Table(title="Background Tasks")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Progress", style="blue")
            table.add_column("Duration", style="magenta")
            
            for task in tasks:
                status = task.get("status", "unknown")
                status_color = {
                    "pending": "dim",
                    "running": "yellow",
                    "completed": "green",
                    "failed": "red",
                    "cancelled": "dim"
                }.get(status, "white")
                
                progress = f"{task.get('progress', 0) * 100:.0f}%"
                duration = task.get("duration_seconds")
                duration_str = f"{duration:.1f}s" if duration else "-"
                
                table.add_row(
                    task.get("id", "?"),
                    task.get("name", "unnamed"),
                    f"[{status_color}]{status}[/{status_color}]",
                    progress,
                    duration_str
                )
            
            console.print(table)
        except ImportError:
            print("Background Tasks:")
            for task in tasks:
                print(f"  {task.get('id')} - {task.get('name')} ({task.get('status')})")
    
    async def get_status(self, task_id: str) -> Optional[dict]:
        """
        Get status of a specific task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task dictionary or None
        """
        runner = await self._get_runner()
        task = runner.get_task(task_id)
        
        if task is None:
            self._print_error(f"Task not found: {task_id}")
            return None
        
        task_dict = task.to_dict()
        self._print_task_details(task_dict)
        return task_dict
    
    def _print_task_details(self, task: dict):
        """Print detailed task information."""
        try:
            from rich.console import Console
            from rich.panel import Panel
            
            console = Console()
            
            status = task.get("status", "unknown")
            status_color = {
                "pending": "dim",
                "running": "yellow",
                "completed": "green",
                "failed": "red",
                "cancelled": "dim"
            }.get(status, "white")
            
            content = f"""
[bold]ID:[/bold] {task.get('id')}
[bold]Name:[/bold] {task.get('name')}
[bold]Status:[/bold] [{status_color}]{status}[/{status_color}]
[bold]Progress:[/bold] {task.get('progress', 0) * 100:.0f}%
[bold]Created:[/bold] {task.get('created_at')}
[bold]Started:[/bold] {task.get('started_at') or '-'}
[bold]Completed:[/bold] {task.get('completed_at') or '-'}
[bold]Duration:[/bold] {task.get('duration_seconds', 0):.2f}s
"""
            if task.get("error"):
                content += f"[bold]Error:[/bold] [red]{task.get('error')}[/red]\n"
            
            if task.get("result"):
                result_str = str(task.get("result"))[:200]
                content += f"[bold]Result:[/bold] {result_str}\n"
            
            console.print(Panel(content.strip(), title=f"Task: {task.get('name')}"))
        except ImportError:
            print(f"Task: {task.get('name')}")
            print(f"  ID: {task.get('id')}")
            print(f"  Status: {task.get('status')}")
            print(f"  Progress: {task.get('progress', 0) * 100:.0f}%")
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            True if cancelled
        """
        runner = await self._get_runner()
        result = await runner.cancel_task(task_id)
        
        if result:
            self._print_success(f"Task cancelled: {task_id}")
        else:
            self._print_error(f"Could not cancel task: {task_id}")
        
        return result
    
    async def clear_completed(self) -> int:
        """
        Clear all completed tasks.
        
        Returns:
            Number of tasks cleared
        """
        runner = await self._get_runner()
        count = len([t for t in runner.tasks if t.is_completed])
        runner.clear_completed()
        
        self._print_success(f"Cleared {count} completed tasks")
        return count
    
    def _print_success(self, message: str):
        """Print success message."""
        try:
            from rich.console import Console
            Console().print(f"[green]✓[/green] {message}")
        except ImportError:
            print(f"✓ {message}")
    
    def _print_error(self, message: str):
        """Print error message."""
        try:
            from rich.console import Console
            Console().print(f"[red]✗[/red] {message}")
        except ImportError:
            print(f"✗ {message}")


def handle_background_command(args: List[str], verbose: bool = False):
    """
    Handle background CLI commands.
    
    Usage:
        praisonai background list [--status <status>] [--json] [--page N] [--page-size N]
        praisonai background status <task_id> [--json]
        praisonai background cancel <task_id> [--json]
        praisonai background clear [--all] [--older-than SEC] [--json]
        praisonai background submit --recipe <name> [--input JSON] [--session-id ID] [--timeout SEC] [--json]
    """
    import argparse
    import json
    
    parser = argparse.ArgumentParser(prog="praisonai background", description="Manage background tasks")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List background tasks")
    list_parser.add_argument("--status", choices=["pending", "running", "completed", "failed", "cancelled"], help="Filter by status")
    list_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    list_parser.add_argument("--page", type=int, default=1, help="Page number")
    list_parser.add_argument("--page-size", type=int, default=20, help="Tasks per page")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get task status")
    status_parser.add_argument("task_id", help="Task ID")
    status_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    
    # Cancel command
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a task")
    cancel_parser.add_argument("task_id", help="Task ID")
    cancel_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear completed tasks")
    clear_parser.add_argument("--all", action="store_true", help="Clear all tasks including running")
    clear_parser.add_argument("--older-than", type=int, help="Clear tasks older than N seconds")
    clear_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    
    # Submit command (NEW - for recipe background submission)
    submit_parser = subparsers.add_parser("submit", help="Submit a recipe as background task")
    submit_parser.add_argument("--recipe", required=True, dest="recipe_name", help="Recipe name to execute")
    submit_parser.add_argument("--input", "-i", dest="input_data", help="Input data as JSON string")
    submit_parser.add_argument("--config", "-c", help="Config overrides as JSON string")
    submit_parser.add_argument("--session-id", "-s", help="Session ID for conversation continuity")
    submit_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default: 300)")
    submit_parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    
    if not args:
        parser.print_help()
        return
    
    # Handle legacy help
    if args[0] in ["help", "--help", "-h"]:
        parser.print_help()
        return
    
    parsed = parser.parse_args(args)
    
    if not parsed.subcommand:
        parser.print_help()
        return
    
    handler = BackgroundHandler(verbose=verbose)
    
    try:
        if parsed.subcommand == "list":
            asyncio.run(handler.list_tasks(status=parsed.status))
        
        elif parsed.subcommand == "status":
            asyncio.run(handler.get_status(parsed.task_id))
        
        elif parsed.subcommand == "cancel":
            asyncio.run(handler.cancel_task(parsed.task_id))
        
        elif parsed.subcommand == "clear":
            asyncio.run(handler.clear_completed())
        
        elif parsed.subcommand == "submit":
            # Parse input and config
            input_data = None
            if parsed.input_data:
                try:
                    input_data = json.loads(parsed.input_data)
                except json.JSONDecodeError:
                    input_data = {"input": parsed.input_data}
            
            config = None
            if parsed.config:
                try:
                    config = json.loads(parsed.config)
                except json.JSONDecodeError:
                    print("Error: --config must be valid JSON")
                    return
            
            # Submit recipe as background task
            from praisonai.recipe.operations import run_background
            
            task = run_background(
                parsed.recipe_name,
                input=input_data,
                config=config,
                session_id=parsed.session_id,
                timeout_sec=parsed.timeout,
            )
            
            if parsed.output_json:
                print(json.dumps({
                    "ok": True,
                    "task_id": task.task_id,
                    "recipe": task.recipe_name,
                    "session_id": task.session_id,
                }))
            else:
                print(f"✓ Recipe '{parsed.recipe_name}' submitted to background")
                print(f"  Task ID: {task.task_id}")
                print(f"  Session: {task.session_id}")
                print(f"\nCheck status with: praisonai background status {task.task_id}")
    
    except Exception as e:
        if getattr(parsed, 'output_json', False):
            print(json.dumps({"ok": False, "error": str(e)}))
        else:
            print(f"✗ Error: {e}")

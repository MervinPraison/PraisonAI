"""
Background Agents CLI Feature for PraisonAI.

Provides CLI commands for managing background agent tasks.

Commands:
- praisonai background list              # List background tasks
- praisonai background status <id>       # Get task status
- praisonai background cancel <id>       # Cancel a task
- praisonai background clear             # Clear completed tasks
"""

import os
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
        praisonai background list [--status <status>]
        praisonai background status <task_id>
        praisonai background cancel <task_id>
        praisonai background clear
    """
    handler = BackgroundHandler(verbose=verbose)
    
    if not args:
        print("Usage: praisonai background <command> [options]")
        print("\nCommands:")
        print("  list [--status <status>]  List background tasks")
        print("  status <task_id>          Get task status")
        print("  cancel <task_id>          Cancel a task")
        print("  clear                     Clear completed tasks")
        return
    
    command = args[0]
    
    if command == "list":
        status = None
        if "--status" in args:
            idx = args.index("--status")
            if idx + 1 < len(args):
                status = args[idx + 1]
        
        asyncio.run(handler.list_tasks(status=status))
    
    elif command == "status":
        if len(args) < 2:
            print("Usage: praisonai background status <task_id>")
            return
        
        asyncio.run(handler.get_status(args[1]))
    
    elif command == "cancel":
        if len(args) < 2:
            print("Usage: praisonai background cancel <task_id>")
            return
        
        asyncio.run(handler.cancel_task(args[1]))
    
    elif command == "clear":
        asyncio.run(handler.clear_completed())
    
    elif command == "help" or command == "--help":
        print("Background CLI Commands:")
        print("\n  praisonai background list [--status <status>]")
        print("    List all background tasks")
        print("    Status: pending, running, completed, failed, cancelled")
        print("\n  praisonai background status <task_id>")
        print("    Get detailed status of a specific task")
        print("\n  praisonai background cancel <task_id>")
        print("    Cancel a running task")
        print("\n  praisonai background clear")
        print("    Clear all completed tasks from the list")
    
    else:
        print(f"Unknown command: {command}")
        print("Use 'praisonai background help' for available commands")

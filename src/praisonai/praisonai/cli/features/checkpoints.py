"""
Checkpoints CLI Feature for PraisonAI.

Provides CLI commands for managing file-level checkpoints.

Commands:
- praisonai checkpoint save <message>     # Save a checkpoint
- praisonai checkpoint restore <id>       # Restore to a checkpoint
- praisonai checkpoint list               # List all checkpoints
- praisonai checkpoint diff [from] [to]   # Show diff between checkpoints
- praisonai checkpoint delete             # Delete all checkpoints
"""

import os
import asyncio
from typing import Optional, List
from dataclasses import dataclass


class CheckpointsHandler:
    """
    Handler for checkpoints CLI commands.
    
    Provides functionality to:
    - Save checkpoints before file modifications
    - Restore workspace to previous checkpoints
    - View diffs between checkpoints
    - List and manage checkpoints
    """
    
    def __init__(self, workspace_dir: Optional[str] = None, verbose: bool = False):
        self.workspace_dir = workspace_dir or os.getcwd()
        self.verbose = verbose
        self._service = None
    
    @property
    def feature_name(self) -> str:
        return "checkpoints"
    
    async def _get_service(self):
        """Lazy load the checkpoint service."""
        if self._service is None:
            from praisonaiagents.checkpoints import CheckpointService
            self._service = CheckpointService(
                workspace_dir=self.workspace_dir
            )
            await self._service.initialize()
        return self._service
    
    async def save(self, message: str, allow_empty: bool = False) -> bool:
        """
        Save a checkpoint.
        
        Args:
            message: Checkpoint message
            allow_empty: Allow checkpoint even if no changes
            
        Returns:
            True if successful
        """
        service = await self._get_service()
        result = await service.save(message, allow_empty=allow_empty)
        
        if result.success:
            self._print_success(f"Checkpoint saved: {result.checkpoint.short_id}")
            self._print_info(f"Message: {result.checkpoint.message}")
            return True
        else:
            self._print_error(f"Failed to save checkpoint: {result.error}")
            return False
    
    async def restore(self, checkpoint_id: str) -> bool:
        """
        Restore to a checkpoint.
        
        Args:
            checkpoint_id: Checkpoint ID to restore
            
        Returns:
            True if successful
        """
        service = await self._get_service()
        result = await service.restore(checkpoint_id)
        
        if result.success:
            self._print_success(f"Restored to checkpoint: {result.checkpoint.short_id}")
            return True
        else:
            self._print_error(f"Failed to restore: {result.error}")
            return False
    
    async def list_checkpoints(self, limit: int = 20) -> List[dict]:
        """
        List all checkpoints.
        
        Args:
            limit: Maximum number to show
            
        Returns:
            List of checkpoint dictionaries
        """
        service = await self._get_service()
        checkpoints = await service.list_checkpoints(limit=limit)
        
        if not checkpoints:
            self._print_info("No checkpoints found")
            return []
        
        self._print_checkpoints_table(checkpoints)
        return [cp.to_dict() for cp in checkpoints]
    
    def _print_checkpoints_table(self, checkpoints):
        """Print checkpoints in table format."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="Checkpoints")
            table.add_column("ID", style="cyan")
            table.add_column("Message", style="green")
            table.add_column("Timestamp", style="yellow")
            
            for cp in checkpoints:
                table.add_row(
                    cp.short_id,
                    cp.message[:50] + "..." if len(cp.message) > 50 else cp.message,
                    cp.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                )
            
            console.print(table)
        except ImportError:
            print("Checkpoints:")
            for cp in checkpoints:
                print(f"  {cp.short_id} - {cp.message} ({cp.timestamp})")
    
    async def diff(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None
    ) -> dict:
        """
        Show diff between checkpoints.
        
        Args:
            from_id: Starting checkpoint (default: previous)
            to_id: Ending checkpoint (default: current)
            
        Returns:
            Diff dictionary
        """
        service = await self._get_service()
        diff = await service.diff(from_id, to_id)
        
        self._print_diff(diff)
        return diff.to_dict()
    
    def _print_diff(self, diff):
        """Print diff in a readable format."""
        try:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            if not diff.files:
                console.print("[yellow]No changes[/yellow]")
                return
            
            console.print(f"\n[bold]Changes from {diff.from_checkpoint} to {diff.to_checkpoint or 'working directory'}[/bold]\n")
            
            table = Table()
            table.add_column("Status", style="cyan")
            table.add_column("File", style="white")
            table.add_column("+", style="green")
            table.add_column("-", style="red")
            
            for f in diff.files:
                status_color = {
                    "added": "green",
                    "modified": "yellow",
                    "deleted": "red"
                }.get(f.status, "white")
                
                table.add_row(
                    f"[{status_color}]{f.status}[/{status_color}]",
                    f.path,
                    str(f.additions),
                    str(f.deletions)
                )
            
            console.print(table)
            console.print(f"\n[green]+{diff.total_additions}[/green] [red]-{diff.total_deletions}[/red]")
        except ImportError:
            print(f"Changes from {diff.from_checkpoint} to {diff.to_checkpoint or 'working directory'}:")
            for f in diff.files:
                print(f"  {f.status}: {f.path} (+{f.additions}/-{f.deletions})")
    
    async def delete_all(self) -> bool:
        """
        Delete all checkpoints.
        
        Returns:
            True if successful
        """
        service = await self._get_service()
        result = await service.delete_all()
        
        if result:
            self._print_success("All checkpoints deleted")
            return True
        else:
            self._print_error("Failed to delete checkpoints")
            return False
    
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
    
    def _print_info(self, message: str):
        """Print info message."""
        try:
            from rich.console import Console
            Console().print(f"[dim]{message}[/dim]")
        except ImportError:
            print(message)


def handle_checkpoint_command(args: List[str], workspace_dir: Optional[str] = None, verbose: bool = False):
    """
    Handle checkpoint CLI commands.
    
    Usage:
        praisonai checkpoint save <message>     # Save a checkpoint
        praisonai checkpoint restore <id>       # Restore to a checkpoint
        praisonai checkpoint list [--limit N]   # List checkpoints
        praisonai checkpoint diff [from] [to]   # Show diff
        praisonai checkpoint delete             # Delete all checkpoints
    """
    handler = CheckpointsHandler(workspace_dir=workspace_dir, verbose=verbose)
    
    if not args:
        print("Usage: praisonai checkpoint <command> [options]")
        print("\nCommands:")
        print("  save <message>           Save a checkpoint with message")
        print("  restore <id>             Restore to a checkpoint")
        print("  list [--limit N]         List checkpoints (default: 20)")
        print("  diff [from] [to]         Show diff between checkpoints")
        print("  delete                   Delete all checkpoints")
        return
    
    command = args[0]
    
    if command == "save":
        if len(args) < 2:
            print("Usage: praisonai checkpoint save <message>")
            return
        
        message = " ".join(args[1:])
        allow_empty = "--allow-empty" in args
        if allow_empty:
            message = message.replace("--allow-empty", "").strip()
        
        asyncio.run(handler.save(message, allow_empty=allow_empty))
    
    elif command == "restore":
        if len(args) < 2:
            print("Usage: praisonai checkpoint restore <checkpoint_id>")
            return
        
        asyncio.run(handler.restore(args[1]))
    
    elif command == "list":
        limit = 20
        if "--limit" in args:
            idx = args.index("--limit")
            if idx + 1 < len(args):
                try:
                    limit = int(args[idx + 1])
                except ValueError:
                    pass
        
        asyncio.run(handler.list_checkpoints(limit=limit))
    
    elif command == "diff":
        from_id = args[1] if len(args) > 1 else None
        to_id = args[2] if len(args) > 2 else None
        
        asyncio.run(handler.diff(from_id, to_id))
    
    elif command == "delete":
        # Confirm deletion
        try:
            from rich.console import Console
            from rich.prompt import Confirm
            
            console = Console()
            if Confirm.ask("[yellow]Delete all checkpoints?[/yellow]"):
                asyncio.run(handler.delete_all())
            else:
                console.print("[dim]Cancelled[/dim]")
        except ImportError:
            response = input("Delete all checkpoints? [y/N] ")
            if response.lower() == 'y':
                asyncio.run(handler.delete_all())
            else:
                print("Cancelled")
    
    elif command == "help" or command == "--help":
        print("Checkpoint CLI Commands:")
        print("\n  praisonai checkpoint save <message>")
        print("    Save a checkpoint with the given message")
        print("    Options: --allow-empty  Allow checkpoint with no changes")
        print("\n  praisonai checkpoint restore <id>")
        print("    Restore workspace to a specific checkpoint")
        print("\n  praisonai checkpoint list [--limit N]")
        print("    List all checkpoints (default limit: 20)")
        print("\n  praisonai checkpoint diff [from_id] [to_id]")
        print("    Show diff between checkpoints")
        print("    If no IDs given, shows diff from last checkpoint to current")
        print("\n  praisonai checkpoint delete")
        print("    Delete all checkpoints for this workspace")
    
    else:
        print(f"Unknown command: {command}")
        print("Use 'praisonai checkpoint help' for available commands")

"""
Kanban command group for PraisonAI CLI.

Provides kanban task management for multi-agent coordination.
"""

import json
from typing import Optional, List

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Kanban task management")


def _get_kanban_store():
    """Get kanban store instance."""
    try:
        from praisonai.kanban.sqlite_store import SQLiteKanbanStore
        return SQLiteKanbanStore()
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Kanban module not available: {e}")
        raise typer.Exit(4)


@app.command("list")
def kanban_list_cmd(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (todo, ready, running, blocked, done)"),
    assignee: Optional[str] = typer.Option(None, "--assignee", "-a", help="Filter by assignee"),
    board: str = typer.Option("default", "--board", "-b", help="Board name"),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of tasks to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List kanban tasks with optional filtering."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        # Build filters
        filters = {'board': board}
        if status:
            filters['status'] = status
        if assignee:
            filters['assignee'] = assignee
        
        tasks = store.list_tasks(filters)
        
        if len(tasks) > limit:
            tasks = tasks[:limit]
        
        if json_output:
            result = {
                'tasks': [task.to_dict() for task in tasks],
                'count': len(tasks),
                'filters': filters,
                'limited': len(tasks) == limit
            }
            output.print_json(result)
        else:
            # Pretty print table
            if not tasks:
                output.print_info("No tasks found")
                return
            
            output.print_info(f"Found {len(tasks)} tasks{' (limited)' if len(tasks) == limit else ''}")
            output.print("")
            
            # Table header
            print(f"{'ID':<15} {'Status':<10} {'Title':<40} {'Assignee':<15} {'Priority':<8}")
            print("-" * 90)
            
            # Task rows
            for task in tasks:
                title = task.title[:37] + "..." if len(task.title) > 40 else task.title
                assignee = task.assignee[:12] + "..." if len(task.assignee) > 15 else task.assignee
                print(f"{task.id:<15} {task.status.value:<10} {title:<40} {assignee:<15} {task.priority:<8}")
    
    except Exception as e:
        output.print_error(f"Failed to list tasks: {e}")
        raise typer.Exit(1)


@app.command("create")
def kanban_create_cmd(
    title: str = typer.Argument(..., help="Task title"),
    body: str = typer.Option("", "--body", "-b", help="Task description"),
    assignee: str = typer.Option("", "--assignee", "-a", help="Username to assign to"),
    status: str = typer.Option("todo", "--status", "-s", help="Initial status"),
    priority: int = typer.Option(0, "--priority", "-p", help="Task priority (higher = more important)"),
    board: str = typer.Option("default", "--board", help="Board name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create a new kanban task."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        task_data = {
            'title': title,
            'body': body,
            'assignee': assignee,
            'status': status,
            'priority': priority,
            'board': board
        }
        
        task = store.create_task(task_data)
        
        if json_output:
            output.print_json(task.to_dict())
        else:
            output.print_success(f"Created task {task.id}")
            output.print_info(f"Title: {task.title}")
            output.print_info(f"Status: {task.status.value}")
            if assignee:
                output.print_info(f"Assignee: {task.assignee}")
    
    except Exception as e:
        output.print_error(f"Failed to create task: {e}")
        raise typer.Exit(1)


@app.command("show")
def kanban_show_cmd(
    task_id: str = typer.Argument(..., help="Task ID to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show detailed task information."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        task = store.get_task(task_id)
        if not task:
            output.print_error(f"Task {task_id} not found")
            raise typer.Exit(1)
        
        comments = store.get_comments(task_id)
        
        if json_output:
            result = {
                'task': task.to_dict(),
                'comments': [comment.to_dict() for comment in comments],
                'comment_count': len(comments)
            }
            output.print_json(result)
        else:
            # Pretty print task details
            output.print_info(f"Task: {task.id}")
            output.print("")
            output.print_info(f"Title: {task.title}")
            output.print_info(f"Status: {task.status.value}")
            output.print_info(f"Assignee: {task.assignee or '(unassigned)'}")
            output.print_info(f"Priority: {task.priority}")
            output.print_info(f"Board: {task.board}")
            output.print_info(f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            output.print_info(f"Updated: {task.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if task.body:
                output.print("")
                output.print_info("Description:")
                output.print(task.body)
            
            if comments:
                output.print("")
                output.print_info(f"Comments ({len(comments)}):")
                for comment in comments:
                    output.print(f"  [{comment.created_at.strftime('%m-%d %H:%M')}] {comment.author}: {comment.text}")
    
    except Exception as e:
        output.print_error(f"Failed to show task: {e}")
        raise typer.Exit(1)


@app.command("move")
def kanban_move_cmd(
    task_id: str = typer.Argument(..., help="Task ID to move"),
    status: str = typer.Argument(..., help="New status (todo, ready, running, blocked, done)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Move task to a new status."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        task = store.move_task(task_id, status)
        
        if json_output:
            output.print_json(task.to_dict())
        else:
            output.print_success(f"Moved task {task_id} to {status}")
    
    except Exception as e:
        output.print_error(f"Failed to move task: {e}")
        raise typer.Exit(1)


@app.command("comment")
def kanban_comment_cmd(
    task_id: str = typer.Argument(..., help="Task ID to comment on"),
    text: str = typer.Argument(..., help="Comment text"),
    author: str = typer.Option("cli", "--author", "-a", help="Comment author"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Add a comment to a task."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        comment = store.add_comment(task_id, author, text)
        
        if json_output:
            output.print_json(comment.to_dict())
        else:
            output.print_success(f"Added comment to task {task_id}")
    
    except Exception as e:
        output.print_error(f"Failed to add comment: {e}")
        raise typer.Exit(1)


@app.command("link")
def kanban_link_cmd(
    parent_id: str = typer.Argument(..., help="Parent task ID"),
    child_id: str = typer.Argument(..., help="Child task ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create dependency link between tasks."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        link = store.add_link(parent_id, child_id)
        
        if json_output:
            result = {
                'parent_id': link.parent_id,
                'child_id': link.child_id,
                'created_at': link.created_at.isoformat()
            }
            output.print_json(result)
        else:
            output.print_success(f"Linked {parent_id} -> {child_id}")
    
    except Exception as e:
        output.print_error(f"Failed to link tasks: {e}")
        raise typer.Exit(1)


@app.command("boards")
def kanban_boards_cmd(
    action: str = typer.Argument("list", help="Action: list, switch"),
    board: Optional[str] = typer.Argument(None, help="Board name for switch action"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Manage kanban boards."""
    output = get_output_controller()
    
    try:
        if action == "list":
            from praisonai.kanban.paths import list_available_boards
            boards = list_available_boards()
            
            if json_output:
                output.print_json({"boards": boards})
            else:
                output.print_info(f"Available boards:")
                for board_name in boards:
                    output.print(f"  - {board_name}")
        
        elif action == "switch":
            if not board:
                output.print_error("Board name required for switch action")
                raise typer.Exit(1)
            
            import os
            os.environ['PRAISONAI_KANBAN_BOARD'] = board
            
            output.print_success(f"Switched to board '{board}'")
            output.print_info("Note: This only affects the current CLI session")
        
        else:
            output.print_error(f"Unknown action: {action}")
            raise typer.Exit(1)
    
    except Exception as e:
        output.print_error(f"Board operation failed: {e}")
        raise typer.Exit(1)


@app.command("dispatch")
def kanban_dispatch_cmd(
    max_spawn: int = typer.Option(3, "--max-spawn", "-m", help="Maximum tasks to spawn"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Manually trigger kanban task dispatcher."""
    output = get_output_controller()
    
    try:
        import asyncio
        from praisonai.gateway.kanban_dispatcher import dispatch_once
        
        # Run dispatcher once
        spawned = asyncio.run(dispatch_once(max_spawn))
        
        if json_output:
            output.print_json({"spawned": spawned})
        else:
            if spawned > 0:
                output.print_success(f"Spawned {spawned} task workers")
            else:
                output.print_info("No ready tasks to spawn")
    
    except Exception as e:
        output.print_error(f"Dispatch failed: {e}")
        raise typer.Exit(1)


@app.command("block")
def kanban_block_cmd(
    task_id: str = typer.Argument(..., help="Task ID to block"),
    reason: str = typer.Argument(..., help="Reason for blocking"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Block a task with a reason."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        # Move to blocked and add comment
        task = store.move_task(task_id, 'blocked')
        store.add_comment(task_id, 'cli', f"Blocked: {reason}")
        
        if json_output:
            output.print_json(task.to_dict())
        else:
            output.print_success(f"Blocked task {task_id}: {reason}")
    
    except Exception as e:
        output.print_error(f"Failed to block task: {e}")
        raise typer.Exit(1)


@app.command("unblock")
def kanban_unblock_cmd(
    task_id: str = typer.Argument(..., help="Task ID to unblock"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Unblock a task (move to ready)."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        task = store.move_task(task_id, 'ready')
        store.add_comment(task_id, 'cli', "Unblocked by CLI")
        
        if json_output:
            output.print_json(task.to_dict())
        else:
            output.print_success(f"Unblocked task {task_id}")
    
    except Exception as e:
        output.print_error(f"Failed to unblock task: {e}")
        raise typer.Exit(1)


@app.command("complete")
def kanban_complete_cmd(
    task_id: str = typer.Argument(..., help="Task ID to complete"),
    comment: str = typer.Option("", "--comment", "-c", help="Completion comment"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Mark a task as completed."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        task = store.move_task(task_id, 'done')
        
        if comment:
            store.add_comment(task_id, 'cli', f"Completed: {comment}")
        
        if json_output:
            output.print_json(task.to_dict())
        else:
            output.print_success(f"Completed task {task_id}")
    
    except Exception as e:
        output.print_error(f"Failed to complete task: {e}")
        raise typer.Exit(1)


@app.command("reclaim")
def kanban_reclaim_cmd(
    task_id: str = typer.Argument(..., help="Task ID to reclaim"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Reclaim a stuck/abandoned task."""
    output = get_output_controller()
    
    try:
        store = _get_kanban_store()
        
        # Force release any claim and move to ready
        store.update_task(task_id, {'claim_lock': None})
        task = store.move_task(task_id, 'ready')
        store.add_comment(task_id, 'cli', "Reclaimed from stuck state")
        
        if json_output:
            output.print_json(task.to_dict())
        else:
            output.print_success(f"Reclaimed task {task_id}")
    
    except Exception as e:
        output.print_error(f"Failed to reclaim task: {e}")
        raise typer.Exit(1)


# Add to main CLI app if this module is being registered
def register_kanban_commands(main_app):
    """Register kanban commands with main CLI app."""
    main_app.add_typer(app, name="kanban")


if __name__ == "__main__":
    app()
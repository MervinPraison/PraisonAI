"""
Todo command group for PraisonAI CLI.

Provides todo/task management commands.
"""

import typer

app = typer.Typer(help="Todo/task management")


@app.command("list")
def todo_list():
    """List todos."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['todo', 'list']
    
    run_wrapper_command(argv, feature="todo")


@app.command("add")
def todo_add(
    task: str = typer.Argument(..., help="Task description"),
    priority: str = typer.Option("medium", "--priority", "-p", help="Priority (low, medium, high)"),
):
    """Add a todo."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['todo', 'add', task]
    
    run_wrapper_command(argv, feature="todo")


@app.command("done")
def todo_done(
    task_id: str = typer.Argument(..., help="Task ID to mark as done"),
):
    """Mark a todo as done."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['todo', 'done', task_id]
    
    run_wrapper_command(argv, feature="todo")

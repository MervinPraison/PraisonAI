"""
Workflow command group for PraisonAI CLI.

Provides workflow management commands.
"""

import typer

app = typer.Typer(help="Workflow management")


@app.command("run", context_settings={"allow_extra_args": True, "allow_interspersed_args": True, "ignore_unknown_options": True})
def workflow_run(
    ctx: typer.Context,
    file: str = typer.Argument(..., help="Workflow file path"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview steps without executing (job workflows only)"),
    resume: bool = typer.Option(False, "--resume", help="Resume from the last saved checkpoint"),
    checkpoint: str = typer.Option(None, "--checkpoint", help="Checkpoint name to save/resume under"),
    rebase_checkpoint: bool = typer.Option(False, "--rebase-checkpoint", help="Force resume at the same step index despite a workflow definition change"),
):
    """Run a workflow.
    
    Use --var key=value to pass variables to YAML workflows.
    Use --dry-run to preview job workflows without executing.
    Use --resume to continue an interrupted run from its last checkpoint.
    Can be specified multiple times.
    
    Example:
        praisonai workflow run my_workflow.yaml --var topic="AI Tools"
        praisonai workflow run release-notes.md --resume
    """
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['workflow', 'run', file]
    # Pass through extra args (includes --var arguments and custom flags)
    argv.extend(ctx.args)
    if model:
        argv.extend(['--model', model])
    if verbose:
        argv.append('--verbose')
    if dry_run:
        argv.append('--dry-run')
    if resume:
        argv.append('--resume')
    if checkpoint:
        argv.extend(['--checkpoint', checkpoint])
    if rebase_checkpoint:
        argv.append('--rebase-checkpoint')
    
    run_wrapper_command(argv, feature="workflow")


@app.command("checkpoints")
def workflow_checkpoints(
    delete: str = typer.Option(None, "--delete", help="Delete the named checkpoint"),
):
    """List saved workflow checkpoints, or delete one with --delete."""
    from praisonai_code._wrapper_bridge import run_wrapper_command

    argv = ['workflow', 'checkpoints']
    if delete:
        argv.extend(['--delete', delete])

    run_wrapper_command(argv, feature="workflow")


@app.command("list")
def workflow_list():
    """List available workflows."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['workflow', 'list']
    
    run_wrapper_command(argv, feature="workflow")


@app.command("validate")
def workflow_validate(
    file: str = typer.Argument(..., help="Workflow file path"),
):
    """Validate a workflow file."""
    from praisonai_code._wrapper_bridge import run_wrapper_command

    argv = ['workflow', 'validate', file]

    run_wrapper_command(argv, feature="workflow")


@app.command("create")
def workflow_create(
    name: str = typer.Argument(..., help="Workflow name"),
    template: str = typer.Option(None, "--template", "-t", help="Template to use"),
):
    """Create a new workflow."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['workflow', 'create', name]
    if template:
        argv.extend(['--template', template])
    
    run_wrapper_command(argv, feature="workflow")

"""
Train command group for PraisonAI CLI.

Provides model training commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Model training and fine-tuning")


@app.callback(invoke_without_command=True)
def train_main(
    ctx: typer.Context,
    dataset: Optional[str] = typer.Argument(None, help="Training dataset path"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Base model to fine-tune"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Train or fine-tune models.
    
    Examples:
        praisonai train dataset.json
        praisonai train --model gpt-4o dataset.json
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['train']
    if dataset:
        argv.append(dataset)
    if model:
        argv.extend(['--model', model])
    if verbose:
        argv.append('--verbose')
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv

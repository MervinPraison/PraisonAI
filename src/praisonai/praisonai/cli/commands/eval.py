"""
Eval command group for PraisonAI CLI.

Provides evaluation commands.
"""

import typer

app = typer.Typer(help="Evaluation and testing")


@app.command("accuracy")
def eval_accuracy(
    agent: str = typer.Argument(..., help="Agent file or name"),
    input_text: str = typer.Option(..., "--input", "-i", help="Input text"),
    expected: str = typer.Option(..., "--expected", "-e", help="Expected output"),
    iterations: int = typer.Option(3, "--iterations", "-n", help="Number of iterations"),
):
    """Run accuracy evaluation."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['eval', 'accuracy', agent, '--input', input_text, '--expected', expected]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("performance")
def eval_performance(
    agent: str = typer.Argument(..., help="Agent file or name"),
    iterations: int = typer.Option(50, "--iterations", "-n", help="Number of iterations"),
):
    """Run performance evaluation."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['eval', 'performance', agent, '--iterations', str(iterations)]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv

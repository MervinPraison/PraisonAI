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


@app.command("judge")
def eval_judge(
    output: str = typer.Option(None, "--output", "-o", help="Output text to judge"),
    expected: str = typer.Option(None, "--expected", "-e", help="Expected output for accuracy mode"),
    criteria: str = typer.Option(None, "--criteria", "-c", help="Custom criteria for evaluation"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model for judging"),
    threshold: float = typer.Option(7.0, "--threshold", "-t", help="Score threshold for passing"),
    input_file: str = typer.Option(None, "--file", "-f", help="File containing output to judge"),
):
    """
    Judge output using LLM-as-judge.
    
    Examples:
        praisonai eval judge --output "4" --expected "4"
        praisonai eval judge --output "Hello!" --criteria "Response is helpful"
        praisonai eval judge --file output.txt --criteria "Code is correct"
    """
    try:
        from praisonaiagents.eval import Judge, JudgeConfig
    except ImportError:
        typer.echo("Error: praisonaiagents package required. Install with: pip install praisonaiagents")
        raise typer.Exit(1)
    
    # Get output from file if specified
    if input_file:
        try:
            with open(input_file, 'r') as f:
                output = f.read()
        except FileNotFoundError:
            typer.echo(f"Error: File not found: {input_file}")
            raise typer.Exit(1)
    
    if not output:
        typer.echo("Error: Either --output or --file must be provided")
        raise typer.Exit(1)
    
    if not expected and not criteria:
        typer.echo("Error: Either --expected or --criteria must be provided")
        raise typer.Exit(1)
    
    # Create judge with config
    config = JudgeConfig(
        model=model,
        threshold=threshold,
        criteria=criteria,
    )
    judge = Judge(config=config)
    
    # Run evaluation
    typer.echo(f"Judging output (threshold: {threshold})...")
    result = judge.run(output=output, expected=expected, criteria=criteria, print_summary=True)
    
    # Exit with appropriate code
    if result.passed:
        raise typer.Exit(0)
    else:
        raise typer.Exit(1)


@app.command("list-judges")
def list_judges_cmd():
    """List all registered judge types."""
    try:
        from praisonaiagents.eval import list_judges
    except ImportError:
        typer.echo("Error: praisonaiagents package required. Install with: pip install praisonaiagents")
        raise typer.Exit(1)
    
    judges = list_judges()
    typer.echo("Registered Judge Types:")
    for name in judges:
        typer.echo(f"  - {name}")

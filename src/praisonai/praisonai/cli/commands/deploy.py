"""
Deploy command group for PraisonAI CLI.

Provides deployment commands.
"""

import typer

app = typer.Typer(help="Deployment management")


@app.command("docker")
def deploy_docker(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    tag: str = typer.Option(None, "--tag", "-t", help="Docker image tag"),
):
    """Deploy as Docker container."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['deploy', 'docker', file]
    if tag:
        argv.extend(['--tag', tag])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("aws")
def deploy_aws(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    region: str = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Deploy to AWS."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['deploy', 'aws', file]
    if region:
        argv.extend(['--region', region])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("gcp")
def deploy_gcp(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    project: str = typer.Option(None, "--project", "-p", help="GCP project"),
):
    """Deploy to Google Cloud."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['deploy', 'gcp', file]
    if project:
        argv.extend(['--project', project])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("azure")
def deploy_azure(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    resource_group: str = typer.Option(None, "--resource-group", "-g", help="Azure resource group"),
):
    """Deploy to Azure."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['deploy', 'azure', file]
    if resource_group:
        argv.extend(['--resource-group', resource_group])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv

"""
Deploy command group for PraisonAI CLI.

Provides deployment commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Deployment management")


@app.command("docker")
def deploy_docker(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Docker image tag"),
):
    """Deploy as Docker container."""
    from praisonai.cli.features.deploy import handle_deploy_command

    args = ["docker", file]
    if tag is not None:
        args.extend(["--tag", tag])

    raise typer.Exit(handle_deploy_command(args))


@app.command("aws")
def deploy_aws(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Deploy to AWS."""
    from praisonai.cli.features.deploy import handle_deploy_command

    args = ["aws", file]
    if region is not None:
        args.extend(["--region", region])

    raise typer.Exit(handle_deploy_command(args))


@app.command("gcp")
def deploy_gcp(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="GCP project"),
):
    """Deploy to Google Cloud."""
    from praisonai.cli.features.deploy import handle_deploy_command

    args = ["gcp", file]
    if project is not None:
        args.extend(["--project", project])

    raise typer.Exit(handle_deploy_command(args))


@app.command("azure")
def deploy_azure(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    resource_group: Optional[str] = typer.Option(None, "--resource-group", "-g", help="Azure resource group"),
):
    """Deploy to Azure."""
    from praisonai.cli.features.deploy import handle_deploy_command

    args = ["azure", file]
    if resource_group is not None:
        args.extend(["--resource-group", resource_group])

    raise typer.Exit(handle_deploy_command(args))

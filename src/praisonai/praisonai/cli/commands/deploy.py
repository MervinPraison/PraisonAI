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
    from ..features.deploy import handle_deploy_command

    args = ["docker", file]
    if tag:
        args.extend(["--tag", tag])

    raise typer.Exit(handle_deploy_command(args))


@app.command("aws")
def deploy_aws(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Deploy to AWS."""
    from ..features.deploy import handle_deploy_command

    args = ["aws", file]
    if region:
        args.extend(["--region", region])

    raise typer.Exit(handle_deploy_command(args))


@app.command("gcp")
def deploy_gcp(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="GCP project"),
):
    """Deploy to Google Cloud."""
    from ..features.deploy import handle_deploy_command

    args = ["gcp", file]
    if project:
        args.extend(["--project", project])

    raise typer.Exit(handle_deploy_command(args))


@app.command("azure")
def deploy_azure(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    resource_group: Optional[str] = typer.Option(None, "--resource-group", "-g", help="Azure resource group"),
):
    """Deploy to Azure."""
    from ..features.deploy import handle_deploy_command

    args = ["azure", file]
    if resource_group:
        args.extend(["--resource-group", resource_group])

    raise typer.Exit(handle_deploy_command(args))

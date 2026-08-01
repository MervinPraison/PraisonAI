"""
Deploy command group for PraisonAI CLI.

Provides deployment commands for API, Docker, and cloud providers.
"""

from __future__ import annotations

from typing import Optional

import typer

app = typer.Typer(help="Deployment management")


def _exit_from_handler(args: list[str]) -> None:
    from praisonai_deploy.cli.features.deploy import handle_deploy_command

    raise typer.Exit(handle_deploy_command(args))


@app.command("run")
def deploy_run(
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Path to agents.yaml"),
    deploy_type: Optional[str] = typer.Option(None, "--type", help="Deployment type: api, docker, cloud"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Cloud provider: aws, azure, gcp"),
    background: bool = typer.Option(False, "--background", help="Run in background (API only)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Deploy agents from agents.yaml."""
    args = ["run", "--file", file]
    if deploy_type:
        args.extend(["--type", deploy_type])
    if provider:
        args.extend(["--provider", provider])
    if background:
        args.append("--background")
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("doctor")
def deploy_doctor(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Path to agents.yaml"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Check specific provider"),
    all_checks: bool = typer.Option(False, "--all", help="Run all checks"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check deployment readiness."""
    args = ["doctor"]
    if file:
        args.extend(["--file", file])
    if provider:
        args.extend(["--provider", provider])
    if all_checks:
        args.append("--all")
    if verbose:
        args.append("--verbose")
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("init")
def deploy_init(
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Output file path"),
    deploy_type: str = typer.Option("api", "--type", help="Deployment type: api, docker, cloud"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Cloud provider (for cloud type)"),
):
    """Generate sample agents.yaml with deploy configuration."""
    args = ["init", "--file", file, "--type", deploy_type]
    if provider:
        args.extend(["--provider", provider])
    _exit_from_handler(args)


@app.command("validate")
def deploy_validate(
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Path to agents.yaml"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Validate agents.yaml deploy configuration."""
    args = ["validate", "--file", file]
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("plan")
def deploy_plan(
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Path to agents.yaml"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show deployment plan without executing."""
    args = ["plan", "--file", file]
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("status")
def deploy_status(
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Path to agents.yaml"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed metadata"),
):
    """Show current deployment status."""
    args = ["status", "--file", file]
    if as_json:
        args.append("--json")
    if verbose:
        args.append("--verbose")
    _exit_from_handler(args)


@app.command("destroy")
def deploy_destroy(
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Path to agents.yaml"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    force: bool = typer.Option(False, "--force", help="Force deletion"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Destroy/delete deployment."""
    args = ["destroy", "--file", file]
    if yes:
        args.append("--yes")
    if force:
        args.append("--force")
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("api")
def deploy_api(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    background: bool = typer.Option(False, "--background", help="Run in background"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Deploy as local API server (alias for run --type api)."""
    args = ["api", file]
    if background:
        args.append("--background")
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("cloud")
def deploy_cloud(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    provider: str = typer.Option(..., "--provider", help="Cloud provider: aws, azure, gcp"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Deploy to cloud (alias for run --type cloud)."""
    args = ["cloud", file, "--provider", provider]
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("docker")
def deploy_docker(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Docker image tag"),
):
    """Deploy as Docker container."""
    args = ["docker", file]
    if tag is not None:
        args.extend(["--tag", tag])
    _exit_from_handler(args)


@app.command("aws")
def deploy_aws(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
):
    """Deploy to AWS."""
    args = ["aws", file]
    if region is not None:
        args.extend(["--region", region])
    _exit_from_handler(args)


@app.command("gcp")
def deploy_gcp(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="GCP project"),
):
    """Deploy to Google Cloud."""
    args = ["gcp", file]
    if project is not None:
        args.extend(["--project", project])
    _exit_from_handler(args)


@app.command("azure")
def deploy_azure(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    resource_group: Optional[str] = typer.Option(None, "--resource-group", "-g", help="Azure resource group"),
):
    """Deploy to Azure."""
    args = ["azure", file]
    if resource_group is not None:
        args.extend(["--resource-group", resource_group])
    _exit_from_handler(args)


@app.command("fly")
def deploy_fly(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="Fly region"),
):
    """Deploy to Fly.io."""
    args = ["fly", file]
    if region is not None:
        args.extend(["--region", region])
    _exit_from_handler(args)


@app.command("railway")
def deploy_railway(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
):
    """Deploy to Railway."""
    _exit_from_handler(["railway", file])


@app.command("render")
def deploy_render(
    file: str = typer.Argument("agents.yaml", help="Agent file to deploy"),
):
    """Deploy to Render."""
    _exit_from_handler(["render", file])


compose_app = typer.Typer(help="Docker Compose stack management")
app.add_typer(compose_app, name="compose")


@compose_app.command("up")
def deploy_compose_up(
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Path to agents.yaml"),
    stack_dir: Optional[str] = typer.Option(None, "--stack-dir", help="Path to compose stack template"),
    foreground: bool = typer.Option(False, "--foreground", help="Run in foreground (no -d)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Start agents API + Postgres compose stack."""
    args = ["compose", "up", "--file", file]
    if stack_dir:
        args.extend(["--stack-dir", stack_dir])
    if foreground:
        args.append("--foreground")
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@compose_app.command("down")
def deploy_compose_down(
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Path to agents.yaml"),
    stack_dir: Optional[str] = typer.Option(None, "--stack-dir", help="Path to compose stack template"),
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Remove named volumes"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Stop agents compose stack."""
    args = ["compose", "down", "--file", file]
    if stack_dir:
        args.extend(["--stack-dir", stack_dir])
    if volumes:
        args.append("--volumes")
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("create")
def deploy_create(
    template: str = typer.Option(..., "--template", "-t", help="Starter template name"),
    directory: str = typer.Option(".", "--dir", "-d", help="Target directory"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Scaffold a deploy project from a starter template."""
    args = ["create", "--template", template, "--dir", directory]
    if as_json:
        args.append("--json")
    _exit_from_handler(args)


@app.command("helm")
def deploy_helm(
    chart: str = typer.Option(..., "--chart", help="Chart name: gateway or agents-api"),
    release: str = typer.Option("praisonai", "--release", "-r", help="Helm release name"),
    namespace: str = typer.Option("default", "--namespace", "-n", help="Kubernetes namespace"),
    stack_dir: Optional[str] = typer.Option(None, "--chart-dir", help="Override chart directory"),
    install: bool = typer.Option(True, "--install/--no-install", help="Run helm upgrade --install"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Thin wrapper around helm upgrade for repo infra charts."""
    args = ["helm", "--chart", chart, "--release", release, "--namespace", namespace]
    if stack_dir:
        args.extend(["--chart-dir", stack_dir])
    if not install:
        args.append("--no-install")
    if as_json:
        args.append("--json")
    _exit_from_handler(args)

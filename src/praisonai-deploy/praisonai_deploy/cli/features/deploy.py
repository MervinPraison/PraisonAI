"""
CLI handler for deploy commands.
"""
import json
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint


console = Console()


def _build_deploy_config_from_args(args):
    """Build DeployConfig from CLI flags, merging YAML deploy section when present."""
    from praisonai_deploy.models import DeployConfig, DeployType, CloudProvider, APIConfig, DockerConfig, CloudConfig
    from praisonai_deploy.schema import validate_agents_yaml

    deploy_type = DeployType(args.type)
    yaml_config = None
    try:
        yaml_config = validate_agents_yaml(args.file)
    except (FileNotFoundError, ValueError):
        pass

    if deploy_type == DeployType.API:
        api = yaml_config.api.model_copy() if yaml_config and yaml_config.api else APIConfig()
        api = api.model_copy(update={
            "host": getattr(args, 'host', api.host),
            "port": getattr(args, 'port', api.port),
            "workers": getattr(args, 'workers', api.workers),
        })
        return DeployConfig(type=deploy_type, api=api)

    if deploy_type == DeployType.DOCKER:
        docker = yaml_config.docker.model_copy() if yaml_config and yaml_config.docker else DockerConfig()
        updates = {}
        if getattr(args, 'image_name', None):
            updates["image_name"] = args.image_name
        if getattr(args, 'tag', None):
            updates["tag"] = args.tag
        if getattr(args, 'registry', None) is not None:
            updates["registry"] = args.registry
        if getattr(args, 'push', False):
            updates["push"] = args.push
        docker = docker.model_copy(update=updates)
        api = yaml_config.api if yaml_config else None
        return DeployConfig(type=deploy_type, docker=docker, api=api)

    provider = CloudProvider(args.provider)
    cloud = yaml_config.cloud.model_copy() if yaml_config and yaml_config.cloud else CloudConfig(
        provider=provider,
        region=getattr(args, 'region', 'us-east-1'),
        service_name=getattr(args, 'service_name', 'praisonai-service'),
    )
    cloud = cloud.model_copy(update={
        "provider": provider,
        "region": getattr(args, 'region', cloud.region),
        "service_name": getattr(args, 'service_name', cloud.service_name),
        "project_id": getattr(args, 'project_id', cloud.project_id),
        "resource_group": getattr(args, 'resource_group', cloud.resource_group),
        "subscription_id": getattr(args, 'subscription_id', cloud.subscription_id),
    })
    return DeployConfig(type=deploy_type, cloud=cloud)


class DeployHandler:
    """Handler for deploy CLI commands."""
    
    def handle_deploy(self, args):
        """
        Handle deploy command.
        
        Args:
            args: Parsed command-line arguments
        """
        try:
            from praisonai_deploy import Deploy
            if args.type:
                config = _build_deploy_config_from_args(args)
                deploy = Deploy(config, args.file)
            else:
                # Load from YAML
                deploy = Deploy.from_yaml(args.file)
            
            # Execute deployment
            console.print(f"\n[bold blue]🚀 Starting deployment...[/bold blue]\n")
            
            background = getattr(args, 'background', False)
            result = deploy.deploy(background=background)
            
            if args.json:
                self._print_json({
                    "success": result.success,
                    "message": result.message,
                    "url": result.url,
                    "error": result.error,
                    "metadata": result.metadata
                })
            else:
                if result.success:
                    console.print(f"\n[bold green]✅ {result.message}[/bold green]")
                    if result.url:
                        console.print(f"[bold cyan]🔗 URL:[/bold cyan] {result.url}")
                    if result.metadata:
                        console.print(f"\n[bold]Metadata:[/bold]")
                        for key, value in result.metadata.items():
                            console.print(f"  • {key}: {value}")
                else:
                    console.print(f"\n[bold red]❌ {result.message}[/bold red]")
                    if result.error:
                        console.print(f"[red]Error: {result.error}[/red]")
                    sys.exit(1)
        
        except Exception as e:
            if getattr(args, 'json', False):
                self._print_json({"success": False, "error": str(e)})
            else:
                console.print(f"[bold red]❌ Deployment failed: {e}[/bold red]")
            sys.exit(1)
    
    def handle_doctor(self, args):
        """
        Handle deploy doctor command.
        
        Args:
            args: Parsed command-line arguments
        """
        try:
            from praisonai_deploy.doctor import (
                run_all_checks, run_local_checks, 
                run_aws_checks, run_azure_checks, run_gcp_checks
            )
            
            console.print("\n[bold blue]🏥 Running deployment health checks...[/bold blue]\n")
            
            # Determine which checks to run
            if args.all:
                report = run_all_checks(args.file)
            elif args.provider:
                if args.provider == 'aws':
                    report = run_aws_checks()
                elif args.provider == 'azure':
                    report = run_azure_checks()
                elif args.provider == 'gcp':
                    report = run_gcp_checks()
                else:
                    console.print(f"[red]Unknown provider: {args.provider}[/red]")
                    sys.exit(1)
            else:
                report = run_local_checks(agents_file=args.file)
            
            if args.json:
                self._print_json({
                    "total_checks": report.total_checks,
                    "passed": report.passed_checks,
                    "failed": report.failed_checks,
                    "all_passed": report.all_passed,
                    "checks": [
                        {
                            "name": c.name,
                            "passed": c.passed,
                            "message": c.message,
                            "fix_suggestion": c.fix_suggestion
                        }
                        for c in report.checks
                    ]
                })
            else:
                # Create results table
                table = Table(title="Health Check Results")
                table.add_column("Check", style="cyan")
                table.add_column("Status", style="bold")
                table.add_column("Message")
                
                for check in report.checks:
                    status = "[green]✅ PASS[/green]" if check.passed else "[red]❌ FAIL[/red]"
                    table.add_row(check.name, status, check.message)
                
                console.print(table)
                
                # Summary
                console.print(f"\n[bold]Summary:[/bold]")
                console.print(f"  Total checks: {report.total_checks}")
                console.print(f"  Passed: [green]{report.passed_checks}[/green]")
                console.print(f"  Failed: [red]{report.failed_checks}[/red]")
                
                # Show fix suggestions for failed checks
                failed_checks = [c for c in report.checks if not c.passed and c.fix_suggestion]
                if failed_checks:
                    console.print(f"\n[bold yellow]💡 Fix Suggestions:[/bold yellow]")
                    for check in failed_checks:
                        console.print(f"\n[bold]{check.name}:[/bold]")
                        console.print(f"  {check.fix_suggestion}")
                
                if not report.all_passed:
                    sys.exit(1)
        
        except Exception as e:
            if getattr(args, 'json', False):
                self._print_json({"error": str(e)})
            else:
                console.print(f"[bold red]❌ Doctor check failed: {e}[/bold red]")
            sys.exit(1)
    
    def handle_init(self, args):
        """
        Handle deploy init command - generate sample agents.yaml.
        
        Args:
            args: Parsed command-line arguments
        """
        try:
            from praisonai_deploy.schema import save_sample_yaml
            from praisonai_deploy.models import DeployType, CloudProvider
            
            deploy_type = DeployType(args.type) if args.type else DeployType.API
            provider = CloudProvider(args.provider) if hasattr(args, 'provider') and args.provider else None
            
            console.print(f"\n[bold blue]📝 Generating sample agents.yaml...[/bold blue]\n")
            
            save_sample_yaml(args.file, deploy_type, provider)
            
            console.print(f"[bold green]✅ Created {args.file}[/bold green]")
            console.print(f"\n[bold]Next steps:[/bold]")
            console.print(f"  1. Edit {args.file} to configure your agents")
            console.print(f"  2. Run: praisonai deploy validate --file {args.file}")
            console.print(f"  3. Run: praisonai deploy --file {args.file}")
        
        except Exception as e:
            console.print(f"[bold red]❌ Failed to create sample YAML: {e}[/bold red]")
            sys.exit(1)
    
    def handle_validate(self, args):
        """
        Handle deploy validate command.
        
        Args:
            args: Parsed command-line arguments
        """
        try:
            from praisonai_deploy.schema import validate_agents_yaml
            
            console.print(f"\n[bold blue]🔍 Validating {args.file}...[/bold blue]\n")
            
            config = validate_agents_yaml(args.file)
            
            if config is None:
                if args.json:
                    self._print_json({"valid": False, "error": "No deploy section found"})
                else:
                    console.print("[yellow]⚠️  No deploy configuration found in agents.yaml[/yellow]")
                    console.print("\nRun: praisonai deploy init --file agents.yaml")
                sys.exit(1)
            
            if args.json:
                self._print_json({
                    "valid": True,
                    "type": config.type.value,
                    "config": config.model_dump()
                })
            else:
                console.print("[bold green]✅ Configuration is valid![/bold green]")
                console.print(f"\n[bold]Deploy Type:[/bold] {config.type.value}")
                
                if config.type.value == "api":
                    console.print(f"  Host: {config.api.host}")
                    console.print(f"  Port: {config.api.port}")
                    console.print(f"  Workers: {config.api.workers}")
                elif config.type.value == "docker":
                    console.print(f"  Image: {config.docker.image_name}:{config.docker.tag}")
                    console.print(f"  Ports: {config.docker.expose}")
                elif config.type.value == "cloud":
                    console.print(f"  Provider: {config.cloud.provider.value}")
                    console.print(f"  Region: {config.cloud.region}")
                    console.print(f"  Service: {config.cloud.service_name}")
        
        except ValueError as e:
            if args.json:
                self._print_json({"valid": False, "error": str(e)})
            else:
                console.print(f"[bold red]❌ Validation failed: {e}[/bold red]")
            sys.exit(1)
        except Exception as e:
            if args.json:
                self._print_json({"valid": False, "error": str(e)})
            else:
                console.print(f"[bold red]❌ Error: {e}[/bold red]")
            sys.exit(1)
    
    def handle_plan(self, args):
        """
        Handle deploy plan command - show deployment plan without executing.
        
        Args:
            args: Parsed command-line arguments
        """
        try:
            from praisonai_deploy import Deploy
            
            console.print(f"\n[bold blue]📋 Generating deployment plan...[/bold blue]\n")
            
            deploy = Deploy.from_yaml(args.file)
            plan = deploy.plan()
            
            if args.json:
                self._print_json(plan)
            else:
                console.print(Panel.fit(
                    self._format_plan(plan),
                    title="[bold]Deployment Plan[/bold]",
                    border_style="blue"
                ))
                
                console.print("\n[bold]To execute this plan, run:[/bold]")
                console.print(f"  praisonai deploy --file {args.file}")
        
        except Exception as e:
            if args.json:
                self._print_json({"error": str(e)})
            else:
                console.print(f"[bold red]❌ Failed to generate plan: {e}[/bold red]")
            sys.exit(1)
    
    def _format_plan(self, plan: dict) -> str:
        """Format plan dictionary as readable text."""
        lines = []
        for key, value in plan.items():
            if key == "steps" and isinstance(value, list):
                lines.append(f"\n[bold]Steps:[/bold]")
                for step in value:
                    lines.append(f"  {step}")
            elif isinstance(value, dict):
                lines.append(f"\n[bold]{key}:[/bold]")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"[bold]{key}:[/bold] {value}")
        return "\n".join(lines)
    
    def handle_status(self, args):
        """
        Handle deploy status command - show current deployment status.
        
        Args:
            args: Parsed command-line arguments
        """
        try:
            from praisonai_deploy import Deploy
            
            console.print(f"\n[bold blue]📊 Checking deployment status...[/bold blue]\n")
            
            deploy = Deploy.from_yaml(args.file)
            status = deploy.status()
            
            if args.json:
                self._print_json(status.to_dict())
            else:
                # Create status table
                table = Table(title="Deployment Status")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="bold")
                
                # State with color
                state_color = {
                    "running": "green",
                    "stopped": "yellow",
                    "pending": "blue",
                    "failed": "red",
                    "not_found": "dim",
                    "unknown": "dim"
                }.get(status.state.value, "white")
                
                table.add_row("State", f"[{state_color}]{status.state.value.upper()}[/{state_color}]")
                table.add_row("Service Name", status.service_name or "N/A")
                table.add_row("Provider", status.provider or "N/A")
                table.add_row("Region", status.region or "N/A")
                
                if status.url:
                    table.add_row("URL", f"[cyan]{status.url}[/cyan]")
                
                table.add_row("Healthy", "✅ Yes" if status.healthy else "❌ No")
                table.add_row("Instances", f"{status.instances_running}/{status.instances_desired}")
                
                if status.created_at:
                    table.add_row("Created", status.created_at)
                if status.updated_at:
                    table.add_row("Updated", status.updated_at)
                
                console.print(table)
                
                if status.message:
                    console.print(f"\n[bold]Message:[/bold] {status.message}")
                
                # Show metadata if verbose
                if getattr(args, 'verbose', False) and status.metadata:
                    console.print(f"\n[bold]Metadata:[/bold]")
                    for key, value in status.metadata.items():
                        console.print(f"  • {key}: {value}")
        
        except Exception as e:
            if getattr(args, 'json', False):
                self._print_json({"error": str(e)})
            else:
                console.print(f"[bold red]❌ Failed to get status: {e}[/bold red]")
            sys.exit(1)
    
    def handle_destroy(self, args):
        """
        Handle deploy destroy command - destroy/delete deployment.
        
        Args:
            args: Parsed command-line arguments
        """
        try:
            from praisonai_deploy import Deploy
            
            deploy = Deploy.from_yaml(args.file)
            
            # Confirmation check unless --yes is provided
            if not args.yes:
                console.print(f"\n[bold yellow]⚠️  Warning: This will destroy the deployment![/bold yellow]")
                console.print(f"[bold]File:[/bold] {args.file}")
                
                # Show what will be destroyed
                status = deploy.status()
                if status.service_name:
                    console.print(f"[bold]Service:[/bold] {status.service_name}")
                if status.provider:
                    console.print(f"[bold]Provider:[/bold] {status.provider}")
                
                confirm = input("\nType 'yes' to confirm destruction: ")
                if confirm.lower() != 'yes':
                    console.print("[yellow]Destruction cancelled.[/yellow]")
                    return
            
            console.print(f"\n[bold red]🗑️ Destroying deployment...[/bold red]\n")
            
            force = getattr(args, 'force', False)
            result = deploy.destroy(force=force)
            
            if args.json:
                self._print_json({
                    "success": result.success,
                    "message": result.message,
                    "resources_deleted": result.resources_deleted,
                    "error": result.error,
                    "metadata": result.metadata
                })
            else:
                if result.success:
                    console.print(f"[bold green]✅ {result.message}[/bold green]")
                    if result.resources_deleted:
                        console.print(f"\n[bold]Deleted resources:[/bold]")
                        for resource in result.resources_deleted:
                            console.print(f"  • {resource}")
                else:
                    console.print(f"[bold red]❌ {result.message}[/bold red]")
                    if result.error:
                        console.print(f"[red]Error: {result.error}[/red]")
                    sys.exit(1)
        
        except Exception as e:
            if getattr(args, 'json', False):
                self._print_json({"success": False, "error": str(e)})
            else:
                console.print(f"[bold red]❌ Destruction failed: {e}[/bold red]")
            sys.exit(1)
    
    def _print_json(self, data: dict):
        """Print data as JSON."""
        print(json.dumps(data, indent=2))


def handle_deploy_command(args):
    """
    Entry point for Typer deploy subcommands.

    Builds an args namespace, dispatches to the canonical ``DeployHandler``
    and returns an exit code, mirroring ``handle_serve_command``.

    Args:
        args: List of CLI tokens, e.g. ``["run", "--file", "agents.yaml"]``.

    Returns:
        Exit code (0 on success, non-zero on failure).
    """
    import argparse as ap

    handler = DeployHandler()

    if not args:
        print("Deploy commands:")
        print("  praisonai deploy run [--file FILE] [--type TYPE]")
        print("  praisonai deploy doctor [--file FILE] [--provider PROVIDER] [--all]")
        print("  praisonai deploy init [--file FILE] [--type TYPE]")
        print("  praisonai deploy validate [--file FILE]")
        print("  praisonai deploy plan [--file FILE]")
        print("  praisonai deploy status [--file FILE]")
        print("  praisonai deploy destroy [--file FILE] [--yes]")
        print("  praisonai deploy docker [FILE] [--tag TAG]")
        print("  praisonai deploy aws|gcp|azure [FILE]")
        return 1

    subcommand = args[0]
    sub_args = args[1:]

    deploy_args = ap.Namespace()
    deploy_args.file = 'agents.yaml'
    deploy_args.json = False
    deploy_args.all = False
    deploy_args.verbose = False
    deploy_args.background = False
    deploy_args.yes = False
    deploy_args.force = False
    deploy_args.provider = None
    deploy_args.type = None
    deploy_args.tag = None
    deploy_args.region = None
    deploy_args.project_id = None
    deploy_args.resource_group = None
    deploy_args.host = '127.0.0.1'
    deploy_args.port = 8005
    deploy_args.workers = 1
    deploy_args.image_name = 'praisonai-app'
    deploy_args.push = False
    deploy_args.registry = None
    deploy_args.service_name = 'praisonai-service'
    deploy_args.subscription_id = None

    value_flags = {
        '--file': 'file', '-f': 'file',
        '--type': 'type',
        '--provider': 'provider',
        '--tag': 'tag', '-t': 'tag',
        '--region': 'region', '-r': 'region',
        '--project': 'project_id', '-p': 'project_id',
        '--resource-group': 'resource_group', '-g': 'resource_group',
        '--host': 'host',
        '--port': 'port',
        '--workers': 'workers',
        '--image-name': 'image_name',
        '--registry': 'registry',
        '--service-name': 'service_name',
        '--subscription-id': 'subscription_id',
    }
    bool_flags = {'--json', '--all', '--verbose', '-v', '--background', '--yes', '-y', '--force', '--push'}

    i = 0
    while i < len(sub_args):
        arg = sub_args[i]
        if arg in value_flags:
            if i + 1 >= len(sub_args):
                print(f"Error: option '{arg}' requires a value")
                return 1
            value = sub_args[i + 1]
            attr = value_flags[arg]
            if attr in ('port', 'workers'):
                setattr(deploy_args, attr, int(value))
            else:
                setattr(deploy_args, attr, value)
            i += 2
        elif arg in bool_flags:
            if arg in ('--verbose', '-v'):
                deploy_args.verbose = True
            elif arg in ('--yes', '-y'):
                deploy_args.yes = True
            elif arg == '--json':
                deploy_args.json = True
            elif arg == '--all':
                deploy_args.all = True
            elif arg == '--background':
                deploy_args.background = True
            elif arg == '--force':
                deploy_args.force = True
            elif arg == '--push':
                deploy_args.push = True
            i += 1
        elif not arg.startswith('-'):
            deploy_args.file = arg
            i += 1
        else:
            print(f"Error: unknown option '{arg}'")
            return 1

    dispatch = {
        'run': handler.handle_deploy,
        'doctor': handler.handle_doctor,
        'init': handler.handle_init,
        'validate': handler.handle_validate,
        'plan': handler.handle_plan,
        'status': handler.handle_status,
        'destroy': handler.handle_destroy,
    }

    if subcommand in dispatch:
        method = dispatch[subcommand]
    elif subcommand == 'docker':
        deploy_args.type = 'docker'
        method = handler.handle_deploy
    elif subcommand == 'api':
        deploy_args.type = 'api'
        method = handler.handle_deploy
    elif subcommand == 'cloud':
        deploy_args.type = 'cloud'
        if deploy_args.provider is None:
            print("Error: cloud deploy requires --provider aws|azure|gcp")
            return 1
        method = handler.handle_deploy
    elif subcommand in ('aws', 'gcp', 'azure'):
        deploy_args.type = 'cloud'
        deploy_args.provider = subcommand
        method = handler.handle_deploy
    else:
        print(f"Unknown deploy subcommand: {subcommand}")
        print("Available: run, doctor, init, validate, plan, status, destroy, api, cloud, docker, aws, gcp, azure")
        return 1

    try:
        method(deploy_args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return 0

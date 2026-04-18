"""
Setup command group for PraisonAI CLI.

Provides interactive onboarding and configuration wizard.
"""

import os
from pathlib import Path
from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Interactive onboarding / configuration wizard")

# Default PRAISON_HOME directory
def get_praison_home() -> Path:
    """Get the PraisonAI home directory."""
    home = os.getenv("PRAISONAI_HOME")
    if home:
        return Path(home)
    return Path.home() / ".praisonai"

PRAISON_HOME = get_praison_home()
ENV_FILE = PRAISON_HOME / ".env"

# Provider configurations
PROVIDERS = {
    "1": ("openai",    "OPENAI_API_KEY",    "gpt-4o-mini"),
    "2": ("anthropic", "ANTHROPIC_API_KEY", "claude-3-5-sonnet-latest"),
    "3": ("google",    "GEMINI_API_KEY",    "gemini-2.0-flash"),
    "4": ("ollama",    None,                "llama3.2"),
    "5": ("custom",    None,                None),
}

PROVIDER_NAMES = {
    "openai": ("OpenAI", "OPENAI_API_KEY", "gpt-4o-mini"),
    "anthropic": ("Anthropic", "ANTHROPIC_API_KEY", "claude-3-5-sonnet-latest"),
    "google": ("Google", "GEMINI_API_KEY", "gemini-2.0-flash"),
    "ollama": ("Ollama", None, "llama3.2"),
    "custom": ("Custom", None, None),
}


def _run_setup(
    non_interactive: bool = False,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> int:
    """Run the setup wizard."""
    try:
        from ..features.setup.handler import SetupHandler
        handler = SetupHandler()
        return handler.execute(
            non_interactive=non_interactive,
            provider=provider,
            api_key=api_key,
            model=model
        )
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Setup module not available: {e}")
        return 4
    except Exception as e:
        output = get_output_controller()
        output.print_error(f"Setup error: {e}")
        return 1


@app.callback(invoke_without_command=True)
def setup_callback(
    ctx: typer.Context,
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Run in non-interactive mode"),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM provider (openai, anthropic, google, ollama, custom)"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key for the provider"),
    model: Optional[str] = typer.Option(None, "--model", help="Default model to use"),
):
    """Run the onboarding wizard (idempotent — safe to re-run)."""
    if ctx.invoked_subcommand:
        return
        
    exit_code = _run_setup(
        non_interactive=non_interactive,
        provider=provider,
        api_key=api_key,
        model=model
    )
    raise typer.Exit(exit_code)


@app.command("wizard")
def setup_wizard(
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM provider"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key"),
    model: Optional[str] = typer.Option(None, "--model", help="Default model"),
):
    """Run the interactive setup wizard."""
    exit_code = _run_setup(
        non_interactive=False,
        provider=provider,
        api_key=api_key,
        model=model
    )
    raise typer.Exit(exit_code)


@app.command("config")
def setup_config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    edit: bool = typer.Option(False, "--edit", help="Edit configuration file"),
):
    """Manage setup configuration."""
    output = get_output_controller()
    
    if show:
        if ENV_FILE.exists():
            output.console.print(f"[bold]Configuration at {ENV_FILE}:[/bold]")
            content = ENV_FILE.read_text()
            # Don't show actual API keys for security
            lines = []
            for line in content.split('\n'):
                if '=' in line and any(key in line for key in ['API_KEY', 'TOKEN', 'SECRET']):
                    key, _ = line.split('=', 1)
                    lines.append(f"{key}=***")
                else:
                    lines.append(line)
            output.console.print('\n'.join(lines))
        else:
            output.print_warning(f"No configuration found at {ENV_FILE}")
            output.console.print("Run [cyan]praisonai setup[/cyan] to create one.")
    
    if edit:
        import subprocess
        editor = os.getenv("EDITOR", "nano")
        try:
            subprocess.run([editor, str(ENV_FILE)], check=True)
        except subprocess.CalledProcessError:
            output.print_error(f"Failed to open editor: {editor}")
        except FileNotFoundError:
            output.print_error(f"Editor not found: {editor}")


@app.command("reset")
def setup_reset(
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
):
    """Reset setup configuration."""
    output = get_output_controller()
    
    praison_home = get_praison_home()
    env_file = praison_home / ".env"
    config_file = praison_home / "config.yaml"
    files_to_remove = [path for path in (env_file, config_file) if path.exists()]

    if not files_to_remove:
        output.print_info("No setup configuration to reset.")
        return
    
    if not force:
        confirm = typer.confirm(f"Reset configuration at {praison_home}?")
        if not confirm:
            output.print_info("Reset cancelled.")
            return
    
    try:
        for path in files_to_remove:
            path.unlink()
        output.print_success("Configuration reset successfully.")
        output.console.print("Run [cyan]praisonai setup[/cyan] to configure again.")
    except Exception as e:
        output.print_error(f"Failed to reset configuration: {e}")
        raise typer.Exit(1)
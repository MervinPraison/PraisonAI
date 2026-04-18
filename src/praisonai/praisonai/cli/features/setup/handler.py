"""
Setup handler for PraisonAI CLI.

Provides the main SetupHandler class that implements the onboarding wizard.
"""

import getpass
import os
from pathlib import Path
from typing import Optional, Dict, Any

from ..base import CommandHandler
from .templates import ENV_TEMPLATE, CONFIG_TEMPLATE, AGENTS_TEMPLATE
from ...output.console import get_output_controller


class SetupHandler(CommandHandler):
    """
    Handler for the 'praisonai setup' command.
    
    Provides interactive onboarding and configuration wizard.
    """
    
    @property
    def feature_name(self) -> str:
        return "setup"
    
    def get_actions(self) -> list[str]:
        return ["wizard", "config", "reset"]
    
    def get_praison_home(self) -> Path:
        """Get the PraisonAI home directory."""
        home = os.getenv("PRAISONAI_HOME")
        if home:
            return Path(home)
        return Path.home() / ".praisonai"
    
    def execute(
        self,
        non_interactive: bool = False,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> int:
        """Execute the setup wizard."""
        output = get_output_controller()
        praison_home = self.get_praison_home()
        
        try:
            # Create directory structure
            self._create_directories(praison_home, output)
            
            if non_interactive:
                return self._run_non_interactive(
                    praison_home, provider, api_key, model, output
                )
            else:
                return self._run_interactive(praison_home, output)
                
        except Exception as e:
            output.print_error(f"Setup failed: {e}")
            return 1
    
    def _create_directories(self, praison_home: Path, output) -> None:
        """Create the ~/.praisonai directory structure."""
        praison_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        (praison_home / "logs").mkdir(exist_ok=True, mode=0o700)
        (praison_home / "sessions").mkdir(exist_ok=True, mode=0o700)
        praison_home.chmod(0o700)
        (praison_home / "logs").chmod(0o700)
        (praison_home / "sessions").chmod(0o700)
        output.print_success(f"Created directory structure at {praison_home}")
    
    def _run_non_interactive(
        self,
        praison_home: Path,
        provider: Optional[str],
        api_key: Optional[str], 
        model: Optional[str],
        output
    ) -> int:
        """Run setup in non-interactive mode."""
        if not provider:
            output.print_error("Provider is required in non-interactive mode")
            return 1
        
        providers = {
            "openai": ("OpenAI", "OPENAI_API_KEY", "gpt-4o-mini"),
            "anthropic": ("Anthropic", "ANTHROPIC_API_KEY", "claude-3-5-sonnet-latest"),
            "google": ("Google", "GEMINI_API_KEY", "gemini-2.0-flash"),
            "ollama": ("Ollama", None, "llama3.2"),
            "custom": ("Custom", None, None),
        }
        
        if provider not in providers:
            output.print_error(f"Unknown provider: {provider}")
            output.console.print("Valid providers: openai, anthropic, google, ollama, custom")
            return 1
        
        provider_info = providers[provider]
        provider_name = provider_info[0]
        env_key = provider_info[1]
        default_model = provider_info[2]
        
        # Validate API key requirement
        if env_key:
            api_key = api_key or os.getenv(env_key)
            if not api_key:
                output.print_error(
                    f"API key is required for {provider_name}; pass --api-key or set {env_key}"
                )
                return 1
        
        # Use default model if not specified
        if not model:
            if default_model:
                model = default_model
            else:
                output.print_error("Model is required for custom provider")
                return 1
        
        # Write configuration
        env_vars = {}
        if env_key and api_key:
            env_vars[env_key] = api_key
        
        config = {
            "provider": provider,
            "model": model,
            "telemetry": True,  # Default enabled in non-interactive mode
        }
        
        self._save_env(praison_home, env_vars, output)
        self._save_config(praison_home, config, output)
        
        output.print_success("Setup complete")
        output.console.print(f"Configuration saved to {praison_home}")
        output.console.print('Try: [cyan]praisonai "Say hello in one sentence"[/cyan]')
        
        return 0
    
    def _run_interactive(self, praison_home: Path, output) -> int:
        """Run setup in interactive mode."""
        try:
            from rich.prompt import Prompt, Confirm
        except ImportError:
            output.print_error("Rich is required for interactive mode")
            return 1
        
        output.console.print("\n[bold green]🚀 PraisonAI Setup Wizard[/bold green]\n")
        output.console.print("Let's configure PraisonAI for your first agent run!\n")
        
        # Provider selection
        output.console.print("[bold]1. Choose your LLM provider:[/bold]")
        output.console.print("  1) OpenAI (GPT-4o, GPT-4, GPT-3.5)")
        output.console.print("  2) Anthropic (Claude)")
        output.console.print("  3) Google (Gemini)")
        output.console.print("  4) Ollama (Local models)")
        output.console.print("  5) Custom provider")
        
        provider_choice = Prompt.ask(
            "\nSelect provider",
            choices=["1", "2", "3", "4", "5"],
            default="1"
        )
        
        providers = {
            "1": ("openai", "OPENAI_API_KEY", "gpt-4o-mini", "OpenAI"),
            "2": ("anthropic", "ANTHROPIC_API_KEY", "claude-3-5-sonnet-latest", "Anthropic"), 
            "3": ("google", "GEMINI_API_KEY", "gemini-2.0-flash", "Google"),
            "4": ("ollama", None, "llama3.2", "Ollama"),
            "5": ("custom", None, None, "Custom"),
        }
        
        provider_id, env_key, default_model, provider_name = providers[provider_choice]
        
        env_vars = {}
        
        # API key input
        if env_key:
            output.console.print(f"\n[bold]2. Enter your {provider_name} API key:[/bold]")
            
            # Check if key already exists in environment
            existing_key = os.getenv(env_key)
            if existing_key:
                use_existing = Confirm.ask(
                    f"Found existing {env_key} in environment. Use it?",
                    default=True
                )
                if use_existing:
                    env_vars[env_key] = existing_key
                else:
                    api_key = getpass.getpass("Enter API key: ")
                    env_vars[env_key] = api_key
            else:
                api_key = getpass.getpass("Enter API key (hidden): ")
                if not api_key.strip():
                    output.print_warning("No API key provided. You can set it later.")
                else:
                    env_vars[env_key] = api_key
        
        # Model selection
        output.console.print("\n[bold]3. Choose default model:[/bold]")
        if default_model:
            model = Prompt.ask(
                f"Default model for {provider_name}",
                default=default_model
            )
        else:
            model = Prompt.ask("Enter model name")
        
        # Telemetry consent
        output.console.print("\n[bold]4. Telemetry settings:[/bold]")
        output.console.print("Anonymous usage data helps improve PraisonAI.")
        output.console.print("No personal data or API keys are collected.")
        enable_telemetry = Confirm.ask(
            "Enable telemetry?",
            default=True
        )
        
        # Starter YAML
        output.console.print("\n[bold]5. Create starter configuration:[/bold]")
        create_starter = Confirm.ask(
            "Create a starter agents.yaml file in current directory?",
            default=False
        )
        
        # Save configuration
        config = {
            "provider": provider_id,
            "model": model,
            "telemetry": enable_telemetry,
        }
        
        self._save_env(praison_home, env_vars, output)
        self._save_config(praison_home, config, output)
        
        if create_starter:
            self._create_starter_yaml(output, model)
        
        # Success message
        output.console.print("\n[bold green]✅ Setup complete![/bold green]")
        output.console.print(f"Configuration saved to {praison_home}")
        
        output.console.print("\n[bold]Next steps:[/bold]")
        output.console.print('• Test: [cyan]praisonai "Say hello in one sentence"[/cyan]')
        output.console.print("• Chat: [cyan]praisonai chat[/cyan]")
        output.console.print("• Help: [cyan]praisonai --help[/cyan]")
        output.console.print("• Docs: [cyan]praisonai doctor[/cyan]")
        
        return 0
    
    def _save_env(self, praison_home: Path, env_vars: Dict[str, str], output) -> None:
        """Save environment variables to .env file."""
        env_file = praison_home / ".env"
        
        # Read existing content
        existing_vars = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    existing_vars[key.strip()] = value.strip()
        
        # Merge with new vars (new vars take precedence)
        existing_vars.update(env_vars)
        
        # Write updated content
        lines = []
        lines.append("# PraisonAI Configuration")
        lines.append("# Generated by praisonai setup")
        lines.append("")
        
        for key, value in sorted(existing_vars.items()):
            lines.append(f"{key}={value}")
        
        env_content = "\n".join(lines) + "\n"
        
        # Write with secure permissions
        def secure_opener(path, flags):
            return os.open(path, flags, 0o600)

        with open(env_file, "w", encoding="utf-8", opener=secure_opener) as file:
            file.write(env_content)
        env_file.chmod(0o600)
        
        output.print_success(f"Environment configuration saved to {env_file}")
    
    def _save_config(self, praison_home: Path, config: Dict[str, Any], output) -> None:
        """Save configuration to config.yaml file."""
        config_file = praison_home / "config.yaml"
        
        try:
            import yaml
        except ImportError:
            # Fall back to basic format if PyYAML not available
            lines = []
            lines.append("# PraisonAI Configuration")
            lines.append("# Generated by praisonai setup")
            lines.append("")
            
            for key, value in config.items():
                lines.append(f"{key}: {value}")
            
            config_content = "\n".join(lines) + "\n"
            config_file.write_text(config_content)
        else:
            config_content = yaml.dump(config, default_flow_style=False)
            config_file.write_text(f"# PraisonAI Configuration\n# Generated by praisonai setup\n\n{config_content}")
        
        output.print_success(f"Configuration saved to {config_file}")
    
    def _create_starter_yaml(self, output, model: str) -> None:
        """Create a starter agents.yaml file in the current directory."""
        agents_file = Path.cwd() / "agents.yaml"
        
        if agents_file.exists():
            output.print_warning("agents.yaml already exists, skipping creation")
            return
        
        agents_file.write_text(AGENTS_TEMPLATE.replace("gpt-4o-mini", model))
        output.print_success(f"Starter agents.yaml created at {agents_file}")
        output.console.print("Run [cyan]praisonai workflow run --file agents.yaml[/cyan] to test it")
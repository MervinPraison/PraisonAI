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
        verify: bool = True,
    ) -> int:
        """Execute the setup wizard."""
        output = get_output_controller()
        praison_home = self.get_praison_home()
        
        try:
            # Create directory structure
            self._create_directories(praison_home, output)
            
            if non_interactive:
                return self._run_non_interactive(
                    praison_home, provider, api_key, model, output, verify
                )
            else:
                return self._run_interactive(praison_home, output, verify)
                
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
        output,
        verify: bool = True,
    ) -> int:
        """Run setup in non-interactive mode."""
        if not provider:
            output.print_error("Provider is required in non-interactive mode")
            return 1
        
        providers = self._provider_defaults()
        
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
        self._save_credentials(praison_home, provider, env_key, api_key, model, output)
        
        output.print_success("Setup complete")
        output.console.print(f"Configuration saved to {praison_home}")

        if verify:
            self._run_smoke_test(model, env_vars, output)

        output.console.print('Try: [cyan]praisonai "Say hello in one sentence"[/cyan]')
        
        return 0
    
    def _run_interactive(self, praison_home: Path, output, verify: bool = True) -> int:
        """Run setup in interactive mode."""
        try:
            from rich.prompt import Prompt, Confirm
        except ImportError:
            output.print_error("Rich is required for interactive mode")
            return 1
        
        output.console.print("\n[bold green]🚀 PraisonAI Setup Wizard[/bold green]\n")
        output.console.print("Let's configure PraisonAI for your first agent run!\n")
        
        env_vars = {}
        provider_id = env_key = default_model = provider_name = None
        
        # 1. Auto-detect a provider whose *_API_KEY is already in the environment
        # and offer it as the pre-selected default. Auth becomes a confirmation
        # rather than a blind form.
        detected = self._detect_provider_from_env()
        if detected:
            provider_id, env_key, default_model, provider_name = detected
            output.console.print(
                f"[bold green]Detected {env_key}[/bold green] in your environment."
            )
            if Confirm.ask(
                f"Use {provider_name} ({default_model})?",
                default=True,
            ):
                env_vars[env_key] = os.environ[env_key]
            else:
                provider_id = env_key = default_model = provider_name = None
        
        # 2. Provider selection (only if nothing detected / accepted)
        if provider_id is None:
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
            
            provider_id, env_key, default_model, provider_name = (
                self._provider_menu()[provider_choice]
            )
            
            # API key input with live validation + re-prompt loop
            if env_key:
                output.console.print(f"\n[bold]2. Enter your {provider_name} API key:[/bold]")
                
                existing_key = os.getenv(env_key)
                if existing_key and Confirm.ask(
                    f"Found existing {env_key} in environment. Use it?",
                    default=True,
                ):
                    env_vars[env_key] = existing_key
                else:
                    entered = self._prompt_and_validate_key(
                        provider_id, provider_name, output
                    )
                    if entered:
                        env_vars[env_key] = entered
                    else:
                        output.print_warning("No API key provided. You can set it later.")
        
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
        self._save_credentials(
            praison_home,
            provider_id,
            env_key,
            env_vars.get(env_key) if env_key else None,
            model,
            output,
        )
        
        if create_starter:
            self._create_starter_yaml(output, model)
        
        # Success message
        output.console.print("\n[bold green]✅ Setup complete![/bold green]")
        output.console.print(f"Configuration saved to {praison_home}")

        # Post-setup smoke test: prove the configured key/model returns a
        # completion, so the user leaves setup with a *verified* working agent.
        if verify and env_vars:
            self._run_smoke_test(model, env_vars, output)

        output.console.print("\n[bold]Next steps:[/bold]")
        output.console.print('• Test: [cyan]praisonai "Say hello in one sentence"[/cyan]')
        output.console.print("• Chat: [cyan]praisonai chat[/cyan]")
        output.console.print("• Help: [cyan]praisonai --help[/cyan]")
        output.console.print("• Docs: [cyan]praisonai doctor[/cyan]")
        
        return 0
    
    def _provider_defaults(self) -> Dict[str, tuple]:
        """Provider table keyed by provider id: (name, env_key, default_model).

        Model choices are refreshed to current strong defaults for a
        coding-focused CLI. OpenAI sources its default from the single source
        of truth in ``llm/env.py`` so setup never re-declares that literal.
        """
        from praisonai_code.llm.env import DEFAULT_FALLBACK_MODEL

        return {
            "openai": ("OpenAI", "OPENAI_API_KEY", DEFAULT_FALLBACK_MODEL),
            "anthropic": ("Anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-4-20250514"),
            "google": ("Google", "GEMINI_API_KEY", "gemini-2.5-flash"),
            "ollama": ("Ollama", None, "llama3.2"),
            "custom": ("Custom", None, None),
        }

    def _provider_menu(self) -> Dict[str, tuple]:
        """Numeric provider menu → (provider_id, env_key, default_model, name)."""
        defaults = self._provider_defaults()
        ordered = ["openai", "anthropic", "google", "ollama", "custom"]
        menu = {}
        for idx, pid in enumerate(ordered, start=1):
            name, env_key, model = defaults[pid]
            menu[str(idx)] = (pid, env_key, model, name)
        return menu

    def _detect_provider_from_env(self) -> Optional[tuple]:
        """Detect a provider whose ``*_API_KEY`` is already in the environment.

        Reuses the shared inference helper in ``llm/env.py`` (the same one that
        drives the run-time "using X because Y is present" notice) and maps the
        resolved model back onto the setup provider table.

        Returns ``(provider_id, env_key, default_model, provider_name)`` or
        ``None`` when no supported provider credential is present.
        """
        # Map each credential env-var to the setup provider it unlocks. The
        # env-var actually present is returned (not the provider's canonical
        # one) so callers can read it back from the environment safely — e.g.
        # GOOGLE_API_KEY and GEMINI_API_KEY both map to "google".
        env_key_to_provider = {
            "OPENAI_API_KEY": "openai",
            "ANTHROPIC_API_KEY": "anthropic",
            "GEMINI_API_KEY": "google",
            "GOOGLE_API_KEY": "google",
        }
        defaults = self._provider_defaults()
        for env_key, provider_id in env_key_to_provider.items():
            if not os.environ.get(env_key):
                continue
            name, _canonical_env, default_model = defaults[provider_id]
            # Always present the refreshed setup default (clean, unprefixed)
            # so the model shown to the user and fed to the smoke test matches
            # _provider_defaults() rather than the older prefixed string from
            # llm/env.py. Return the env-var that was actually found.
            return provider_id, env_key, default_model, name
        return None

    def _prompt_and_validate_key(self, provider_id: str, provider_name: str, output) -> Optional[str]:
        """Prompt for an API key and validate it, re-prompting on failure.

        Reuses the shared ``validate_api_key`` format check (also used by
        ``auth login``) so a bad key is caught here rather than silently
        persisted and surfaced on the user's first real prompt.
        """
        try:
            from rich.prompt import Confirm
        except ImportError:
            Confirm = None

        try:
            from ...configuration.credentials import validate_api_key
        except Exception:
            validate_api_key = None

        max_attempts = 3
        for attempt in range(max_attempts):
            api_key = getpass.getpass("Enter API key (hidden): ").strip()
            if not api_key:
                return None

            if validate_api_key is None:
                return api_key

            valid, message = validate_api_key(provider_id, api_key)
            if valid:
                return api_key

            output.print_error(f"Invalid API key for {provider_name}: {message}")
            last_attempt = attempt == max_attempts - 1
            if last_attempt:
                # Bounded: keep the key on the final attempt rather than looping
                # forever (Confirm may be unavailable when rich is missing).
                output.print_warning("Proceeding with the entered key; you can update it later.")
                return api_key
            if Confirm is not None and not Confirm.ask("Try again?", default=True):
                return api_key
        return None

    def _run_smoke_test(self, model: Optional[str], env_vars: Dict[str, str], output) -> None:
        """Run a one-line smoke test to confirm the configured agent works.

        Constructs a minimal ``Agent`` and calls ``.start(...)`` once, so the
        user leaves setup with a verified working agent. Failures are reported
        but never abort setup (config is already persisted).
        """
        if not model:
            return

        output.console.print("\n[bold]Verifying your setup...[/bold]")

        # Ensure the freshly-entered key is visible to the smoke-test process.
        for key, value in env_vars.items():
            os.environ.setdefault(key, value)

        try:
            from praisonaiagents import Agent
        except Exception as e:
            output.print_warning(f"Skipping verification (praisonaiagents unavailable): {e}")
            return

        try:
            agent = Agent(name="setup-check", llm=model)
            result = agent.start("Say hello in one sentence")
            if result:
                output.print_success("Verified — your agent is working!")
                output.console.print(f"[dim]{str(result).strip()}[/dim]")
            else:
                output.print_warning("Verification returned no output.")
        except Exception as e:
            output.print_warning(f"Verification failed: {e}")
            output.console.print(
                "Your config was saved. Check your key/model, then run "
                "[cyan]praisonai doctor[/cyan]."
            )

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
        """Save configuration to unified config.yaml."""
        config_file = praison_home / "config.yaml"
        
        # Read existing config if it exists
        existing_config = {}
        if config_file.exists():
            try:
                import yaml
                with open(config_file, 'r') as f:
                    existing_config = yaml.safe_load(f) or {}
            except Exception as e:
                output.print_warning(f"Could not read existing config: {e}")
                # Continue with empty config rather than failing setup
        
        # Build new config structure following the unified schema
        new_config = existing_config.copy()
        
        # Map setup config to new schema
        if "model" in config:
            new_config.setdefault("agent", {})["model"] = config["model"]
        if "provider" in config:
            new_config.setdefault("agent", {})["provider"] = config["provider"]
        if "telemetry" in config:
            new_config["telemetry"] = config["telemetry"]
        
        # Write updated config
        try:
            import yaml
            config_content = yaml.dump(new_config, default_flow_style=False, sort_keys=False)
            config_file.write_text(f"# PraisonAI Configuration\n# Generated by praisonai setup\n\n{config_content}")
        except ImportError:
            # Fall back to basic format if PyYAML not available
            lines = []
            lines.append("# PraisonAI Configuration")
            lines.append("# Generated by praisonai setup")
            lines.append("")
            
            # Write agent section
            if "agent" in new_config:
                lines.append("agent:")
                for key, value in new_config["agent"].items():
                    lines.append(f"  {key}: {value}")
            
            # Write other top-level keys
            for key, value in new_config.items():
                if key != "agent":
                    lines.append(f"{key}: {value}")
            
            config_content = "\n".join(lines) + "\n"
            config_file.write_text(config_content)
        
        config_file.chmod(0o600)
        output.print_success(f"Configuration saved to {config_file}")
    
    def _save_credentials(
        self,
        praison_home: Path,
        provider: Optional[str],
        env_key: Optional[str],
        api_key: Optional[str],
        model: Optional[str],
        output,
    ) -> None:
        """Mirror the API key into the unified CredentialStore.

        Historically ``setup`` only wrote keys to ``~/.praisonai/.env`` while
        ``auth`` / ``inject_credentials_into_env`` read from a separate
        ``CredentialStore``. Writing here too gives both code paths a single
        source of truth so a key set via ``setup`` is picked up everywhere.

        To stay a single source of truth, this writes to the *same* store that
        ``auth`` / ``inject_credentials_into_env`` read from. When
        ``PRAISONAI_HOME`` is not overridden we use the default
        ``CredentialStore()`` so its legacy ``~/.praison/credentials.json``
        fallback is honoured and any pre-existing ``auth`` credentials are
        transparently migrated onto the canonical file on this write (no data
        loss). Only when ``PRAISONAI_HOME`` points somewhere other than the
        default home do we anchor the store under that directory.
        """
        # Only providers with a real API key can be stored; local providers
        # (e.g. ollama) and empty keys are skipped silently.
        if not provider or not env_key or not api_key:
            return

        try:
            from ...configuration.credentials import CredentialStore

            # Prefer the default store (canonical path + legacy fallback and
            # migration) so setup and the auth/inject read paths converge on a
            # single file. Fall back to an explicit path only when a custom
            # PRAISONAI_HOME is in effect.
            default_home = Path.home() / ".praisonai"
            if praison_home.resolve() == default_home.resolve():
                store = CredentialStore()
            else:
                store = CredentialStore(praison_home / "credentials.json")
            store.store_credential(
                provider=provider,
                api_key=api_key,
                model=model,
            )
        except Exception as e:
            # Never fail setup because the credential mirror failed; the .env
            # file has already been written as the primary artifact.
            output.print_warning(f"Could not save to credential store: {e}")

    def _create_starter_yaml(self, output, model: str) -> None:
        """Create a starter agents.yaml file in the current directory."""
        agents_file = Path.cwd() / "agents.yaml"
        
        if agents_file.exists():
            output.print_warning("agents.yaml already exists, skipping creation")
            return
        
        agents_file.write_text(AGENTS_TEMPLATE.replace("gpt-4o-mini", model))
        output.print_success(f"Starter agents.yaml created at {agents_file}")
        output.console.print("Run [cyan]praisonai workflow run --file agents.yaml[/cyan] to test it")
"""
Onboarding wizard for PraisonAI bots.

Interactive setup that guides users through:
1. Platform selection
2. Token configuration
3. Connection test (probe)
4. Config file generation (bot.yaml)
5. Optional daemon install

Usage:
    praisonai onboard
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

# Platform info for the wizard
PLATFORMS = {
    "telegram": {
        "name": "Telegram",
        "token_env": "TELEGRAM_BOT_TOKEN",
        "token_help": "Get from @BotFather on Telegram: https://t.me/BotFather",
        "install_hint": "pip install python-telegram-bot",
    },
    "discord": {
        "name": "Discord",
        "token_env": "DISCORD_BOT_TOKEN",
        "token_help": "Create at https://discord.com/developers/applications",
        "install_hint": "pip install discord.py",
    },
    "slack": {
        "name": "Slack",
        "token_env": "SLACK_BOT_TOKEN",
        "token_help": "Create at https://api.slack.com/apps",
        "install_hint": "pip install slack-bolt",
        "extra_env": {"SLACK_APP_TOKEN": "App token (xapp-...)"},
    },
    "whatsapp": {
        "name": "WhatsApp",
        "token_env": "WHATSAPP_ACCESS_TOKEN",
        "token_help": "Get from Meta for Developers: https://developers.facebook.com",
        "install_hint": "pip install aiohttp",
        "extra_env": {"WHATSAPP_PHONE_NUMBER_ID": "Phone number ID"},
    },
}


def _generate_bot_yaml(platforms: List[str], agent_name: str = "assistant", agent_instructions: str = "") -> str:
    """Generate bot.yaml content."""
    lines = ["agent:"]
    lines.append(f'  name: "{agent_name}"')
    if agent_instructions:
        lines.append(f'  instructions: "{agent_instructions}"')
    lines.append('  model: "gpt-4o-mini"')
    lines.append("")
    lines.append("channels:")
    for plat in platforms:
        info = PLATFORMS.get(plat, {})
        env_var = info.get("token_env", f"{plat.upper()}_BOT_TOKEN")
        lines.append(f"  {plat}:")
        lines.append(f"    token: ${{{env_var}}}")
        lines.append("    group_policy: mention_only")
        if plat == "whatsapp":
            lines.append("    phone_number_id: ${WHATSAPP_PHONE_NUMBER_ID}")
    lines.append("")
    lines.append("routing:")
    lines.append("  default: assistant")
    lines.append("")
    return "\n".join(lines)


class OnboardWizard:
    """Interactive onboarding wizard using rich prompts."""

    def __init__(self):
        self.selected_platforms: List[str] = []
        self.tokens: Dict[str, str] = {}
        self.agent_name: str = "assistant"
        self.agent_instructions: str = "You are a helpful AI assistant."
        self.config_path: str = "bot.yaml"

    def run(self) -> None:
        """Run the wizard interactively."""
        try:
            from rich.console import Console
            from rich.prompt import Prompt, Confirm
            from rich.panel import Panel
        except ImportError:
            self._run_plain()
            return

        console = Console()

        # Welcome
        console.print(Panel(
            "[bold]Welcome to PraisonAI Bot Setup[/bold]\n\n"
            "This wizard will help you set up your AI bot in a few steps.\n"
            "You'll need a bot token from your chosen platform.",
            title="🤖 PraisonAI Onboard",
            border_style="blue",
        ))

        # Step 1: Platform selection
        console.print("\n[bold]Step 1: Choose your platform(s)[/bold]\n")
        for key, info in PLATFORMS.items():
            console.print(f"  [cyan]{key}[/cyan] — {info['name']}")

        platforms_input = Prompt.ask(
            "\nPlatform(s) [comma-separated]",
            default="telegram",
        )
        self.selected_platforms = [p.strip().lower() for p in platforms_input.split(",") if p.strip()]

        # Validate
        for plat in self.selected_platforms:
            if plat not in PLATFORMS:
                console.print(f"[red]Unknown platform: {plat}[/red]")
                return

        # Step 2: Token configuration
        console.print("\n[bold]Step 2: Configure tokens[/bold]\n")
        for plat in self.selected_platforms:
            info = PLATFORMS[plat]
            env_var = info["token_env"]
            existing = os.environ.get(env_var, "")

            if existing:
                console.print(f"  [green]✓[/green] {info['name']}: {env_var} already set")
                self.tokens[plat] = existing
            else:
                console.print(f"  [dim]{info['token_help']}[/dim]")
                token = Prompt.ask(f"  {info['name']} token ({env_var})")
                if token:
                    self.tokens[plat] = token
                    os.environ[env_var] = token
                    console.print("  [green]✓[/green] Token set for this session")
                else:
                    console.print(f"  [yellow]⚠[/yellow] No token — you'll need to set {env_var} before starting")

            # Extra env vars (e.g., Slack app token)
            for extra_env, extra_desc in info.get("extra_env", {}).items():
                if not os.environ.get(extra_env):
                    extra_val = Prompt.ask(f"  {extra_desc} ({extra_env})", default="")
                    if extra_val:
                        os.environ[extra_env] = extra_val

        # Step 3: Test connection
        console.print("\n[bold]Step 3: Test connection[/bold]\n")
        for plat in self.selected_platforms:
            if plat in self.tokens:
                console.print(f"  Testing {PLATFORMS[plat]['name']}...", end=" ")
                try:
                    result = asyncio.run(self._probe(plat))
                    if result.ok:
                        console.print(f"[green]✓ @{result.bot_username}[/green] ({result.elapsed_ms:.0f}ms)")
                    else:
                        console.print(f"[red]✗ {result.error}[/red]")
                except Exception as e:
                    console.print(f"[red]✗ {str(e)[:100]}[/red]")

        # Step 4: Agent configuration
        console.print("\n[bold]Step 4: Configure your agent[/bold]\n")
        self.agent_name = Prompt.ask("Agent name", default="assistant")
        self.agent_instructions = Prompt.ask(
            "Agent instructions",
            default="You are a helpful AI assistant.",
        )

        # Step 5: Generate config
        console.print("\n[bold]Step 5: Generate configuration[/bold]\n")
        yaml_content = _generate_bot_yaml(
            self.selected_platforms,
            agent_name=self.agent_name,
            agent_instructions=self.agent_instructions,
        )

        self.config_path = Prompt.ask("Config file path", default="bot.yaml")

        if os.path.exists(self.config_path):
            if not Confirm.ask(f"  {self.config_path} exists. Overwrite?", default=False):
                console.print("  [dim]Skipped[/dim]")
                return

        with open(self.config_path, "w") as f:
            f.write(yaml_content)
        console.print(f"  [green]✓[/green] Written to {self.config_path}")

        # Step 6: Optional daemon install
        if Confirm.ask("\nInstall as background service (daemon)?", default=False):
            try:
                from praisonai.daemon import install_daemon
                result = install_daemon(config_path=self.config_path)
                if result.get("ok"):
                    console.print(f"  [green]✓[/green] {result.get('message', 'Service installed')}")
                else:
                    console.print(f"  [red]✗[/red] {result.get('error', 'Install failed')}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {str(e)[:200]}")

        # Done
        console.print(Panel(
            f"[bold green]Setup complete![/bold green]\n\n"
            f"Start your bot:\n"
            f"  [cyan]praisonai bot start --config {self.config_path}[/cyan]\n\n"
            f"Check health:\n"
            f"  [cyan]praisonai doctor[/cyan]\n\n"
            f"View status:\n"
            f"  [cyan]praisonai bot status[/cyan]",
            title="✅ Done",
            border_style="green",
        ))

    async def _probe(self, platform: str):
        """Run a probe for a platform."""
        from praisonai.bots import Bot
        bot = Bot(platform, token=self.tokens.get(platform, ""))
        return await bot.probe()

    def _run_plain(self) -> None:
        """Fallback for when rich is not available."""
        print("\n=== PraisonAI Bot Setup ===\n")
        print("Available platforms: telegram, discord, slack, whatsapp")
        platforms_input = input("Platform(s) [comma-separated, default=telegram]: ").strip() or "telegram"
        self.selected_platforms = [p.strip().lower() for p in platforms_input.split(",")]

        for plat in self.selected_platforms:
            info = PLATFORMS.get(plat, {})
            env_var = info.get("token_env", f"{plat.upper()}_BOT_TOKEN")
            if not os.environ.get(env_var):
                print(f"\n  {info.get('token_help', '')}")
                token = input(f"  {env_var}: ").strip()
                if token:
                    os.environ[env_var] = token
                    self.tokens[plat] = token

        yaml_content = _generate_bot_yaml(self.selected_platforms)
        with open("bot.yaml", "w") as f:
            f.write(yaml_content)
        print("\n✓ Written to bot.yaml")
        print("Start with: praisonai bot start --config bot.yaml")


def run_onboard() -> None:
    """Entry point for 'praisonai onboard' command."""
    wizard = OnboardWizard()
    wizard.run()

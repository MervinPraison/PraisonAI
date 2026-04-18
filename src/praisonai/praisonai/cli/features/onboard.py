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
import getpass
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Platform info for the wizard.
# ``allowed_users_env`` / ``home_channel_env`` mirror the hermes/openclaw
# pattern: a per-platform allowlist of user IDs and a default "home" channel
# for proactive/cron deliveries.
PLATFORMS = {
    "telegram": {
        "name": "Telegram",
        "token_env": "TELEGRAM_BOT_TOKEN",
        "token_help": "Get from @BotFather on Telegram: https://t.me/BotFather",
        "install_hint": "pip install python-telegram-bot",
        "allowed_users_env": "TELEGRAM_ALLOWED_USERS",
        "home_channel_env": "TELEGRAM_HOME_CHANNEL",
        "user_id_help": "Find your user ID by messaging @userinfobot on Telegram",
    },
    "discord": {
        "name": "Discord",
        "token_env": "DISCORD_BOT_TOKEN",
        "token_help": "Create at https://discord.com/developers/applications",
        "install_hint": "pip install discord.py",
        "allowed_users_env": "DISCORD_ALLOWED_USERS",
        "home_channel_env": "DISCORD_HOME_CHANNEL",
        "user_id_help": "Enable Developer Mode (Settings > Advanced), right-click your name > Copy User ID",
    },
    "slack": {
        "name": "Slack",
        "token_env": "SLACK_BOT_TOKEN",
        "token_help": "Create at https://api.slack.com/apps",
        "install_hint": "pip install slack-bolt",
        "extra_env": {"SLACK_APP_TOKEN": "App token (xapp-...)"},
        "allowed_users_env": "SLACK_ALLOWED_USERS",
        "home_channel_env": "SLACK_HOME_CHANNEL",
        "user_id_help": "Your Slack member ID (U...). Profile > More > Copy member ID",
    },
    "whatsapp": {
        "name": "WhatsApp",
        "token_env": "WHATSAPP_ACCESS_TOKEN",
        "token_help": "Get from Meta for Developers: https://developers.facebook.com",
        "install_hint": "pip install aiohttp",
        "extra_env": {"WHATSAPP_PHONE_NUMBER_ID": "Phone number ID"},
        "allowed_users_env": "WHATSAPP_ALLOWED_USERS",
        "home_channel_env": "WHATSAPP_HOME_CHANNEL",
        "user_id_help": "Your WhatsApp phone number in E.164 (e.g. 15551234567, no +)",
    },
}


def _praison_home() -> Path:
    """Return ``$PRAISONAI_HOME`` or ``~/.praisonai``."""
    override = os.environ.get("PRAISONAI_HOME")
    return Path(override) if override else Path.home() / ".praisonai"


def _save_env_vars(env_vars: Dict[str, Optional[str]]) -> Optional[Path]:
    """Atomically merge ``env_vars`` into ``~/.praisonai/.env`` (chmod 600).

    - Non-empty string values are written (updating existing keys).
    - ``None`` values **remove** the key from the file (supports "clear" updates
      so the user can drop an allowlist or home-channel).
    - Empty-string values are skipped.
    Existing keys not referenced in ``env_vars`` are preserved. Written with a
    temp-then-rename to avoid partial writes.
    """
    updates = {k: v for k, v in env_vars.items() if v}
    deletes = {k for k, v in env_vars.items() if v is None}
    if not updates and not deletes:
        return None

    env_file = _praison_home() / ".env"
    try:
        env_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Could not create %s", env_file.parent)
        return None

    existing: Dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                existing[k.strip()] = v.strip()
    existing.update(updates)
    for k in deletes:
        existing.pop(k, None)

    body = ["# PraisonAI configuration",
            "# Managed by praisonai onboard / setup", ""]
    for k in sorted(existing):
        body.append(f"{k}={existing[k]}")

    tmp = env_file.with_name(env_file.name + ".tmp")
    tmp.write_text("\n".join(body) + "\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, env_file)
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass
    return env_file


def _generate_bot_yaml(platforms: List[str], agent_name: str = "assistant", agent_instructions: str = "") -> str:
    """Generate bot.yaml content compatible with BOTH ``praisonai bot start``
    and ``praisonai gateway start``.

    Includes:
      - ``agent:`` (singular) — legacy single-bot schema used by ``bot start``.
      - ``agents:`` (plural) — required by the gateway validator so the same
        file can boot a daemonised gateway (which binds ``/health`` on 8765).
      - ``channels:`` — per-platform, with env-var references so secrets stay
        in ``~/.praisonai/.env``.
    """
    instructions = agent_instructions or "You are a helpful AI assistant."

    lines = ["# Generated by `praisonai onboard`. Works with both",
             "# `praisonai bot start` (single-bot) and `praisonai gateway start`",
             "# (multi-bot daemon exposing /health on 8765).",
             ""]

    # Gateway server block — consumed by `gateway start`, ignored by `bot start`.
    lines.append("gateway:")
    lines.append('  host: "127.0.0.1"')
    lines.append("  port: 8765")
    lines.append("")

    # Legacy single-agent block — consumed by `bot start`.
    lines.append("agent:")
    lines.append(f'  name: "{agent_name}"')
    lines.append(f'  instructions: "{instructions}"')
    lines.append('  model: "gpt-4o-mini"')
    lines.append("")

    # Multi-agent block — REQUIRED by `gateway start`, ignored by `bot start`.
    lines.append("agents:")
    lines.append(f"  {agent_name}:")
    lines.append(f'    instructions: "{instructions}"')
    lines.append('    model: gpt-4o-mini')
    lines.append("    memory: false")
    lines.append("")

    # Channels section — shared by both commands.
    lines.append("channels:")
    for plat in platforms:
        info = PLATFORMS.get(plat, {})
        env_var = info.get("token_env", f"{plat.upper()}_BOT_TOKEN")
        lines.append(f"  {plat}:")
        lines.append(f"    platform: {plat}")
        lines.append(f"    token: ${{{env_var}}}")
        lines.append("    group_policy: mention_only")
        allowed_env = info.get("allowed_users_env")
        if allowed_env:
            lines.append(f"    allowed_users: ${{{allowed_env}}}")
        home_env = info.get("home_channel_env")
        if home_env:
            lines.append(f"    home_channel: ${{{home_env}}}")
        if plat == "whatsapp":
            lines.append("    phone_number_id: ${WHATSAPP_PHONE_NUMBER_ID}")
        # Gateway-style routing (ignored by `bot start` which uses top-level routing).
        lines.append("    routes:")
        lines.append(f"      default: {agent_name}")
    lines.append("")

    # Legacy routing block — consumed by `bot start`.
    lines.append("routing:")
    lines.append(f"  default: {agent_name}")
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

        # Step 2: Token configuration (password-hidden; persisted to ~/.praisonai/.env)
        # Every setting can be updated even if already present — existing values are
        # shown as masked defaults; press Enter to keep, or type a new value to
        # overwrite (mirrors hermes-agent setup behaviour).
        console.print("\n[bold]Step 2: Configure tokens[/bold]\n")
        console.print(
            "  [dim]Press Enter to keep the existing value, or type a new one to update.[/dim]\n"
        )
        env_to_save: Dict[str, Optional[str]] = {}

        def _mask(value: str) -> str:
            if not value:
                return ""
            if len(value) <= 6:
                return "*" * len(value)
            return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"

        for plat in self.selected_platforms:
            info = PLATFORMS[plat]
            env_var = info["token_env"]
            existing = os.environ.get(env_var, "")

            if existing:
                console.print(
                    f"  [green]✓[/green] {info['name']}: {env_var} = [cyan]{_mask(existing)}[/cyan]"
                )
                console.print(f"    [dim]{info['token_help']}[/dim]")
                new_token = Prompt.ask(
                    f"  Update {info['name']} token? (Enter = keep current)",
                    password=True,
                    default="",
                    show_default=False,
                )
                if new_token:
                    self.tokens[plat] = new_token
                    os.environ[env_var] = new_token
                    env_to_save[env_var] = new_token
                    console.print("  [green]✓[/green] Token updated")
                else:
                    self.tokens[plat] = existing
            else:
                console.print(f"  [dim]{info['token_help']}[/dim]")
                token = Prompt.ask(
                    f"  {info['name']} token ({env_var})",
                    password=True,
                    default="",
                    show_default=False,
                )
                if token:
                    self.tokens[plat] = token
                    os.environ[env_var] = token
                    env_to_save[env_var] = token
                    console.print("  [green]✓[/green] Token captured")
                else:
                    console.print(
                        f"  [yellow]⚠[/yellow] No token — you'll need to set {env_var} before starting"
                    )

            # Extra env vars (e.g., Slack app token) — also hidden by default
            for extra_env, extra_desc in info.get("extra_env", {}).items():
                existing_extra = os.environ.get(extra_env, "")
                if existing_extra:
                    console.print(
                        f"    [green]✓[/green] {extra_env} = [cyan]{_mask(existing_extra)}[/cyan]"
                    )
                    new_extra = Prompt.ask(
                        f"    Update {extra_desc}? (Enter = keep current)",
                        password=True,
                        default="",
                        show_default=False,
                    )
                    if new_extra:
                        os.environ[extra_env] = new_extra
                        env_to_save[extra_env] = new_extra
                        console.print(f"    [green]✓[/green] {extra_env} updated")
                else:
                    extra_val = Prompt.ask(
                        f"  {extra_desc} ({extra_env})",
                        password=True,
                        default="",
                        show_default=False,
                    )
                    if extra_val:
                        os.environ[extra_env] = extra_val
                        env_to_save[extra_env] = extra_val

            # Step 2b: Security — allowlist + home channel (mirrors hermes)
            allowed_env = info.get("allowed_users_env")
            home_env = info.get("home_channel_env")
            if allowed_env:
                existing_allow = os.environ.get(allowed_env, "").strip()
                if existing_allow:
                    console.print(
                        f"  [green]✓[/green] {allowed_env} = [cyan]{existing_allow}[/cyan]"
                    )
                    console.print(
                        f"    [dim]{info.get('user_id_help', 'Comma-separated user IDs')}[/dim]"
                    )
                    new_allow = Prompt.ask(
                        f"  Update allowed users for {info['name']}? (Enter = keep, 'clear' = remove)",
                        default="",
                        show_default=False,
                    ).strip()
                    if new_allow.lower() == "clear":
                        os.environ.pop(allowed_env, None)
                        env_to_save[allowed_env] = None
                        console.print(
                            "  [yellow]✓ Allowlist cleared — open access restored[/yellow]"
                        )
                    elif new_allow:
                        new_allow = new_allow.replace(" ", "")
                        os.environ[allowed_env] = new_allow
                        env_to_save[allowed_env] = new_allow
                        console.print("  [green]✓[/green] Allowlist updated")
                else:
                    console.print(
                        f"  [bold]🔒 Security — restrict who can use your {info['name']} bot[/bold]"
                    )
                    console.print(
                        f"  [dim]{info.get('user_id_help', 'Enter comma-separated user IDs')}[/dim]"
                    )
                    allow_val = Prompt.ask(
                        "  Allowed user IDs (comma-separated, empty = open access)",
                        default="",
                        show_default=False,
                    )
                    allow_val = allow_val.replace(" ", "")
                    if allow_val:
                        os.environ[allowed_env] = allow_val
                        env_to_save[allowed_env] = allow_val
                        console.print(
                            "  [green]✓[/green] Allowlist saved — only listed users can talk to the bot"
                        )
                    else:
                        console.print(
                            "  [yellow]⚠  Warning:[/yellow] no allowlist set — anyone who finds your bot can use it."
                        )

                # Home channel (default = first allowed user) — also updatable
                if home_env:
                    existing_home = os.environ.get(home_env, "").strip()
                    first_allowed = ""
                    saved_allow = env_to_save.get(allowed_env, existing_allow)
                    if isinstance(saved_allow, str) and saved_allow:
                        first_allowed = saved_allow.split(",")[0].strip()
                    default_home = existing_home or first_allowed
                    if existing_home:
                        console.print(
                            f"  [green]✓[/green] {home_env} = [cyan]{existing_home}[/cyan]"
                        )
                        prompt_label = (
                            f"  Update home channel for {info['name']}? (Enter = keep current)"
                        )
                    else:
                        prompt_label = (
                            f"  Home channel / user ID for proactive messages ({home_env})"
                        )
                    home_val = Prompt.ask(
                        prompt_label,
                        default=default_home,
                        show_default=bool(default_home),
                    ).strip()
                    if home_val and home_val != existing_home:
                        os.environ[home_env] = home_val
                        env_to_save[home_env] = home_val
                        console.print(f"  [green]✓[/green] Home channel set to {home_val}")

        # Persist everything collected above to ~/.praisonai/.env
        env_file = _save_env_vars(env_to_save)
        if env_file:
            console.print(f"\n  [green]✓[/green] Secrets saved to [cyan]{env_file}[/cyan] (chmod 600)")

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
        # Guard: refuse to install a daemon that has no tokens — it would loop
        # in a crash-restart cycle. List the platforms missing tokens so the
        # user can rerun onboard once they have them.
        missing_tokens = [
            PLATFORMS[p]["name"]
            for p in self.selected_platforms
            if p not in self.tokens
        ]
        if missing_tokens:
            console.print(
                f"\n  [yellow]⚠[/yellow] Skipping daemon install — missing token(s) for: "
                f"[bold]{', '.join(missing_tokens)}[/bold]."
            )
            console.print(
                "  [dim]Re-run [cyan]praisonai onboard[/cyan] once you have the token(s) and "
                "the service will be installed automatically.[/dim]"
            )
        elif Confirm.ask("\nInstall as background service (daemon)?", default=True):
            try:
                from praisonai.daemon import install_daemon
                result = install_daemon(config_path=self.config_path)
                if result.get("ok"):
                    console.print(f"  [green]✓[/green] {result.get('message', 'Service installed')}")
                else:
                    console.print(f"  [red]✗[/red] {result.get('error', 'Install failed')}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {str(e)[:200]}")

        # Done — commands referenced here must exist in `praisonai --help`.
        console.print(Panel(
            f"[bold green]Setup complete![/bold green]\n\n"
            f"Start your bot:\n"
            f"  [cyan]praisonai bot start --config {self.config_path}[/cyan]\n\n"
            f"Check health:\n"
            f"  [cyan]praisonai doctor[/cyan]\n\n"
            f"View gateway status:\n"
            f"  [cyan]praisonai gateway status[/cyan]",
            title="✅ Done",
            border_style="green",
        ))

    async def _probe(self, platform: str):
        """Run a probe for a platform."""
        from praisonai.bots import Bot
        bot = Bot(platform, token=self.tokens.get(platform, ""))
        return await bot.probe()

    def _run_plain(self) -> None:
        """Fallback for when rich is not available.

        Parity with the rich path: hidden token input via ``getpass``,
        allowlist + home-channel prompts, and persistence to
        ``~/.praisonai/.env``.
        """
        print("\n=== PraisonAI Bot Setup ===\n")
        print("Available platforms: telegram, discord, slack, whatsapp")
        platforms_input = input("Platform(s) [comma-separated, default=telegram]: ").strip() or "telegram"
        self.selected_platforms = [p.strip().lower() for p in platforms_input.split(",")]

        env_to_save: Dict[str, str] = {}
        for plat in self.selected_platforms:
            info = PLATFORMS.get(plat, {})
            env_var = info.get("token_env", f"{plat.upper()}_BOT_TOKEN")
            if not os.environ.get(env_var):
                print(f"\n  {info.get('token_help', '')}")
                token = getpass.getpass(f"  {env_var} (hidden): ").strip()
                if token:
                    os.environ[env_var] = token
                    env_to_save[env_var] = token
                    self.tokens[plat] = token

            allowed_env = info.get("allowed_users_env")
            if allowed_env and not os.environ.get(allowed_env):
                print(f"\n  🔒 {info.get('user_id_help', 'Enter allowed user IDs')}")
                allow = input("  Allowed user IDs (comma-separated, empty = open): ").strip().replace(" ", "")
                if allow:
                    os.environ[allowed_env] = allow
                    env_to_save[allowed_env] = allow
                else:
                    print("  ⚠  No allowlist — anyone who finds your bot can use it.")

            home_env = info.get("home_channel_env")
            if home_env and not os.environ.get(home_env):
                first = env_to_save.get(allowed_env, "").split(",")[0].strip() if allowed_env else ""
                prompt_text = f"  Home channel ({home_env})" + (f" [{first}]: " if first else ": ")
                home = input(prompt_text).strip() or first
                if home:
                    os.environ[home_env] = home
                    env_to_save[home_env] = home

        env_file = _save_env_vars(env_to_save)
        yaml_content = _generate_bot_yaml(self.selected_platforms)
        with open("bot.yaml", "w") as f:
            f.write(yaml_content)
        print("\n✓ Written to bot.yaml")
        if env_file:
            print(f"✓ Secrets saved to {env_file} (chmod 600)")
        print("Start with: praisonai bot start --config bot.yaml")


def run_onboard() -> None:
    """Entry point for 'praisonai onboard' command."""
    wizard = OnboardWizard()
    wizard.run()

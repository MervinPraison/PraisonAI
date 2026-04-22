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
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _is_non_interactive() -> bool:
    """Return True when the wizard must not block on user input.

    Triggers on either:
      - ``PRAISONAI_NO_PROMPT=1`` (explicit opt-out; set by the ``--yes``
        CLI flag and by ``install.sh`` when running non-interactively), or
      - ``stdin`` is not a TTY (e.g. piped from a script or CI).

    In non-interactive mode every prompt short-circuits to its declared
    default. Tokens / allowlists already present in the environment are
    preserved; missing values are left blank and the generated
    ``bot.yaml`` simply references the env vars — the user can populate
    them later and re-run ``praisonai onboard --yes`` to finalise setup.
    """
    if os.environ.get("PRAISONAI_NO_PROMPT", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    try:
        if not sys.stdin.isatty():
            return True
    except (AttributeError, ValueError):
        return True
    return False


def _prompt_ask(prompt_cls: Any, *args, **kwargs) -> str:
    """Wrapper around ``rich.prompt.Prompt.ask`` that honours non-interactive mode.

    Returns the declared ``default`` (or empty string) without blocking.
    """
    if _is_non_interactive():
        return kwargs.get("default", "") or ""
    return prompt_cls.ask(*args, **kwargs)


def _confirm_ask(confirm_cls: Any, *args, **kwargs) -> bool:
    """Wrapper around ``rich.prompt.Confirm.ask`` that honours non-interactive mode."""
    if _is_non_interactive():
        return bool(kwargs.get("default", False))
    return confirm_cls.ask(*args, **kwargs)


def _plain_input(msg: str, default: str = "") -> str:
    """Non-blocking ``input()`` replacement for the plain fallback path."""
    if _is_non_interactive():
        return default
    try:
        return input(msg)
    except EOFError:
        return default


def _plain_getpass(msg: str) -> str:
    """Non-blocking ``getpass.getpass()`` replacement for the plain fallback path."""
    if _is_non_interactive():
        return ""
    try:
        return getpass.getpass(msg)
    except EOFError:
        return ""

# Platform info for the wizard. ``allowed_users_env`` is a per-platform
# allowlist of user IDs used by the channel adapter to restrict inbound
# traffic. We deliberately don't carry a ``home_channel_env`` any more:
# no code path in the gateway reads ``home_channel`` today (the scheduler
# uses an explicit DeliveryTarget.channel_id per job), and the prompt
# confused non-developers. If a proactive-delivery feature ships later
# it can reintroduce this on an opt-in basis.
PLATFORMS = {
    "telegram": {
        "name": "Telegram",
        "token_env": "TELEGRAM_BOT_TOKEN",
        "token_help": "Get from @BotFather on Telegram: https://t.me/BotFather",
        "install_hint": "pip install python-telegram-bot",
        "allowed_users_env": "TELEGRAM_ALLOWED_USERS",
        "user_id_help": "Find your user ID by messaging @userinfobot on Telegram",
    },
    "discord": {
        "name": "Discord",
        "token_env": "DISCORD_BOT_TOKEN",
        "token_help": "Create at https://discord.com/developers/applications",
        "install_hint": "pip install discord.py",
        "allowed_users_env": "DISCORD_ALLOWED_USERS",
        "user_id_help": "Enable Developer Mode (Settings > Advanced), right-click your name > Copy User ID",
    },
    "slack": {
        "name": "Slack",
        "token_env": "SLACK_BOT_TOKEN",
        "token_help": "Create at https://api.slack.com/apps",
        "install_hint": "pip install slack-bolt",
        "extra_env": {"SLACK_APP_TOKEN": "App token (xapp-...)"},
        "allowed_users_env": "SLACK_ALLOWED_USERS",
        "user_id_help": "Your Slack member ID (U...). Profile > More > Copy member ID",
    },
    "whatsapp": {
        "name": "WhatsApp",
        "token_env": "WHATSAPP_ACCESS_TOKEN",
        "token_help": "Get from Meta for Developers: https://developers.facebook.com",
        "install_hint": "pip install aiohttp",
        "extra_env": {"WHATSAPP_PHONE_NUMBER_ID": "Phone number ID"},
        "allowed_users_env": "WHATSAPP_ALLOWED_USERS",
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
    - ``None`` values **remove** the key from the file (supports "clear" updates,
      e.g. dropping an allowlist).
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


def _read_env_value(key: str) -> Optional[str]:
    """Read a single value from ``~/.praisonai/.env`` (if present)."""
    env_file = _praison_home() / ".env"
    if not env_file.exists():
        return None
    try:
        for line in env_file.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None


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

        non_interactive = _is_non_interactive()

        # Welcome
        console.print(Panel(
            "[bold]Welcome to PraisonAI Bot Setup[/bold]\n\n"
            "This wizard will help you set up your AI bot in a few steps.\n"
            "You'll need a bot token from your chosen platform.",
            title="🤖 PraisonAI Onboard",
            border_style="blue",
        ))
        if non_interactive:
            console.print(
                "[dim]Non-interactive mode (PRAISONAI_NO_PROMPT=1 or --yes). "
                "Tokens/allowlists taken from env vars; missing values left blank. "
                "Existing bot.yaml will be kept (no overwrite).[/dim]"
            )

        # Step 1: Platform selection
        console.print("\n[bold]Step 1: Choose your platform(s)[/bold]\n")
        for key, info in PLATFORMS.items():
            console.print(f"  [cyan]{key}[/cyan] — {info['name']}")

        platforms_input = _prompt_ask(
            Prompt,
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
                new_token = _prompt_ask(
                    Prompt,
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
                token = _prompt_ask(
                    Prompt,
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
                    new_extra = _prompt_ask(
                        Prompt,
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
                    extra_val = _prompt_ask(
                        Prompt,
                        f"  {extra_desc} ({extra_env})",
                        password=True,
                        default="",
                        show_default=False,
                    )
                    if extra_val:
                        os.environ[extra_env] = extra_val
                        env_to_save[extra_env] = extra_val

            # Step 2b: Security — allowlist (mirrors hermes)
            allowed_env = info.get("allowed_users_env")
            if allowed_env:
                existing_allow = os.environ.get(allowed_env, "").strip()
                if existing_allow:
                    console.print(
                        f"  [green]✓[/green] {allowed_env} = [cyan]{existing_allow}[/cyan]"
                    )
                    console.print(
                        f"    [dim]{info.get('user_id_help', 'Comma-separated user IDs')}[/dim]"
                    )
                    new_allow = _prompt_ask(
                        Prompt,
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
                    allow_val = _prompt_ask(
                        Prompt,
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

                # Home-channel prompt intentionally removed — see PLATFORMS
                # docstring above. No code path consumes home_channel today.

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
        #
        # We no longer ask for an agent name and instructions up-front:
        # 95% of first-time users pressed Enter through both prompts, and
        # the remaining 5% are better served editing the generated bot.yaml
        # afterwards (which also shows them the full schema). Defaults are
        # already set in __init__.
        console.print(
            "\n[bold]Step 4: Agent defaults applied[/bold] "
            f"[dim](name=[cyan]{self.agent_name}[/cyan], "
            f"instructions=[cyan]{self.agent_instructions!r}[/cyan] — "
            "edit bot.yaml to customise)[/dim]"
        )

        # Step 4b: Ensure a stable GATEWAY_AUTH_TOKEN is persisted. Without
        # this the gateway server auto-generates a random token on every
        # start (see server.py _check_auth), which means the dashboard link
        # we show in the Done panel would rotate each restart. Persisting
        # one value to ~/.praisonai/.env keeps clicks working across
        # daemon restarts.
        existing_gateway_token = _read_env_value("GATEWAY_AUTH_TOKEN")
        if not existing_gateway_token:
            import secrets as _secrets
            self._gateway_token = _secrets.token_hex(16)
            _save_env_vars({"GATEWAY_AUTH_TOKEN": self._gateway_token})
        else:
            self._gateway_token = existing_gateway_token

        # Step 5: Generate config
        #
        # We write to the canonical default path without asking. An earlier
        # free-text "Config file path" prompt caused real user pain: typing
        # 'n' (meaning 'no') created a literal file named ``n`` in cwd. The
        # canonical path is discoverable via ``praisonai doctor`` and is
        # honoured by both ``praisonai bot start`` and ``praisonai gateway
        # start`` with zero flags. Overwrite-confirm still guards existing
        # configs so power users who hand-edited the file aren't surprised.
        console.print("\n[bold]Step 5: Generate configuration[/bold]\n")
        yaml_content = _generate_bot_yaml(
            self.selected_platforms,
            agent_name=self.agent_name,
            agent_instructions=self.agent_instructions,
        )

        from praisonai.cli._paths import default_bot_config_path
        self.config_path = str(default_bot_config_path())
        os.makedirs(os.path.dirname(os.path.abspath(self.config_path)) or ".", exist_ok=True)

        if os.path.exists(self.config_path):
            if not _confirm_ask(
                Confirm,
                f"  {self.config_path} exists. Overwrite with fresh config?",
                default=False,
            ):
                console.print("  [dim]Kept existing file[/dim]")
                return

        with open(self.config_path, "w") as f:
            f.write(yaml_content)
        console.print(f"  [green]✓[/green] Written to [cyan]{self.config_path}[/cyan]")

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
        else:
            # Install the daemon by default — no prompt. The previous
            # "Install as background service (daemon)? [Y/n]" question
            # confused non-developer users ("what does daemon mean?") and
            # 95% answered Yes anyway. If they really don't want it, they
            # run `praisonai gateway uninstall` afterwards. This keeps the
            # onboarding 'do-the-thing-for-me' feel instead of 'quiz me'.
            daemon_success = self._install_daemon_with_feedback(
                console.print, self.config_path
            )
        
        if 'daemon_success' not in locals():
            daemon_success = False

        # Done panel. Commands referenced here must exist in `praisonai --help`.
        # OS-aware daemon management hints: non-developers struggle to find
        # launchctl/systemctl invocations themselves, so we surface the exact
        # line for their platform. Label ``ai.praison.bot`` is used for launchd,
        # while ``praisonai-bot`` is used for systemd.
        _tok = getattr(self, "_gateway_token", "")
        _masked = (_tok[:4] + "…" + _tok[-4:]) if len(_tok) >= 10 else "(set)"
        _health_url = "http://127.0.0.1:8765/health"
        _info_url = (
            f"http://127.0.0.1:8765/info?token={_tok}"
            if _tok
            else "http://127.0.0.1:8765/info"
        )
        import platform as _platform  # stdlib, free
        _os = _platform.system().lower()
        if _os == "darwin":
            _restart_cmd = "launchctl kickstart -k gui/$(id -u)/ai.praison.bot"
        elif _os == "linux":
            _restart_cmd = "systemctl --user restart praisonai-bot"
        elif _os == "windows":
            _restart_cmd = "schtasks /End /TN PraisonAIGateway && schtasks /Run /TN PraisonAIGateway"
        else:
            _restart_cmd = "praisonai gateway install  # re-run installer"
        # Adjust headline based on daemon install success
        daemon_running_text = (
            "Your bot is now running in the background." if daemon_success
            else "Configuration complete."
        )
        
        console.print(Panel(
            f"[bold green]Setup complete![/bold green] "
            f"[dim]{daemon_running_text}[/dim]\n\n"
            f"[bold]🦞 Dashboard UI:[/bold]\n"
            f"  [cyan]praisonai claw[/cyan]          [dim]→ http://127.0.0.1:8082[/dim]\n\n"
            f"[bold]Gateway endpoints:[/bold]\n"
            f"  Health (public):  [cyan]{_health_url}[/cyan]\n"
            f"  Info (authed):    [cyan]{_info_url}[/cyan]\n"
            f"  [dim]Token {_masked} stored in ~/.praisonai/.env as GATEWAY_AUTH_TOKEN[/dim]\n\n"
            f"[bold]Manage the daemon:[/bold]\n"
            f"  [cyan]praisonai gateway status[/cyan]     [dim]# is it running?[/dim]\n"
            f"  [cyan]praisonai gateway logs[/cyan]       [dim]# tail the logs[/dim]\n"
            f"  [cyan]{_restart_cmd}[/cyan]\n"
            f"  [cyan]praisonai gateway uninstall[/cyan]  [dim]# remove the daemon[/dim]\n\n"
            f"[bold]Re-run or reconfigure:[/bold]\n"
            f"  [cyan]praisonai onboard[/cyan]            [dim]# change tokens / add platforms[/dim]\n"
            f"  [cyan]praisonai gateway start[/cyan]      [dim]# run in foreground (skip the daemon)[/dim]\n"
            f"  [cyan]praisonai doctor[/cyan]             [dim]# diagnose the whole stack[/dim]",
            title="✅ Done",
            border_style="green",
        ))

    async def _probe(self, platform: str):
        """Run a probe for a platform."""
        from praisonai.bots import Bot
        bot = Bot(platform, token=self.tokens.get(platform, ""))
        return await bot.probe()

    def _install_daemon_with_feedback(self, print_fn, config_path: str) -> bool:
        """Install daemon with error handling and feedback. Returns success status."""
        try:
            # First check if already installed to make idempotent
            from praisonai.daemon import get_daemon_status, install_daemon
            status = get_daemon_status()
            if status.get("installed") and status.get("running"):
                print_fn(
                    "  ✓ Daemon already installed and running"
                )
                return True
            
            result = install_daemon(config_path=config_path)
            if result.get("ok"):
                print_fn(
                    f"  ✓ {result.get('message', 'Service installed')}"
                )
                return True
            else:
                print_fn(
                    f"  ✗ {result.get('error', 'Install failed')}"
                )
                return False
        except Exception as e:
            print_fn(f"  ✗ {str(e)[:200]}")
            return False

    def _run_plain(self) -> None:
        """Fallback for when rich is not available.

        Parity with the rich path: hidden token input via ``getpass``,
        allowlist prompt, and persistence to
        ``~/.praisonai/.env``.
        """
        print("\n=== PraisonAI Bot Setup ===\n")
        print("Available platforms: telegram, discord, slack, whatsapp")
        platforms_input = _plain_input(
            "Platform(s) [comma-separated, default=telegram]: ",
            default="telegram",
        ).strip() or "telegram"
        self.selected_platforms = [p.strip().lower() for p in platforms_input.split(",")]

        env_to_save: Dict[str, str] = {}
        for plat in self.selected_platforms:
            info = PLATFORMS.get(plat, {})
            env_var = info.get("token_env", f"{plat.upper()}_BOT_TOKEN")
            existing = os.environ.get(env_var)
            if existing:
                self.tokens[plat] = existing
            else:
                print(f"\n  {info.get('token_help', '')}")
                token = _plain_getpass(f"  {env_var} (hidden): ").strip()
                if token:
                    os.environ[env_var] = token
                    env_to_save[env_var] = token
                    self.tokens[plat] = token

            allowed_env = info.get("allowed_users_env")
            if allowed_env and not os.environ.get(allowed_env):
                print(f"\n  🔒 {info.get('user_id_help', 'Enter allowed user IDs')}")
                allow = _plain_input(
                    "  Allowed user IDs (comma-separated, empty = open): ",
                    default="",
                ).strip().replace(" ", "")
                if allow:
                    os.environ[allowed_env] = allow
                    env_to_save[allowed_env] = allow
                else:
                    print("  ⚠  No allowlist — anyone who finds your bot can use it.")

            # Home-channel prompt intentionally removed — see PLATFORMS
            # docstring above. No code path consumes home_channel today.

        env_file = _save_env_vars(env_to_save)
        yaml_content = _generate_bot_yaml(self.selected_platforms)
        from praisonai.cli._paths import default_bot_config_path
        cfg_path = default_bot_config_path()
        os.makedirs(cfg_path.parent, exist_ok=True)
        with open(cfg_path, "w") as f:
            f.write(yaml_content)
        print(f"\n✓ Written to {cfg_path}")
        if env_file:
            print(f"✓ Secrets saved to {env_file} (chmod 600)")

        # Parity with rich flow: install daemon by default (no prompt)
        # when every selected platform has a token captured.
        if self.selected_platforms and all(
            p in self.tokens or os.environ.get(
                PLATFORMS.get(p, {}).get("token_env", f"{p.upper()}_BOT_TOKEN")
            )
            for p in self.selected_platforms
        ):
            self._install_daemon_with_feedback(print, str(cfg_path))

        print("\nNext steps:")
        print("  praisonai gateway status     # check if the daemon is running")
        print("  praisonai gateway logs       # see what the bot is doing")
        print("  praisonai onboard            # change tokens / add platforms")
        print(f"  praisonai gateway start --config {cfg_path}   # foreground run (no daemon)")


def run_onboard() -> None:
    """Entry point for 'praisonai onboard' command."""
    wizard = OnboardWizard()
    wizard.run()

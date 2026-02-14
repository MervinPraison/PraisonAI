"""
Bot command group for PraisonAI CLI.

Provides commands for starting messaging bots with full agent capabilities.
Inspired by moltbot's comprehensive CLI options.
"""

from typing import List, Optional

import typer

app = typer.Typer(
    help="Start messaging bots with full agent capabilities",
    no_args_is_help=True,
)


def _common_options():
    """Common options for all bot commands."""
    pass


@app.command("start")
def bot_start(
    config: str = typer.Option(..., "--config", "-c", help="Path to bot YAML config file"),
):
    """Start a bot from a single YAML config file (zero-code).
    
    The config file contains platform, token, and agent settings all in one place.
    
    Examples:
        praisonai bot start --config bot.yaml
        praisonai bot start -c my-telegram-bot.yaml
    """
    from ..features.bots_cli import BotHandler
    
    handler = BotHandler()
    handler.start_from_config(config)


@app.command("telegram")
def bot_telegram(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Telegram bot token", envvar="TELEGRAM_BOT_TOKEN"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent YAML configuration file"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    browser: bool = typer.Option(False, "--browser", help="Enable browser control"),
    browser_profile: str = typer.Option("default", "--browser-profile", help="Browser profile name"),
    browser_headless: bool = typer.Option(False, "--browser-headless", help="Run browser headless"),
    tools: Optional[List[str]] = typer.Option(None, "--tools", help="Tools to enable"),
    skills: Optional[List[str]] = typer.Option(None, "--skills", help="Skills to enable"),
    skills_dir: Optional[str] = typer.Option(None, "--skills-dir", help="Custom skills directory"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    memory_provider: str = typer.Option("default", "--memory-provider", help="Memory provider"),
    knowledge: bool = typer.Option(False, "--knowledge", help="Enable knowledge/RAG"),
    knowledge_sources: Optional[List[str]] = typer.Option(None, "--knowledge-sources", help="Knowledge sources"),
    web_search: bool = typer.Option(False, "--web", "--web-search", help="Enable web search"),
    web_provider: str = typer.Option("duckduckgo", "--web-provider", help="Web search provider"),
    sandbox: bool = typer.Option(False, "--sandbox", help="Enable sandbox mode"),
    exec_enabled: bool = typer.Option(False, "--exec", help="Enable exec tool"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Auto-approve all tool executions"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Session ID"),
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    thinking: Optional[str] = typer.Option(None, "--thinking", help="Thinking mode (off, minimal, low, medium, high)"),
    tts: bool = typer.Option(False, "--tts", help="Enable TTS tool for text-to-speech"),
    tts_voice: str = typer.Option("alloy", "--tts-voice", help="TTS voice (alloy, echo, fable, onyx, nova, shimmer)"),
    tts_model: Optional[str] = typer.Option(None, "--tts-model", help="TTS model (default: openai/tts-1)"),
    auto_tts: bool = typer.Option(False, "--auto-tts", help="Auto-convert all responses to speech"),
    stt: bool = typer.Option(False, "--stt", help="Enable STT tool for speech-to-text"),
    stt_model: Optional[str] = typer.Option(None, "--stt-model", help="STT model (default: openai/whisper-1)"),
):
    """Start a Telegram bot with full agent capabilities.
    
    Examples:
        praisonai bot telegram --token $TELEGRAM_BOT_TOKEN
        praisonai bot telegram --agent agents.yaml --browser --web
        praisonai bot telegram --tools DuckDuckGoTool WikipediaTool --memory
    """
    from ..features.bots_cli import BotHandler, BotCapabilities
    
    capabilities = BotCapabilities(
        browser=browser,
        browser_profile=browser_profile,
        browser_headless=browser_headless,
        tools=tools or [],
        skills=skills or [],
        skills_dir=skills_dir,
        memory=memory,
        memory_provider=memory_provider,
        knowledge=knowledge,
        knowledge_sources=knowledge_sources or [],
        web_search=web_search,
        web_search_provider=web_provider,
        sandbox=sandbox,
        exec_enabled=exec_enabled,
        auto_approve=auto_approve,
        model=model,
        thinking=thinking,
        tts=tts,
        tts_voice=tts_voice,
        tts_model=tts_model,
        auto_tts=auto_tts,
        stt=stt,
        stt_model=stt_model,
        session_id=session_id,
        user_id=user_id,
    )
    
    handler = BotHandler()
    handler.start_telegram(token=token, agent_file=agent, capabilities=capabilities)


@app.command("discord")
def bot_discord(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Discord bot token", envvar="DISCORD_BOT_TOKEN"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent YAML configuration file"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    browser: bool = typer.Option(False, "--browser", help="Enable browser control"),
    browser_profile: str = typer.Option("default", "--browser-profile", help="Browser profile name"),
    browser_headless: bool = typer.Option(False, "--browser-headless", help="Run browser headless"),
    tools: Optional[List[str]] = typer.Option(None, "--tools", help="Tools to enable"),
    skills: Optional[List[str]] = typer.Option(None, "--skills", help="Skills to enable"),
    skills_dir: Optional[str] = typer.Option(None, "--skills-dir", help="Custom skills directory"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    memory_provider: str = typer.Option("default", "--memory-provider", help="Memory provider"),
    knowledge: bool = typer.Option(False, "--knowledge", help="Enable knowledge/RAG"),
    knowledge_sources: Optional[List[str]] = typer.Option(None, "--knowledge-sources", help="Knowledge sources"),
    web_search: bool = typer.Option(False, "--web", "--web-search", help="Enable web search"),
    web_provider: str = typer.Option("duckduckgo", "--web-provider", help="Web search provider"),
    sandbox: bool = typer.Option(False, "--sandbox", help="Enable sandbox mode"),
    exec_enabled: bool = typer.Option(False, "--exec", help="Enable exec tool"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Auto-approve all tool executions"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Session ID"),
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    thinking: Optional[str] = typer.Option(None, "--thinking", help="Thinking mode (off, minimal, low, medium, high)"),
    tts: bool = typer.Option(False, "--tts", help="Enable TTS tool for text-to-speech"),
    tts_voice: str = typer.Option("alloy", "--tts-voice", help="TTS voice (alloy, echo, fable, onyx, nova, shimmer)"),
    tts_model: Optional[str] = typer.Option(None, "--tts-model", help="TTS model (default: openai/tts-1)"),
    auto_tts: bool = typer.Option(False, "--auto-tts", help="Auto-convert all responses to speech"),
    stt: bool = typer.Option(False, "--stt", help="Enable STT tool for speech-to-text"),
    stt_model: Optional[str] = typer.Option(None, "--stt-model", help="STT model (default: openai/whisper-1)"),
):
    """Start a Discord bot with full agent capabilities.
    
    Examples:
        praisonai bot discord --token $DISCORD_BOT_TOKEN
        praisonai bot discord --agent agents.yaml --browser --web
        praisonai bot discord --tools DuckDuckGoTool --memory
    """
    from ..features.bots_cli import BotHandler, BotCapabilities
    
    capabilities = BotCapabilities(
        browser=browser,
        browser_profile=browser_profile,
        browser_headless=browser_headless,
        tools=tools or [],
        skills=skills or [],
        skills_dir=skills_dir,
        memory=memory,
        memory_provider=memory_provider,
        knowledge=knowledge,
        knowledge_sources=knowledge_sources or [],
        web_search=web_search,
        web_search_provider=web_provider,
        sandbox=sandbox,
        exec_enabled=exec_enabled,
        auto_approve=auto_approve,
        model=model,
        thinking=thinking,
        tts=tts,
        tts_voice=tts_voice,
        tts_model=tts_model,
        auto_tts=auto_tts,
        stt=stt,
        stt_model=stt_model,
        session_id=session_id,
        user_id=user_id,
    )
    
    handler = BotHandler()
    handler.start_discord(token=token, agent_file=agent, capabilities=capabilities)


@app.command("slack")
def bot_slack(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Slack bot token", envvar="SLACK_BOT_TOKEN"),
    app_token: Optional[str] = typer.Option(None, "--app-token", help="Slack app token for Socket Mode", envvar="SLACK_APP_TOKEN"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent YAML configuration file"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    browser: bool = typer.Option(False, "--browser", help="Enable browser control"),
    browser_profile: str = typer.Option("default", "--browser-profile", help="Browser profile name"),
    browser_headless: bool = typer.Option(False, "--browser-headless", help="Run browser headless"),
    tools: Optional[List[str]] = typer.Option(None, "--tools", help="Tools to enable"),
    skills: Optional[List[str]] = typer.Option(None, "--skills", help="Skills to enable"),
    skills_dir: Optional[str] = typer.Option(None, "--skills-dir", help="Custom skills directory"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    memory_provider: str = typer.Option("default", "--memory-provider", help="Memory provider"),
    knowledge: bool = typer.Option(False, "--knowledge", help="Enable knowledge/RAG"),
    knowledge_sources: Optional[List[str]] = typer.Option(None, "--knowledge-sources", help="Knowledge sources"),
    web_search: bool = typer.Option(False, "--web", "--web-search", help="Enable web search"),
    web_provider: str = typer.Option("duckduckgo", "--web-provider", help="Web search provider"),
    sandbox: bool = typer.Option(False, "--sandbox", help="Enable sandbox mode"),
    exec_enabled: bool = typer.Option(False, "--exec", help="Enable exec tool"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Auto-approve all tool executions"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Session ID"),
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    thinking: Optional[str] = typer.Option(None, "--thinking", help="Thinking mode (off, minimal, low, medium, high)"),
    tts: bool = typer.Option(False, "--tts", help="Enable TTS tool for text-to-speech"),
    tts_voice: str = typer.Option("alloy", "--tts-voice", help="TTS voice (alloy, echo, fable, onyx, nova, shimmer)"),
    tts_model: Optional[str] = typer.Option(None, "--tts-model", help="TTS model (default: openai/tts-1)"),
    auto_tts: bool = typer.Option(False, "--auto-tts", help="Auto-convert all responses to speech"),
    stt: bool = typer.Option(False, "--stt", help="Enable STT tool for speech-to-text"),
    stt_model: Optional[str] = typer.Option(None, "--stt-model", help="STT model (default: openai/whisper-1)"),
):
    """Start a Slack bot with full agent capabilities.
    
    Examples:
        praisonai bot slack --token $SLACK_BOT_TOKEN
        praisonai bot slack --agent agents.yaml --browser --web
        praisonai bot slack --tools DuckDuckGoTool --memory --app-token $SLACK_APP_TOKEN
    """
    from ..features.bots_cli import BotHandler, BotCapabilities
    
    capabilities = BotCapabilities(
        browser=browser,
        browser_profile=browser_profile,
        browser_headless=browser_headless,
        tools=tools or [],
        skills=skills or [],
        skills_dir=skills_dir,
        memory=memory,
        memory_provider=memory_provider,
        knowledge=knowledge,
        knowledge_sources=knowledge_sources or [],
        web_search=web_search,
        web_search_provider=web_provider,
        sandbox=sandbox,
        exec_enabled=exec_enabled,
        auto_approve=auto_approve,
        model=model,
        thinking=thinking,
        tts=tts,
        tts_voice=tts_voice,
        tts_model=tts_model,
        auto_tts=auto_tts,
        stt=stt,
        stt_model=stt_model,
        session_id=session_id,
        user_id=user_id,
    )
    
    handler = BotHandler()
    handler.start_slack(token=token, app_token=app_token, agent_file=agent, capabilities=capabilities)


@app.command("whatsapp")
def bot_whatsapp(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="WhatsApp access token (Cloud mode)", envvar="WHATSAPP_ACCESS_TOKEN"),
    phone_id: Optional[str] = typer.Option(None, "--phone-id", help="WhatsApp phone number ID (Cloud mode)", envvar="WHATSAPP_PHONE_NUMBER_ID"),
    verify_token: Optional[str] = typer.Option(None, "--verify-token", help="Webhook verification token (Cloud mode)", envvar="WHATSAPP_VERIFY_TOKEN"),
    port: int = typer.Option(8080, "--port", "-p", help="Webhook server port (Cloud mode)"),
    mode: str = typer.Option("cloud", "--mode", help="Connection mode: 'cloud' (Meta API) or 'web' (QR scan, experimental)"),
    creds_dir: Optional[str] = typer.Option(None, "--creds-dir", help="Credentials directory for Web mode"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent YAML configuration file"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    browser: bool = typer.Option(False, "--browser", help="Enable browser control"),
    browser_profile: str = typer.Option("default", "--browser-profile", help="Browser profile name"),
    browser_headless: bool = typer.Option(False, "--browser-headless", help="Run browser headless"),
    tools: Optional[List[str]] = typer.Option(None, "--tools", help="Tools to enable"),
    skills: Optional[List[str]] = typer.Option(None, "--skills", help="Skills to enable"),
    skills_dir: Optional[str] = typer.Option(None, "--skills-dir", help="Custom skills directory"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    memory_provider: str = typer.Option("default", "--memory-provider", help="Memory provider"),
    knowledge: bool = typer.Option(False, "--knowledge", help="Enable knowledge/RAG"),
    knowledge_sources: Optional[List[str]] = typer.Option(None, "--knowledge-sources", help="Knowledge sources"),
    web_search: bool = typer.Option(False, "--web", "--web-search", help="Enable web search"),
    web_provider: str = typer.Option("duckduckgo", "--web-provider", help="Web search provider"),
    sandbox: bool = typer.Option(False, "--sandbox", help="Enable sandbox mode"),
    exec_enabled: bool = typer.Option(False, "--exec", help="Enable exec tool"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Auto-approve all tool executions"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Session ID"),
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    thinking: Optional[str] = typer.Option(None, "--thinking", help="Thinking mode (off, minimal, low, medium, high)"),
    tts: bool = typer.Option(False, "--tts", help="Enable TTS tool for text-to-speech"),
    tts_voice: str = typer.Option("alloy", "--tts-voice", help="TTS voice (alloy, echo, fable, onyx, nova, shimmer)"),
    tts_model: Optional[str] = typer.Option(None, "--tts-model", help="TTS model (default: openai/tts-1)"),
    auto_tts: bool = typer.Option(False, "--auto-tts", help="Auto-convert all responses to speech"),
    stt: bool = typer.Option(False, "--stt", help="Enable STT tool for speech-to-text"),
    stt_model: Optional[str] = typer.Option(None, "--stt-model", help="STT model (default: openai/whisper-1)"),
    respond_to: Optional[str] = typer.Option(None, "--respond-to", help="Comma-separated phone numbers the bot responds to (besides self)"),
    respond_to_groups: Optional[str] = typer.Option(None, "--respond-to-groups", help="Comma-separated group JIDs the bot responds in"),
    respond_to_all: bool = typer.Option(False, "--respond-to-all", help="Respond to ALL messages (default: self-only)"),
):
    """Start a WhatsApp bot with full agent capabilities.
    
    Cloud mode (default): Webhook server for Meta Cloud API.
    Web mode (experimental): QR code scan, no tokens needed.
    
    Examples:
        praisonai bot whatsapp --token $WHATSAPP_ACCESS_TOKEN --phone-id $WHATSAPP_PHONE_NUMBER_ID
        praisonai bot whatsapp --mode web
        praisonai bot whatsapp --mode web --creds-dir ~/.myapp/wa-creds
        praisonai bot whatsapp --agent agents.yaml --memory --web
    """
    from ..features.bots_cli import BotHandler, BotCapabilities
    
    capabilities = BotCapabilities(
        browser=browser,
        browser_profile=browser_profile,
        browser_headless=browser_headless,
        tools=tools or [],
        skills=skills or [],
        skills_dir=skills_dir,
        memory=memory,
        memory_provider=memory_provider,
        knowledge=knowledge,
        knowledge_sources=knowledge_sources or [],
        web_search=web_search,
        web_search_provider=web_provider,
        sandbox=sandbox,
        exec_enabled=exec_enabled,
        auto_approve=auto_approve,
        model=model,
        thinking=thinking,
        tts=tts,
        tts_voice=tts_voice,
        tts_model=tts_model,
        auto_tts=auto_tts,
        stt=stt,
        stt_model=stt_model,
        session_id=session_id,
        user_id=user_id,
    )
    
    # Parse comma-separated filtering values
    allowed_numbers = [n.strip() for n in respond_to.split(",") if n.strip()] if respond_to else None
    allowed_groups = [g.strip() for g in respond_to_groups.split(",") if g.strip()] if respond_to_groups else None
    
    handler = BotHandler()
    handler.start_whatsapp(
        token=token,
        phone_number_id=phone_id,
        verify_token=verify_token,
        webhook_port=port,
        agent_file=agent,
        capabilities=capabilities,
        mode=mode,
        creds_dir=creds_dir,
        allowed_numbers=allowed_numbers,
        allowed_groups=allowed_groups,
        respond_to_all=respond_to_all,
    )


@app.callback(invoke_without_command=True)
def bot_callback(ctx: typer.Context):
    """Show bot help if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Bot - Messaging Bots with Full Agent Capabilities[/bold cyan]

Start a bot on any platform with: praisonai bot <platform>

[bold]Platforms:[/bold]
  [green]telegram[/green]    Telegram Bot API
  [green]discord[/green]     Discord Bot API  
  [green]slack[/green]       Slack Socket Mode
  [green]whatsapp[/green]    WhatsApp Cloud API or Web mode (QR scan)

[bold]Capability Options (all platforms):[/bold]
  [yellow]--agent FILE[/yellow]          Agent YAML configuration
  [yellow]--model MODEL[/yellow]         LLM model to use
  [yellow]--browser[/yellow]             Enable browser control
  [yellow]--web[/yellow]                 Enable web search
  [yellow]--memory[/yellow]              Enable memory
  [yellow]--knowledge[/yellow]           Enable knowledge/RAG
  [yellow]--tools TOOL...[/yellow]       Enable specific tools
  [yellow]--sandbox[/yellow]             Enable sandbox mode
  [yellow]--auto-approve[/yellow]        Auto-approve all tool executions
  [yellow]--tts[/yellow]                 Enable TTS tool
  [yellow]--stt[/yellow]                 Enable STT tool
  [yellow]--auto-tts[/yellow]            Auto-convert responses to speech

[bold]Zero-Code Mode (YAML config):[/bold]
  praisonai bot start --config bot.yaml

[bold]Examples:[/bold]
  praisonai bot telegram --token $TELEGRAM_BOT_TOKEN
  praisonai bot slack --agent agents.yaml --browser --web
  praisonai bot discord --tools DuckDuckGoTool --memory --model gpt-4o
  praisonai bot whatsapp --token $WHATSAPP_ACCESS_TOKEN --phone-id $WHATSAPP_PHONE_NUMBER_ID
  praisonai bot whatsapp --mode web
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)

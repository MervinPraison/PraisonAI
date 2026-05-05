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
    config: str = typer.Option(
        "bot.yaml", "--config", "-c",
        help="Path to bot YAML config file (defaults to ./bot.yaml if present, else ~/.praisonai/bot.yaml)",
    ),
):
    """Start a bot from a single YAML config file (zero-code).

    The config file contains platform, token, and agent settings all in one place.
    Resolution order when ``--config`` is not given:
    ``./bot.yaml`` (back-compat) → ``~/.praisonai/bot.yaml`` (canonical).

    Examples:
        praisonai bot start                              # auto-detect
        praisonai bot start --config ~/.praisonai/bot.yaml
        praisonai bot start -c my-telegram-bot.yaml
    """
    from .._paths import resolve_bot_config_path
    from ..features.bots_cli import BotHandler

    resolved = resolve_bot_config_path(config)
    handler = BotHandler()
    handler.start_from_config(resolved)


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
    respond_to: Optional[List[str]] = typer.Option(None, "--respond-to", help="Phone numbers the bot responds to (besides self). Repeat or comma-separate."),
    respond_to_groups: Optional[List[str]] = typer.Option(None, "--respond-to-groups", help="Group JIDs the bot responds in. Repeat or comma-separate."),
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
    
    # Parse filtering values — support both repeated flags and comma-separated
    allowed_numbers = None
    if respond_to:
        allowed_numbers = [n.strip() for raw in respond_to for n in raw.split(",") if n.strip()]
    allowed_groups = None
    if respond_to_groups:
        allowed_groups = [g.strip() for raw in respond_to_groups for g in raw.split(",") if g.strip()]
    
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


@app.command("linear")
def bot_linear(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Linear OAuth token", envvar="LINEAR_OAUTH_TOKEN"),
    signing_secret: Optional[str] = typer.Option(None, "--signing-secret", help="Linear webhook signing secret", envvar="LINEAR_WEBHOOK_SECRET"),
    port: int = typer.Option(8080, "--port", "-p", help="Webhook server port"),
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
):
    """Start a Linear bot with full agent capabilities.
    
    Handles Linear AgentSession webhooks for issue mentions and assignments.
    
    Examples:
        praisonai bot linear --token $LINEAR_OAUTH_TOKEN --signing-secret $LINEAR_WEBHOOK_SECRET
        praisonai bot linear --agent agents.yaml --memory --web --tools linear_tools
    """
    from ..features.bots_cli import BotHandler, BotCapabilities
    
    capabilities = BotCapabilities(
        model=model,
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
        session_id=session_id,
        user_id=user_id,
        thinking=thinking,
    )
    
    handler = BotHandler()
    handler.start_linear(
        token=token,
        signing_secret=signing_secret,
        webhook_port=port,
        agent_file=agent,
        capabilities=capabilities,
    )


@app.command("email")
def bot_email(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Email app password", envvar="EMAIL_APP_PASSWORD"),
    email_address: Optional[str] = typer.Option(None, "--email", help="Email address", envvar="EMAIL_ADDRESS"),
    imap_server: Optional[str] = typer.Option(None, "--imap", help="IMAP server"),
    smtp_server: Optional[str] = typer.Option(None, "--smtp", help="SMTP server"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent YAML configuration file"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    tools: Optional[List[str]] = typer.Option(None, "--tools", help="Tools to enable"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    knowledge: bool = typer.Option(False, "--knowledge", help="Enable knowledge/RAG"),
    web_search: bool = typer.Option(False, "--web", "--web-search", help="Enable web search"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Auto-approve all tool executions"),
):
    """Start an Email bot (IMAP/SMTP).
    
    Examples:
        praisonai bot email --token $EMAIL_APP_PASSWORD --email user@gmail.com
        praisonai bot email --agent agents.yaml --memory
    """
    from ..features.bots_cli import BotHandler, BotCapabilities
    
    capabilities = BotCapabilities(
        tools=tools or [],
        memory=memory,
        knowledge=knowledge,
        web_search=web_search,
        auto_approve=auto_approve,
        model=model,
    )
    
    handler = BotHandler()
    handler.start_email(
        token=token,
        agent_file=agent,
        capabilities=capabilities,
        email_address=email_address,
        imap_server=imap_server,
        smtp_server=smtp_server,
    )


@app.command("agentmail")
def bot_agentmail(
    token: Optional[str] = typer.Option(None, "--token", "-t", help="AgentMail API key", envvar="AGENTMAIL_API_KEY"),
    inbox_id: Optional[str] = typer.Option(None, "--inbox", help="Existing inbox ID / email address", envvar="AGENTMAIL_INBOX_ID"),
    domain: Optional[str] = typer.Option(None, "--domain", help="Custom domain for new inboxes", envvar="AGENTMAIL_DOMAIN"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent YAML configuration file"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    tools: Optional[List[str]] = typer.Option(None, "--tools", help="Tools to enable"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    knowledge: bool = typer.Option(False, "--knowledge", help="Enable knowledge/RAG"),
    web_search: bool = typer.Option(False, "--web", "--web-search", help="Enable web search"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Auto-approve all tool executions"),
):
    """Start an AgentMail bot (API-first email for AI agents).
    
    Examples:
        praisonai bot agentmail --token $AGENTMAIL_API_KEY
        praisonai bot agentmail --inbox praison@agentmail.to
        praisonai bot agentmail --agent agents.yaml --memory
    """
    from ..features.bots_cli import BotHandler, BotCapabilities
    
    capabilities = BotCapabilities(
        tools=tools or [],
        memory=memory,
        knowledge=knowledge,
        web_search=web_search,
        auto_approve=auto_approve,
        model=model,
    )
    
    handler = BotHandler()
    handler.start_agentmail(
        token=token,
        agent_file=agent,
        capabilities=capabilities,
        inbox_id=inbox_id,
        domain=domain,
    )


@app.command("install-daemon")
def bot_install_daemon(
    config: str = typer.Option(
        "bot.yaml", "--config",
        help="Path to bot.yaml (defaults to ./bot.yaml → ~/.praisonai/bot.yaml)",
    ),
    start: bool = typer.Option(True, "--start/--no-start", help="Start after install"),
):
    """Install bot as OS daemon service (alias for 'praisonai gateway install').
    
    Examples:
        praisonai bot install-daemon
        praisonai bot install-daemon --config my-bot.yaml --no-start
    """
    from praisonai.daemon import install_daemon
    from .._paths import resolve_bot_config_path
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    config = resolve_bot_config_path(config)
    
    try:
        result = install_daemon(config_path=config)
        if result.get("ok"):
            output.print_success(result.get("message", "Service installed successfully"))
            if start:
                output.print_info("Starting the service...")
                from praisonai.daemon import get_daemon_status
                status = get_daemon_status()
                if status.get("running"):
                    output.print_success("Service is now running")
                else:
                    output.print_warning("Service installed but not running. Check system logs.")
        else:
            error = result.get("error", "Installation failed")
            output.print_error(f"Installation failed: {error}")
            raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Installation error: {str(e)}")
        raise typer.Exit(1)


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
  [green]linear[/green]      Linear AgentSession webhooks
  [green]email[/green]       Email via IMAP/SMTP
  [green]agentmail[/green]   AgentMail API (API-first email for AI agents)

[bold]Daemon Management:[/bold]
  [green]install-daemon[/green]   Install bot as OS daemon service (auto-start)

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
  praisonai bot linear --token $LINEAR_OAUTH_TOKEN --signing-secret $LINEAR_WEBHOOK_SECRET
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)

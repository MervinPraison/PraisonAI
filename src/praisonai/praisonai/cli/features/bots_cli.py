"""
Bot CLI commands for PraisonAI.

Provides CLI commands for managing messaging bots with full tool support.
Inspired by moltbot's comprehensive CLI options.

Features:
- Browser control integration
- Skills/tools enabling
- YAML agent configuration
- Memory support
- Knowledge/RAG integration
- Web search capability
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BotCapabilities:
    """Capabilities configuration for bot instances.
    
    Enables various agent capabilities when running bots.
    All capabilities are opt-in for zero performance impact.
    """
    
    # Browser control
    browser: bool = False
    browser_profile: str = "default"
    browser_headless: bool = False
    
    # Tools and skills
    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    skills_dir: Optional[str] = None
    
    # Memory
    memory: bool = False
    memory_provider: str = "default"
    
    # Knowledge/RAG
    knowledge: bool = False
    knowledge_sources: List[str] = field(default_factory=list)
    
    # Web search
    web_search: bool = False
    web_search_provider: str = "duckduckgo"
    
    # Execution
    sandbox: bool = False
    exec_enabled: bool = False
    auto_approve: bool = False  # Auto-approve CLI tool execution
    
    # Model settings
    model: Optional[str] = None
    thinking: Optional[str] = None  # off, minimal, low, medium, high
    
    # Session
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "browser": self.browser,
            "browser_profile": self.browser_profile,
            "browser_headless": self.browser_headless,
            "tools": self.tools,
            "skills": self.skills,
            "skills_dir": self.skills_dir,
            "memory": self.memory,
            "memory_provider": self.memory_provider,
            "knowledge": self.knowledge,
            "knowledge_sources": self.knowledge_sources,
            "web_search": self.web_search,
            "web_search_provider": self.web_search_provider,
            "sandbox": self.sandbox,
            "exec_enabled": self.exec_enabled,
            "auto_approve": self.auto_approve,
            "model": self.model,
            "thinking": self.thinking,
            "session_id": self.session_id,
            "user_id": self.user_id,
        }


class BotHandler:
    """Handler for bot CLI commands.
    
    Supports comprehensive tool/capability configuration inspired by moltbot.
    """
    
    def start_telegram(
        self,
        token: Optional[str] = None,
        agent_file: Optional[str] = None,
        capabilities: Optional[BotCapabilities] = None,
    ) -> None:
        """Start a Telegram bot.
        
        Args:
            token: Telegram bot token (or use TELEGRAM_BOT_TOKEN env var)
            agent_file: Optional path to agent configuration file
            capabilities: Optional capabilities configuration
        """
        token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            print("Error: Telegram bot token required")
            print("Provide via --token or TELEGRAM_BOT_TOKEN environment variable")
            return
        
        # Set auto-approve if enabled - use environment variable (persists across async contexts)
        if capabilities and capabilities.auto_approve:
            os.environ["PRAISONAI_AUTO_APPROVE"] = "true"
            logger.info("Auto-approve enabled for all tool executions")
        
        try:
            from praisonai.bots import TelegramBot
        except ImportError as e:
            print(f"Error: TelegramBot requires python-telegram-bot. {e}")
            print("Install with: pip install python-telegram-bot")
            return
        
        agent = self._load_agent(agent_file, capabilities)
        bot = TelegramBot(token=token, agent=agent)
        
        self._print_startup_info("Telegram", capabilities)
        
        try:
            asyncio.run(bot.start())
        except KeyboardInterrupt:
            print("\nStopping bot...")
            asyncio.run(bot.stop())
    
    def start_discord(
        self,
        token: Optional[str] = None,
        agent_file: Optional[str] = None,
        capabilities: Optional[BotCapabilities] = None,
    ) -> None:
        """Start a Discord bot.
        
        Args:
            token: Discord bot token (or use DISCORD_BOT_TOKEN env var)
            agent_file: Optional path to agent configuration file
            capabilities: Optional capabilities configuration
        """
        token = token or os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            print("Error: Discord bot token required")
            print("Provide via --token or DISCORD_BOT_TOKEN environment variable")
            return
        
        # Set auto-approve if enabled - use environment variable (persists across async contexts)
        if capabilities and capabilities.auto_approve:
            os.environ["PRAISONAI_AUTO_APPROVE"] = "true"
            logger.info("Auto-approve enabled for all tool executions")
        
        try:
            from praisonai.bots import DiscordBot
        except ImportError as e:
            print(f"Error: DiscordBot requires discord.py. {e}")
            print("Install with: pip install discord.py")
            return
        
        agent = self._load_agent(agent_file, capabilities)
        bot = DiscordBot(token=token, agent=agent)
        
        self._print_startup_info("Discord", capabilities)
        
        try:
            asyncio.run(bot.start())
        except KeyboardInterrupt:
            print("\nStopping bot...")
            asyncio.run(bot.stop())
    
    def start_slack(
        self,
        token: Optional[str] = None,
        app_token: Optional[str] = None,
        agent_file: Optional[str] = None,
        capabilities: Optional[BotCapabilities] = None,
    ) -> None:
        """Start a Slack bot.
        
        Args:
            token: Slack bot token (or use SLACK_BOT_TOKEN env var)
            app_token: Slack app token (or use SLACK_APP_TOKEN env var)
            agent_file: Optional path to agent configuration file
            capabilities: Optional capabilities configuration
        """
        token = token or os.environ.get("SLACK_BOT_TOKEN")
        app_token = app_token or os.environ.get("SLACK_APP_TOKEN")
        
        if not token:
            print("Error: Slack bot token required")
            print("Provide via --token or SLACK_BOT_TOKEN environment variable")
            return
        
        # Set auto-approve if enabled - use environment variable (persists across async contexts)
        if capabilities and capabilities.auto_approve:
            os.environ["PRAISONAI_AUTO_APPROVE"] = "true"
            logger.info("Auto-approve enabled for all tool executions")
        
        try:
            from praisonai.bots import SlackBot
        except ImportError as e:
            print(f"Error: SlackBot requires slack-bolt. {e}")
            print("Install with: pip install slack-bolt")
            return
        
        agent = self._load_agent(agent_file, capabilities)
        bot = SlackBot(token=token, app_token=app_token, agent=agent)
        
        self._print_startup_info("Slack", capabilities)
        
        try:
            asyncio.run(bot.start())
        except KeyboardInterrupt:
            print("\nStopping bot...")
            asyncio.run(bot.stop())
    
    def _print_startup_info(self, platform: str, capabilities: Optional[BotCapabilities]) -> None:
        """Print startup information with enabled capabilities."""
        print(f"Starting {platform} bot...")
        
        if capabilities:
            enabled = []
            if capabilities.browser:
                enabled.append(f"browser ({capabilities.browser_profile})")
            if capabilities.tools:
                enabled.append(f"tools ({len(capabilities.tools)})")
            if capabilities.skills:
                enabled.append(f"skills ({len(capabilities.skills)})")
            if capabilities.memory:
                enabled.append("memory")
            if capabilities.knowledge:
                enabled.append("knowledge")
            if capabilities.web_search:
                enabled.append(f"web ({capabilities.web_search_provider})")
            if capabilities.sandbox:
                enabled.append("sandbox")
            if capabilities.exec_enabled:
                enabled.append("exec")
            
            if enabled:
                print(f"Capabilities: {', '.join(enabled)}")
        
        print("Press Ctrl+C to stop")
    
    def _load_agent(
        self,
        file_path: Optional[str],
        capabilities: Optional[BotCapabilities] = None,
    ):
        """Load agent from configuration file with capabilities.
        
        Args:
            file_path: Path to agent YAML configuration
            capabilities: Bot capabilities to apply
            
        Returns:
            Configured Agent instance
        """
        from praisonaiagents import Agent
        
        # Build tools list from capabilities
        tools = self._build_tools(capabilities) if capabilities else []
        
        # Default agent if no file
        if not file_path:
            return Agent(
                name="assistant",
                instructions="You are a helpful assistant.",
                tools=tools if tools else None,
                llm=capabilities.model if capabilities and capabilities.model else None,
            )
        
        # Resolve file path - try current dir first, then check if it's absolute
        resolved_path = file_path
        if not os.path.isabs(file_path):
            # Try relative to current working directory
            cwd_path = os.path.join(os.getcwd(), file_path)
            if os.path.exists(cwd_path):
                resolved_path = cwd_path
        
        if not os.path.exists(resolved_path):
            print(f"Warning: Agent file not found: {file_path} (resolved: {resolved_path})")
            return Agent(
                name="assistant",
                instructions="You are a helpful assistant.",
                tools=tools if tools else None,
                llm=capabilities.model if capabilities and capabilities.model else None,
            )
        
        try:
            import yaml
            with open(resolved_path, "r") as f:
                config = yaml.safe_load(f)
            
            # Support both list-style and dict-style YAML agents
            agent_config = None
            if "agents" in config and config["agents"]:
                agents = config["agents"]
                if isinstance(agents, list):
                    # List style: agents: - name: foo
                    agent_config = agents[0]
                elif isinstance(agents, dict):
                    # Dict style: agents: searcher: name: foo
                    first_key = next(iter(agents))
                    agent_config = agents[first_key]
            
            if not agent_config:
                agent_config = config
            
            # Merge tools from YAML and capabilities
            yaml_tools = agent_config.get("tools", [])
            all_tools = self._resolve_tools(yaml_tools) + tools
            
            return Agent(
                name=agent_config.get("name", "assistant"),
                instructions=agent_config.get("instructions", "You are a helpful assistant."),
                llm=capabilities.model if capabilities and capabilities.model else agent_config.get("llm"),
                tools=all_tools if all_tools else None,
            )
        except Exception as e:
            import traceback
            print(f"Error loading agent: {e}")
            traceback.print_exc()
            return Agent(
                name="assistant",
                instructions="You are a helpful assistant.",
                tools=tools if tools else None,
                llm=capabilities.model if capabilities and capabilities.model else None,
            )
    
    def _build_tools(self, capabilities: BotCapabilities) -> List:
        """Build tools list from capabilities."""
        tools = []
        
        # Default tools: execute_command and search_web (always enabled)
        try:
            from praisonaiagents.tools import execute_command, search_web
            tools.append(execute_command)
            tools.append(search_web)
            logger.info("Default tools enabled: execute_command, search_web")
        except ImportError:
            logger.warning("Default tools not available from praisonaiagents.tools")
        
        # Browser tool
        if capabilities.browser:
            try:
                from praisonai_tools import BrowserBaseTool
                tools.append(BrowserBaseTool())
                logger.info("Browser tool enabled")
            except ImportError:
                logger.warning("Browser tool not available. Install praisonai-tools.")
        
        # Web search (additional provider-specific tool)
        if capabilities.web_search:
            try:
                if capabilities.web_search_provider == "duckduckgo":
                    from praisonai_tools import DuckDuckGoTool
                    tools.append(DuckDuckGoTool())
                elif capabilities.web_search_provider == "tavily":
                    from praisonai_tools import TavilyTool
                    tools.append(TavilyTool())
                elif capabilities.web_search_provider == "serper":
                    from praisonai_tools import SerperTool
                    tools.append(SerperTool())
                else:
                    from praisonai_tools import DuckDuckGoTool
                    tools.append(DuckDuckGoTool())
                logger.info(f"Web search provider enabled: {capabilities.web_search_provider}")
            except ImportError:
                logger.warning("Web search tool not available. Install praisonai-tools.")
        
        # Exec tool (code execution) - already included in default via execute_command
        if capabilities.exec_enabled:
            logger.info("Exec mode enabled (execute_command already included)")
        
        # Named tools
        for tool_name in capabilities.tools:
            tool = self._resolve_tool_by_name(tool_name)
            if tool:
                tools.append(tool)
        
        return tools
    
    def _resolve_tool_by_name(self, name: str):
        """Resolve a tool by name."""
        try:
            import praisonai_tools
            tool_class = getattr(praisonai_tools, name, None)
            if tool_class:
                return tool_class()
        except ImportError:
            pass
        
        try:
            from praisonaiagents import tools as agent_tools
            tool_func = getattr(agent_tools, name, None)
            if tool_func:
                return tool_func
        except ImportError:
            pass
        
        logger.warning(f"Tool not found: {name}")
        return None
    
    def _resolve_tools(self, tool_names: List[str]) -> List:
        """Resolve a list of tool names to tool instances."""
        tools = []
        for name in tool_names:
            tool = self._resolve_tool_by_name(name)
            if tool:
                tools.append(tool)
        return tools


def _add_capability_args(parser) -> None:
    """Add capability arguments to a parser."""
    # Agent configuration
    parser.add_argument("--agent", help="Path to agent YAML configuration file")
    parser.add_argument("--model", "-m", help="LLM model to use")
    
    # Browser
    parser.add_argument("--browser", action="store_true", help="Enable browser control")
    parser.add_argument("--browser-profile", default="default", help="Browser profile name")
    parser.add_argument("--browser-headless", action="store_true", help="Run browser in headless mode")
    
    # Tools
    parser.add_argument("--tools", "-t", nargs="*", default=[], help="Tools to enable (e.g., DuckDuckGoTool)")
    parser.add_argument("--skills", nargs="*", default=[], help="Skills to enable")
    parser.add_argument("--skills-dir", help="Custom skills directory")
    
    # Memory
    parser.add_argument("--memory", action="store_true", help="Enable memory")
    parser.add_argument("--memory-provider", default="default", help="Memory provider")
    
    # Knowledge/RAG
    parser.add_argument("--knowledge", action="store_true", help="Enable knowledge/RAG")
    parser.add_argument("--knowledge-sources", nargs="*", default=[], help="Knowledge sources")
    
    # Web search
    parser.add_argument("--web", "--web-search", dest="web_search", action="store_true", help="Enable web search")
    parser.add_argument("--web-provider", default="duckduckgo", help="Web search provider (duckduckgo, tavily, serper)")
    
    # Execution
    parser.add_argument("--sandbox", action="store_true", help="Enable sandbox mode")
    parser.add_argument("--exec", dest="exec_enabled", action="store_true", help="Enable exec tool")
    parser.add_argument("--auto-approve", dest="auto_approve", action="store_true", help="Auto-approve all tool executions")
    
    # Session
    parser.add_argument("--session-id", help="Session ID")
    parser.add_argument("--user-id", help="User ID for memory isolation")
    
    # Thinking mode
    parser.add_argument("--thinking", choices=["off", "minimal", "low", "medium", "high"], help="Thinking mode")


def _build_capabilities_from_args(args) -> BotCapabilities:
    """Build BotCapabilities from parsed arguments."""
    return BotCapabilities(
        browser=getattr(args, "browser", False),
        browser_profile=getattr(args, "browser_profile", "default"),
        browser_headless=getattr(args, "browser_headless", False),
        tools=getattr(args, "tools", []) or [],
        skills=getattr(args, "skills", []) or [],
        skills_dir=getattr(args, "skills_dir", None),
        memory=getattr(args, "memory", False),
        memory_provider=getattr(args, "memory_provider", "default"),
        knowledge=getattr(args, "knowledge", False),
        knowledge_sources=getattr(args, "knowledge_sources", []) or [],
        web_search=getattr(args, "web_search", False),
        web_search_provider=getattr(args, "web_provider", "duckduckgo"),
        sandbox=getattr(args, "sandbox", False),
        exec_enabled=getattr(args, "exec_enabled", False),
        auto_approve=getattr(args, "auto_approve", False),
        model=getattr(args, "model", None),
        thinking=getattr(args, "thinking", None),
        session_id=getattr(args, "session_id", None),
        user_id=getattr(args, "user_id", None),
    )


def handle_bot_command(args) -> int:
    """Handle bot CLI command.
    
    Args:
        args: Either a list of command-line arguments (from main.py unknown_args)
              or an argparse.Namespace object (from legacy add_bot_parser).
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    import argparse
    
    # If args is a list, parse it using argparse
    if isinstance(args, list):
        parser = argparse.ArgumentParser(
            prog="praisonai bot",
            description="Start a messaging bot with full agent capabilities",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Basic bot
  praisonai bot telegram --token $TELEGRAM_BOT_TOKEN

  # Bot with agent YAML
  praisonai bot slack --token $SLACK_BOT_TOKEN --agent agents.yaml

  # Bot with browser and web search
  praisonai bot discord --token $DISCORD_BOT_TOKEN --browser --web

  # Bot with tools
  praisonai bot telegram --token $TELEGRAM_BOT_TOKEN --tools DuckDuckGoTool WikipediaTool

  # Full-featured bot
  praisonai bot slack --token $SLACK_BOT_TOKEN --agent agents.yaml --browser --web --memory --model gpt-4o
""",
        )
        subparsers = parser.add_subparsers(dest="platform", help="Bot platform")
        
        # Telegram
        telegram_parser = subparsers.add_parser("telegram", help="Start a Telegram bot")
        telegram_parser.add_argument("--token", help="Telegram bot token")
        _add_capability_args(telegram_parser)
        
        # Discord
        discord_parser = subparsers.add_parser("discord", help="Start a Discord bot")
        discord_parser.add_argument("--token", help="Discord bot token")
        _add_capability_args(discord_parser)
        
        # Slack
        slack_parser = subparsers.add_parser("slack", help="Start a Slack bot")
        slack_parser.add_argument("--token", help="Slack bot token")
        slack_parser.add_argument("--app-token", dest="app_token", help="Slack app token for Socket Mode")
        _add_capability_args(slack_parser)
        
        try:
            args = parser.parse_args(args)
        except SystemExit:
            return 1
    
    handler = BotHandler()
    capabilities = _build_capabilities_from_args(args)
    
    platform = getattr(args, "platform", None)
    
    if platform == "telegram":
        handler.start_telegram(
            token=getattr(args, "token", None),
            agent_file=getattr(args, "agent", None),
            capabilities=capabilities,
        )
        return 0
    elif platform == "discord":
        handler.start_discord(
            token=getattr(args, "token", None),
            agent_file=getattr(args, "agent", None),
            capabilities=capabilities,
        )
        return 0
    elif platform == "slack":
        handler.start_slack(
            token=getattr(args, "token", None),
            app_token=getattr(args, "app_token", None),
            agent_file=getattr(args, "agent", None),
            capabilities=capabilities,
        )
        return 0
    else:
        print("Available platforms: telegram, discord, slack")
        print("")
        print("Usage: praisonai bot <platform> [options]")
        print("")
        print("Capability Options:")
        print("  --agent FILE        Agent YAML configuration file")
        print("  --model MODEL       LLM model to use")
        print("  --browser           Enable browser control")
        print("  --web               Enable web search")
        print("  --memory            Enable memory")
        print("  --knowledge         Enable knowledge/RAG")
        print("  --tools TOOL...     Enable specific tools")
        print("  --sandbox           Enable sandbox mode")
        print("")
        print("Examples:")
        print("  praisonai bot telegram --token $TELEGRAM_BOT_TOKEN")
        print("  praisonai bot slack --token $SLACK_BOT_TOKEN --agent agents.yaml --browser --web")
        print("  praisonai bot discord --token $DISCORD_BOT_TOKEN --tools DuckDuckGoTool --memory")
        return 1


def add_bot_parser(subparsers) -> None:
    """Add bot subparser to CLI with full capability options."""
    bot_parser = subparsers.add_parser(
        "bot",
        help="Start a messaging bot with full agent capabilities",
    )
    
    bot_subparsers = bot_parser.add_subparsers(
        dest="platform",
        help="Bot platform",
    )
    
    # Telegram
    telegram_parser = bot_subparsers.add_parser(
        "telegram",
        help="Start a Telegram bot",
    )
    telegram_parser.add_argument(
        "--token",
        help="Telegram bot token (or use TELEGRAM_BOT_TOKEN env var)",
    )
    _add_capability_args(telegram_parser)
    
    # Discord
    discord_parser = bot_subparsers.add_parser(
        "discord",
        help="Start a Discord bot",
    )
    discord_parser.add_argument(
        "--token",
        help="Discord bot token (or use DISCORD_BOT_TOKEN env var)",
    )
    _add_capability_args(discord_parser)
    
    # Slack
    slack_parser = bot_subparsers.add_parser(
        "slack",
        help="Start a Slack bot",
    )
    slack_parser.add_argument(
        "--token",
        help="Slack bot token (or use SLACK_BOT_TOKEN env var)",
    )
    slack_parser.add_argument(
        "--app-token",
        dest="app_token",
        help="Slack app token for Socket Mode (or use SLACK_APP_TOKEN env var)",
    )
    _add_capability_args(slack_parser)
    
    bot_parser.set_defaults(func=handle_bot_command)

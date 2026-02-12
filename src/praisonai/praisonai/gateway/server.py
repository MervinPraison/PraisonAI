"""
WebSocket Gateway Server for PraisonAI.

Provides a WebSocket-based gateway for multi-agent coordination,
session management, and real-time communication.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonaiagents.gateway import (
    GatewayConfig,
    GatewayEvent,
    GatewayMessage,
    EventType,
)

logger = logging.getLogger(__name__)


@dataclass
class GatewaySession:
    """A gateway session tracking a conversation between client and agent."""
    
    _session_id: str
    _agent_id: str
    _client_id: Optional[str] = None
    _is_active: bool = True
    _created_at: float = field(default_factory=time.time)
    _last_activity: float = field(default_factory=time.time)
    _state: Dict[str, Any] = field(default_factory=dict)
    _messages: List[GatewayMessage] = field(default_factory=list)
    _max_messages: int = 1000
    
    @property
    def session_id(self) -> str:
        return self._session_id
    
    @property
    def agent_id(self) -> Optional[str]:
        return self._agent_id
    
    @property
    def client_id(self) -> Optional[str]:
        return self._client_id
    
    @property
    def is_active(self) -> bool:
        return self._is_active
    
    @property
    def created_at(self) -> float:
        return self._created_at
    
    @property
    def last_activity(self) -> float:
        return self._last_activity
    
    def get_state(self) -> Dict[str, Any]:
        return dict(self._state)
    
    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value
        self._last_activity = time.time()
    
    def add_message(self, message: GatewayMessage) -> None:
        self._messages.append(message)
        self._last_activity = time.time()
        if self._max_messages > 0 and len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]
    
    def get_messages(self, limit: Optional[int] = None) -> List[GatewayMessage]:
        if limit:
            return list(self._messages[-limit:])
        return list(self._messages)
    
    def close(self) -> None:
        self._is_active = False


class WebSocketGateway:
    """WebSocket gateway server for multi-agent coordination.
    
    Implements the GatewayProtocol for WebSocket-based communication.
    
    Example:
        from praisonai.gateway import WebSocketGateway
        from praisonaiagents import Agent
        
        # Create gateway
        gateway = WebSocketGateway(port=8765)
        
        # Register agents
        agent = Agent(name="assistant")
        gateway.register_agent(agent)
        
        # Start gateway
        await gateway.start()
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        config: Optional[GatewayConfig] = None,
    ):
        """Initialize the gateway.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            config: Optional gateway configuration
        """
        self.config = config or GatewayConfig(host=host, port=port)
        self._host = self.config.host
        self._port = self.config.port
        
        self._is_running = False
        self._started_at: Optional[float] = None
        self._server = None
        
        self._agents: Dict[str, "Agent"] = {}
        self._sessions: Dict[str, GatewaySession] = {}
        self._clients: Dict[str, Any] = {}  # WebSocket connections
        self._client_sessions: Dict[str, str] = {}  # client_id -> session_id
        
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        
        # Multi-bot lifecycle
        self._channel_bots: Dict[str, Any] = {}  # channel_name -> bot instance
        self._routing_rules: Dict[str, Dict[str, str]] = {}  # channel_name -> {context -> agent_id}
        self._channel_tasks: List[asyncio.Task] = []
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def port(self) -> int:
        return self._port
    
    @property
    def host(self) -> str:
        return self._host
    
    async def start(self) -> None:
        """Start the gateway server."""
        if self._is_running:
            logger.warning("Gateway already running")
            return
        
        try:
            from starlette.applications import Starlette
            from starlette.routing import Route, WebSocketRoute
            from starlette.responses import JSONResponse
            from starlette.websockets import WebSocket, WebSocketDisconnect
            import uvicorn
        except ImportError:
            raise ImportError(
                "Gateway requires starlette and uvicorn. "
                "Install with: pip install praisonai[api]"
            )
        
        async def health(request):
            return JSONResponse(self.health())
        
        async def info(request):
            return JSONResponse({
                "name": "PraisonAI Gateway",
                "version": "1.0.0",
                "agents": list(self._agents.keys()),
                "sessions": len(self._sessions),
                "clients": len(self._clients),
            })
        
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            client_id = str(uuid.uuid4())
            self._clients[client_id] = websocket
            
            logger.info(f"Client connected: {client_id}")
            
            await self.emit(GatewayEvent(
                type=EventType.CONNECT,
                data={"client_id": client_id},
                source=client_id,
            ))
            
            try:
                while True:
                    data = await websocket.receive_json()
                    await self._handle_client_message(client_id, data)
            except WebSocketDisconnect:
                logger.info(f"Client disconnected: {client_id}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self._clients.pop(client_id, None)
                session_id = self._client_sessions.pop(client_id, None)
                if session_id:
                    self.close_session(session_id)
                
                await self.emit(GatewayEvent(
                    type=EventType.DISCONNECT,
                    data={"client_id": client_id},
                    source=client_id,
                ))
        
        routes = [
            Route("/health", health, methods=["GET"]),
            Route("/info", info, methods=["GET"]),
            WebSocketRoute("/ws", websocket_endpoint),
        ]
        
        app = Starlette(routes=routes)
        
        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        
        self._is_running = True
        self._started_at = time.time()
        
        logger.info(f"Gateway started on ws://{self._host}:{self._port}")
        
        await self._server.serve()
    
    async def stop(self) -> None:
        """Stop the gateway server."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        for client_id, ws in list(self._clients.items()):
            try:
                await ws.close()
            except Exception:
                pass
        
        self._clients.clear()
        self._client_sessions.clear()
        
        for session in list(self._sessions.values()):
            session.close()
        
        if self._server:
            self._server.should_exit = True
        
        logger.info("Gateway stopped")
    
    async def _handle_client_message(self, client_id: str, data: Dict[str, Any]) -> None:
        """Handle a message from a client."""
        msg_type = data.get("type", "message")
        
        if msg_type == "join":
            agent_id = data.get("agent_id")
            if agent_id and agent_id in self._agents:
                session = self.create_session(agent_id, client_id)
                self._client_sessions[client_id] = session.session_id
                await self._send_to_client(client_id, {
                    "type": "joined",
                    "session_id": session.session_id,
                    "agent_id": agent_id,
                })
            else:
                await self._send_to_client(client_id, {
                    "type": "error",
                    "message": f"Agent not found: {agent_id}",
                })
        
        elif msg_type == "message":
            session_id = self._client_sessions.get(client_id)
            if session_id:
                session = self._sessions.get(session_id)
                if session:
                    content = data.get("content", "")
                    message = GatewayMessage(
                        content=content,
                        sender_id=client_id,
                        session_id=session_id,
                    )
                    session.add_message(message)
                    
                    response = await self._process_agent_message(session, message)
                    
                    await self._send_to_client(client_id, {
                        "type": "response",
                        "content": response,
                        "session_id": session_id,
                    })
            else:
                await self._send_to_client(client_id, {
                    "type": "error",
                    "message": "Not joined to any session",
                })
        
        elif msg_type == "leave":
            session_id = self._client_sessions.pop(client_id, None)
            if session_id:
                self.close_session(session_id)
                await self._send_to_client(client_id, {
                    "type": "left",
                    "session_id": session_id,
                })
    
    async def _process_agent_message(
        self,
        session: GatewaySession,
        message: GatewayMessage,
    ) -> str:
        """Process a message through the agent."""
        agent = self._agents.get(session.agent_id)
        if not agent:
            return "Agent not available"
        
        try:
            content = message.content if isinstance(message.content, str) else str(message.content)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, agent.chat, content)
            
            response_message = GatewayMessage(
                content=response,
                sender_id=session.agent_id,
                session_id=session.session_id,
                reply_to=message.message_id,
            )
            session.add_message(response_message)
            
            return response
        except Exception as e:
            logger.error(f"Agent error: {e}")
            return f"Error: {str(e)}"
    
    async def _send_to_client(self, client_id: str, data: Dict[str, Any]) -> None:
        """Send data to a specific client."""
        ws = self._clients.get(client_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
    
    def register_agent(self, agent: "Agent", agent_id: Optional[str] = None) -> str:
        """Register an agent with the gateway."""
        aid = agent_id or getattr(agent, "agent_id", None) or str(uuid.uuid4())
        self._agents[aid] = agent
        logger.info(f"Agent registered: {aid}")
        return aid
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the gateway."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Agent unregistered: {agent_id}")
            return True
        return False
    
    def get_agent(self, agent_id: str) -> Optional["Agent"]:
        """Get a registered agent by ID."""
        return self._agents.get(agent_id)
    
    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        return list(self._agents.keys())
    
    def create_session(
        self,
        agent_id: str,
        client_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GatewaySession:
        """Create a new session."""
        sid = session_id or str(uuid.uuid4())
        session = GatewaySession(
            _session_id=sid,
            _agent_id=agent_id,
            _client_id=client_id,
            _max_messages=self.config.session_config.max_messages,
        )
        self._sessions[sid] = session
        logger.info(f"Session created: {sid} for agent {agent_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[GatewaySession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def close_session(self, session_id: str) -> bool:
        """Close a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()
            logger.info(f"Session closed: {session_id}")
            return True
        return False
    
    def list_sessions(self, agent_id: Optional[str] = None) -> List[str]:
        """List session IDs, optionally filtered by agent."""
        if agent_id:
            return [
                sid for sid, session in self._sessions.items()
                if session.agent_id == agent_id
            ]
        return list(self._sessions.keys())
    
    def on_event(self, event_type: str) -> Callable:
        """Decorator to register an event handler."""
        def decorator(func: Callable) -> Callable:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            self._event_handlers[event_type].append(func)
            return func
        return decorator
    
    async def emit(self, event: GatewayEvent) -> None:
        """Emit an event to registered handlers."""
        event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
    
    async def broadcast(
        self,
        event: GatewayEvent,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """Broadcast an event to all connected clients."""
        exclude_set = set(exclude or [])
        data = event.to_dict()
        
        for client_id, ws in list(self._clients.items()):
            if client_id not in exclude_set:
                try:
                    await ws.send_json(data)
                except Exception as e:
                    logger.error(f"Broadcast error to {client_id}: {e}")
    
    def health(self) -> Dict[str, Any]:
        """Get gateway health status including per-channel bot status."""
        uptime = time.time() - self._started_at if self._started_at else 0
        channel_status = {}
        for name, bot in self._channel_bots.items():
            running = getattr(bot, "is_running", False)
            platform = getattr(bot, "platform", "unknown")
            channel_status[name] = {
                "platform": platform,
                "running": running,
            }
        return {
            "status": "healthy" if self._is_running else "stopped",
            "uptime": uptime,
            "agents": len(self._agents),
            "sessions": len(self._sessions),
            "clients": len(self._clients),
            "channels": channel_status,
        }

    # ── Multi-bot lifecycle ───────────────────────────────────────────

    @staticmethod
    def _substitute_env_vars(value: str) -> str:
        """Replace ${VAR_NAME} patterns with environment variable values."""
        if not isinstance(value, str):
            return value
        def _replacer(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                logger.warning(f"Environment variable {var_name} not set")
                return match.group(0)
            return env_val
        return re.sub(r'\$\{([^}]+)\}', _replacer, value)

    @classmethod
    def load_gateway_config(cls, config_path: str) -> Dict[str, Any]:
        """Load and parse a gateway.yaml configuration file.

        Performs environment variable substitution on all string values.

        Args:
            config_path: Path to the YAML configuration file.

        Returns:
            Parsed configuration dictionary with env vars resolved.
        """
        import yaml

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Gateway config not found: {config_path}")

        with open(config_path, "r") as f:
            raw = yaml.safe_load(f)

        if not raw or not isinstance(raw, dict):
            raise ValueError(f"Invalid gateway config: {config_path}")

        def _resolve(obj):
            if isinstance(obj, str):
                return cls._substitute_env_vars(obj)
            if isinstance(obj, dict):
                return {k: _resolve(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_resolve(v) for v in obj]
            return obj

        return _resolve(raw)

    def _create_agents_from_config(self, agents_cfg: Dict[str, Dict[str, Any]]) -> None:
        """Create and register Agent instances from the agents section of gateway.yaml."""
        from praisonaiagents import Agent

        for agent_id, agent_def in agents_cfg.items():
            instructions = agent_def.get("instructions", "")
            model = agent_def.get("model", None)
            memory = agent_def.get("memory", False)

            agent = Agent(
                name=agent_id,
                instructions=instructions,
                llm=model,
                memory=memory,
            )
            self.register_agent(agent, agent_id=agent_id)
            logger.info(f"Created agent '{agent_id}' (model={model})")

    def _determine_routing_context(
        self, channel_type: str, message_metadata: Dict[str, Any]
    ) -> str:
        """Determine the routing context key for a message.

        Args:
            channel_type: Platform name (telegram, discord, slack).
            message_metadata: Dict with at least 'chat_type' or 'is_dm' keys.

        Returns:
            Context string: 'dm', 'group', 'channel', or 'default'.
        """
        chat_type = message_metadata.get("chat_type", "")
        is_dm = message_metadata.get("is_dm", False)

        if is_dm or chat_type in ("private", "dm"):
            return "dm"
        if chat_type in ("group", "supergroup", "guild"):
            return "group"
        if chat_type == "channel":
            return "channel"
        return "default"

    def _resolve_agent_for_message(
        self, channel_name: str, context: str
    ) -> Optional["Agent"]:
        """Look up the correct agent for a channel + context."""
        rules = self._routing_rules.get(channel_name, {})
        agent_id = rules.get(context) or rules.get("default", "default")
        agent = self._agents.get(agent_id)
        if not agent:
            logger.warning(
                f"No agent '{agent_id}' for channel={channel_name} context={context}"
            )
        return agent

    async def start_channels(self, channels_cfg: Dict[str, Dict[str, Any]]) -> None:
        """Start bot instances for each configured channel.

        Each bot runs as a concurrent asyncio task.  If a single bot fails
        to start the others continue running.

        Args:
            channels_cfg: The ``channels`` section of gateway.yaml.
        """
        from praisonaiagents.bots import BotConfig

        for channel_name, ch_cfg in channels_cfg.items():
            channel_type = channel_name.lower()
            token = ch_cfg.get("token", "")
            if not token:
                logger.warning(f"No token for channel '{channel_name}', skipping")
                continue

            routes = ch_cfg.get("routes", {"default": "default"})
            self._routing_rules[channel_name] = routes

            # Resolve default agent for this channel (used as the bot's primary agent)
            default_agent_id = routes.get("default", list(self._agents.keys())[0] if self._agents else "default")
            default_agent = self._agents.get(default_agent_id)
            if not default_agent:
                logger.warning(f"Default agent '{default_agent_id}' not found for channel '{channel_name}', skipping")
                continue

            config = BotConfig(token=token)

            try:
                bot = self._create_bot(channel_type, token, default_agent, config, ch_cfg)
                if bot is None:
                    continue
                self._channel_bots[channel_name] = bot
                logger.info(f"Channel '{channel_name}' ({channel_type}) initialized")
            except Exception as e:
                logger.error(f"Failed to create bot for '{channel_name}': {e}")
                continue

        # Start all bots concurrently
        if self._channel_bots:
            for name, bot in self._channel_bots.items():
                task = asyncio.create_task(self._run_bot_safe(name, bot))
                self._channel_tasks.append(task)
            logger.info(f"Started {len(self._channel_bots)} channel bot(s)")

    def _create_bot(
        self,
        channel_type: str,
        token: str,
        agent: "Agent",
        config: Any,
        ch_cfg: Dict[str, Any],
    ) -> Any:
        """Create a bot instance for the given channel type."""
        if channel_type == "telegram":
            from praisonai.bots import TelegramBot
            return TelegramBot(token=token, agent=agent, config=config)
        elif channel_type == "discord":
            from praisonai.bots import DiscordBot
            return DiscordBot(token=token, agent=agent, config=config)
        elif channel_type == "slack":
            from praisonai.bots import SlackBot
            app_token = ch_cfg.get("app_token", os.environ.get("SLACK_APP_TOKEN", ""))
            return SlackBot(token=token, agent=agent, config=config, app_token=app_token)
        else:
            logger.warning(f"Unknown channel type: {channel_type}")
            return None

    async def _run_bot_safe(self, name: str, bot: Any) -> None:
        """Run a single bot, catching errors so other bots stay alive.

        For TelegramBot, uses the low-level initialize/start/start_polling
        API to avoid event-loop conflicts with ``run_polling()``.
        For Discord/Slack, injects a routing-aware message handler before
        starting so the gateway's routing rules are respected.
        """
        try:
            logger.info(f"Starting bot for channel '{name}'...")

            # TelegramBot special handling: run_polling() tries to manage
            # its own event loop which conflicts with our gateway loop.
            # Use the lower-level API instead.
            if self._is_telegram_bot(bot):
                await self._start_telegram_bot_polling(name, bot)
            else:
                # Inject routing-aware handler for Discord/Slack
                self._inject_routing_handler(name, bot)
                await bot.start()
        except asyncio.CancelledError:
            logger.info(f"Bot '{name}' cancelled")
        except Exception as e:
            logger.error(f"Bot '{name}' crashed: {e}")

    @staticmethod
    def _is_telegram_bot(bot: Any) -> bool:
        """Check if a bot instance is a TelegramBot."""
        return type(bot).__name__ == "TelegramBot"

    def _inject_routing_handler(self, channel_name: str, bot: Any) -> None:
        """Inject a routing-aware on_message handler into a Discord/Slack bot.

        This overrides the bot's default agent with a dynamically-resolved
        agent based on the gateway's routing rules for each incoming message.
        """
        gateway = self

        @bot.on_message
        async def _routed_message_handler(message):
            if not message.sender:
                return
            # Determine routing context from channel type
            ch_type = message.channel.channel_type if message.channel else ""
            is_dm = ch_type in ("dm", "private")
            routing_ctx = gateway._determine_routing_context(
                channel_name, {"chat_type": ch_type, "is_dm": is_dm}
            )
            agent = gateway._resolve_agent_for_message(channel_name, routing_ctx)
            if agent:
                bot.set_agent(agent)

        logger.info(f"Injected routing handler for channel '{channel_name}'")

    async def _start_telegram_bot_polling(self, name: str, bot: Any) -> None:
        """Start a TelegramBot using low-level PTB API for shared event loop.

        Uses ``initialize() -> start() -> updater.start_polling()`` instead
        of the high-level ``run_polling()`` which owns the event loop.
        """
        try:
            from telegram import Update
            from telegram.ext import (
                Application,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.error("python-telegram-bot not installed, cannot start Telegram channel")
            return

        app = Application.builder().token(bot._token).build()

        # Copy handlers from the bot's application if it was already built
        # Otherwise, re-build handlers here using the bot's setup logic
        bot._application = app
        bot._started_at = time.time()

        # Get bot info
        bot_info = await app.bot.get_me()
        from praisonaiagents.bots import BotUser
        bot._bot_user = BotUser(
            user_id=str(bot_info.id),
            username=bot_info.username,
            display_name=bot_info.first_name,
            is_bot=True,
        )

        # Set up message handler with routing support
        channel_name = name
        gateway = self

        async def handle_message(update: Update, context: Any):
            if not update.message:
                return

            message_text = None
            if update.message.voice or update.message.audio:
                message_text = await bot._transcribe_audio(update)
            elif update.message.text:
                message_text = update.message.text

            if not message_text:
                return

            # Determine routing context
            chat_type = update.message.chat.type if update.message.chat else "private"
            routing_ctx = gateway._determine_routing_context(
                "telegram", {"chat_type": chat_type}
            )
            agent = gateway._resolve_agent_for_message(channel_name, routing_ctx)
            if not agent:
                agent = bot._agent  # fallback to default

            # Show typing indicator
            if bot.config.typing_indicator:
                await update.message.chat.send_action("typing")

            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, agent.chat, message_text)
                if hasattr(bot, '_send_response_with_media'):
                    await bot._send_response_with_media(
                        update.message.chat_id,
                        response,
                        reply_to=update.message.message_id,
                    )
                else:
                    await update.message.reply_text(str(response))
            except Exception as e:
                logger.error(f"Agent error in {name}: {e}")
                await update.message.reply_text(f"Error: {str(e)}")

        async def handle_voice(update: Update, context: Any):
            await handle_message(update, context)

        # Register handlers
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

        # Initialize and start using low-level API
        await app.initialize()
        await app.start()
        await app.updater.start_polling(poll_interval=bot.config.polling_interval)

        bot._is_running = True
        logger.info(f"Telegram bot started: @{bot._bot_user.username}")

        # Keep alive until cancelled
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info(f"Stopping Telegram bot '{name}'...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            bot._is_running = False

    async def stop_channels(self) -> None:
        """Gracefully stop all running channel bots."""
        for task in self._channel_tasks:
            task.cancel()

        if self._channel_tasks:
            await asyncio.gather(*self._channel_tasks, return_exceptions=True)
            self._channel_tasks.clear()

        for name, bot in list(self._channel_bots.items()):
            try:
                if hasattr(bot, "stop"):
                    await bot.stop()
                logger.info(f"Stopped bot '{name}'")
            except Exception as e:
                logger.error(f"Error stopping bot '{name}': {e}")

        self._channel_bots.clear()
        self._routing_rules.clear()

    async def start_with_config(self, config_path: str) -> None:
        """Start the gateway with a gateway.yaml configuration.

        This loads agents from the config, starts channel bots, then
        starts the WebSocket server.  All run concurrently.

        Args:
            config_path: Path to gateway.yaml.
        """
        cfg = self.load_gateway_config(config_path)

        # Apply gateway section overrides
        gw_cfg = cfg.get("gateway", {})
        if gw_cfg.get("host"):
            self._host = gw_cfg["host"]
        if gw_cfg.get("port"):
            self._port = int(gw_cfg["port"])

        # Create agents
        agents_cfg = cfg.get("agents", {})
        if agents_cfg:
            self._create_agents_from_config(agents_cfg)

        # Start channels + WebSocket server concurrently
        channels_cfg = cfg.get("channels", {})

        async def _run_all():
            if channels_cfg:
                await self.start_channels(channels_cfg)
            await self.start()

        # Register signal handlers for graceful shutdown
        import signal

        def _request_shutdown(sig, frame):
            logger.info(f"Received signal {sig}, shutting down gateway...")
            if self._server:
                self._server.should_exit = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _request_shutdown)
            except (OSError, ValueError):
                pass  # Not all signals available on all platforms

        try:
            await _run_all()
        finally:
            await self.stop_channels()

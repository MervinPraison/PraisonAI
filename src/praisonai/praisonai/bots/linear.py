"""
Linear Bot implementation for PraisonAI.

Supports Linear agent integration via AgentSession webhooks.

Usage:
    bot = LinearBot(token="linear-oauth-token", agent=agent, 
                   signing_secret="webhook-secret")
    await bot.start()
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonai.bots._protocol_mixin import ChatCommandMixin, MessageHookMixin
from praisonaiagents.bots import (
    BotConfig,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
)

from ._commands import format_status, format_help
from ._session import BotSessionManager
from ._rate_limit import RateLimiter
from ._ack import AckReactor

logger = logging.getLogger(__name__)

# Linear GraphQL endpoint
LINEAR_API_BASE = "https://api.linear.app/graphql"


class LinearBot(ChatCommandMixin, MessageHookMixin):
    """Linear bot runtime for PraisonAI agents.

    Connects an agent to Linear via AgentSession webhooks, handling
    mentions, assignments, and providing full bot functionality.

    Example:
        from praisonai.bots import LinearBot
        from praisonaiagents import Agent

        agent = Agent(name="assistant")
        bot = LinearBot(
            token="YOUR_OAUTH_TOKEN",
            signing_secret="YOUR_WEBHOOK_SECRET",
            agent=agent,
        )

        await bot.start()
    """

    def __init__(
        self,
        token: str = "",
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        signing_secret: str = "",
        webhook_port: int = 8080,
        webhook_path: str = "/webhook",
        **kwargs,
    ):
        # Store extra kwargs for forward compatibility
        self._extra_kwargs = kwargs
        
        # Determine token source for proper authorization format
        self._oauth_token = token or os.environ.get("LINEAR_OAUTH_TOKEN", "")
        self._api_key = os.environ.get("LINEAR_API_KEY", "") if not self._oauth_token else ""
        self._token = self._oauth_token or self._api_key
        self._is_oauth = bool(self._oauth_token)
        self._agent = agent
        self.config = config or BotConfig(token=self._token, mode="webhook")
        self._signing_secret = signing_secret or os.environ.get("LINEAR_WEBHOOK_SECRET", "")
        self._webhook_port = webhook_port
        self._webhook_path = webhook_path

        self._is_running = False
        self._started_at: Optional[float] = None
        self._bot_user: Optional[BotUser] = None
        
        try:
            from praisonaiagents.session import get_default_session_store
            _store = get_default_session_store()
        except Exception:
            _store = None
            
        self._session_mgr = BotSessionManager(
            store=_store,
            platform="linear",
        )
        self._message_handlers: List[Callable] = []
        self._runner: Any = None
        self._site: Any = None
        self._http_session: Any = None
        self._background_tasks: set = set()
        self._rate_limiter = RateLimiter.for_platform("linear")
        self._ack: AckReactor = AckReactor(
            ack_emoji=self.config.ack_emoji,
            done_emoji=self.config.done_emoji,
        )

        # ChatCommandMixin setup
        self._command_handlers: Dict[str, Callable] = {}
        self._command_info: Dict[str, Dict[str, Any]] = {}

        # Register built-in commands
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in /status, /new, /help commands."""

        async def _status(msg):
            return format_status(self._agent, "linear", self._started_at, self._is_running)

        async def _new(msg):
            user_id = msg.sender.user_id if msg.sender else "unknown"
            self._session_mgr.reset(user_id)
            return "Session reset. Send a message to start a new conversation."

        async def _help(msg):
            extra = {
                name: info.get("description", "")
                for name, info in self._command_info.items()
                if name not in ("status", "new", "help")
            }
            return format_help(self._agent, "linear", extra or None)

        self.register_command("status", _status, description="Show bot status and info")
        self.register_command("new", _new, description="Reset conversation session")
        self.register_command("help", _help, description="Show this help message")

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def platform(self) -> str:
        return "linear"

    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the Linear webhook server."""
        if self._is_running:
            return

        if not self._token:
            raise ValueError("LINEAR_OAUTH_TOKEN or LINEAR_API_KEY required")
            
        if not self._signing_secret:
            logger.warning("LINEAR_WEBHOOK_SECRET not set - webhook signatures will not be verified")

        logger.info(f"Starting Linear bot on port {self._webhook_port}")
        
        try:
            import aiohttp
            from aiohttp import web
        except ImportError:
            raise ImportError("aiohttp required: pip install aiohttp")

        # Create HTTP session for API calls
        self._http_session = aiohttp.ClientSession()

        # Create webhook server
        app = web.Application()
        app.router.add_post(self._webhook_path, self._handle_webhook)
        app.router.add_get(self._webhook_path, self._handle_webhook_verify)
        
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._webhook_port)
        await self._site.start()

        self._is_running = True
        self._started_at = time.time()
        
        # Get bot user info
        await self._fetch_bot_user()
        
        logger.info(f"Linear bot started on http://0.0.0.0:{self._webhook_port}{self._webhook_path}")

    async def stop(self) -> None:
        """Stop the Linear webhook server."""
        if not self._is_running:
            return

        logger.info("Stopping Linear bot...")
        
        # Wait for background tasks to complete
        if self._background_tasks:
            logger.info(f"Waiting for {len(self._background_tasks)} background tasks...")
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Stop HTTP server
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
            
        # Close HTTP session
        if self._http_session:
            await self._http_session.close()

        self._is_running = False
        self._started_at = None
        logger.info("Linear bot stopped")

    # ── Webhook Handling ─────────────────────────────────────────────

    async def _handle_webhook_verify(self, request) -> Any:
        """Handle webhook verification (GET request)."""
        from aiohttp import web
        return web.Response(status=200, text="Linear webhook endpoint")

    async def _handle_webhook(self, request) -> Any:
        """Handle incoming Linear webhooks."""
        from aiohttp import web
        
        try:
            # Read raw body for signature verification
            raw_body = await request.read()
            
            # Verify signature if secret is configured
            if self._signing_secret:
                signature = request.headers.get("Linear-Signature", "")
                if not self._verify_signature(raw_body, signature):
                    logger.warning("Invalid webhook signature")
                    return web.Response(status=401, text="Invalid signature")
            
            # Parse JSON body
            try:
                body = json.loads(raw_body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Invalid JSON payload: {e}")
                return web.Response(status=400, text="Invalid JSON")
                
            # Check timestamp for replay protection (Linear recommendation: 60s window)
            webhook_timestamp = body.get("webhookTimestamp", 0)
            if webhook_timestamp:
                time_diff = abs(time.time() * 1000 - webhook_timestamp)
                if time_diff > 60_000:  # 60 seconds in milliseconds
                    logger.warning(f"Webhook timestamp too old: {time_diff}ms")
                    return web.Response(status=401, text="Timestamp too old")
            
            # Get event type
            event_type = request.headers.get("Linear-Event", "")
            
            # Process webhook in background to avoid blocking
            task = asyncio.create_task(self._process_webhook(event_type, body))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            
            return web.Response(status=200, text="OK")
            
        except Exception as e:
            logger.error(f"Webhook handling error: {e}")
            return web.Response(status=500, text="Internal error")

    def _verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify Linear webhook signature using HMAC-SHA256."""
        if not self._signing_secret or not signature:
            return False
            
        expected = hmac.new(
            self._signing_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)

    async def _process_webhook(self, event_type: str, body: Dict[str, Any]) -> None:
        """Process webhook events."""
        try:
            logger.debug(f"Processing {event_type} event")
            
            if event_type == "AgentSession":
                await self._handle_agent_session(body)
            elif event_type == "Comment":
                await self._handle_comment(body)
            elif event_type == "Issue":
                await self._handle_issue(body)
            else:
                logger.debug(f"Ignoring {event_type} event")
                
        except Exception as e:
            logger.error(f"Error processing {event_type} webhook: {e}")

    async def _handle_agent_session(self, body: Dict[str, Any]) -> None:
        """Handle AgentSession events (mentions, assignments)."""
        action = body.get("action")
        data = body.get("data", {})
        
        if action == "create":
            # New agent session created (mention or assignment)
            session_id = data.get("id")
            issue_data = data.get("issue", {})
            
            if not session_id or not issue_data:
                logger.warning("Missing session or issue data")
                return
                
            # Create bot message from issue
            issue_id = issue_data.get("id", "")
            issue_title = issue_data.get("title", "")
            issue_description = issue_data.get("description", "")
            
            message_text = f"Issue: {issue_title}"
            if issue_description:
                message_text += f"\n\n{issue_description}"
                
            bot_message = BotMessage(
                message_id=session_id,
                content=message_text,
                message_type=MessageType.TEXT,
                channel=BotChannel(channel_id=issue_id, name=f"Issue {issue_data.get('identifier', '')}"),
                sender=BotUser(user_id="linear-system", display_name="Linear"),
                timestamp=time.time(),
                metadata={"issue": issue_data, "session_id": session_id}
            )
            
            # Process with agent
            await self._handle_agent_message(bot_message)

    async def _handle_comment(self, body: Dict[str, Any]) -> None:
        """Handle Comment events."""
        # For future implementation - comment threads
        logger.debug("Comment event received")

    async def _handle_issue(self, body: Dict[str, Any]) -> None:
        """Handle Issue events."""
        # For future implementation - issue updates
        logger.debug("Issue event received")

    async def _handle_agent_message(self, message: BotMessage) -> None:
        """Process message with the agent."""
        if not self._agent:
            logger.warning("No agent configured")
            return

        try:
            user_id = message.sender.user_id if message.sender else "unknown"
            session_id = message.metadata.get("session_id") if message.metadata else None

            # Use BotSessionManager.chat() which handles history isolation and run_in_executor
            response = await self._session_mgr.chat(self._agent, user_id, message.content)

            # Send response back to Linear
            if response and message.metadata:
                await self._send_comment(
                    issue_id=message.metadata.get("issue", {}).get("id", ""),
                    comment=response,
                    session_id=session_id,
                )

        except Exception as e:
            logger.error(f"Error processing agent message: {e}")

    # ── Linear API Methods ──────────────────────────────────────────

    async def _fetch_bot_user(self) -> None:
        """Fetch bot user information from Linear API."""
        try:
            query = """query {
              viewer { id name email }
            }"""
            
            data = await self._gql_query(query)
            viewer = data.get("viewer", {})
            
            if viewer:
                self._bot_user = BotUser(
                    user_id=viewer.get("id", ""),
                    display_name=viewer.get("name", "Linear Bot"),
                    metadata=viewer
                )
                logger.info(f"Connected as: {self._bot_user.display_name}")
            
        except Exception as e:
            logger.warning(f"Could not fetch bot user: {e}")

    async def _send_comment(self, issue_id: str, comment: str, session_id: Optional[str] = None) -> None:
        """Send a comment to a Linear issue."""
        try:
            mutation = """mutation($input: CommentCreateInput!) {
              commentCreate(input: $input) {
                success
                comment { id url }
              }
            }"""
            
            variables = {
                "input": {
                    "issueId": issue_id,
                    "body": comment
                }
            }
            
            data = await self._gql_query(mutation, variables)
            
            if data.get("commentCreate", {}).get("success"):
                logger.info(f"Comment posted to issue {issue_id}")
                
                # Optionally update agent session status
                if session_id:
                    await self._update_agent_session(session_id, "response", comment)
            else:
                logger.error("Failed to post comment to Linear")
                
        except Exception as e:
            logger.error(f"Error sending comment: {e}")

    async def _update_agent_session(self, session_id: str, activity_type: str, content: str) -> None:
        """Update agent session with activity."""
        try:
            mutation = """mutation($input: AgentActivityCreateInput!) {
              agentActivityCreate(input: $input) {
                success
              }
            }"""
            
            variables = {
                "input": {
                    "agentSessionId": session_id,
                    "type": activity_type,
                    "content": content
                }
            }
            
            await self._gql_query(mutation, variables)
            
        except Exception as e:
            logger.debug(f"Could not update agent session: {e}")

    async def _gql_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute GraphQL query against Linear API."""
        if not self._http_session:
            raise RuntimeError("HTTP session not initialized")
            
        # OAuth tokens require Bearer prefix, API keys are sent raw
        auth_header = f"Bearer {self._token}" if self._is_oauth else self._token
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
        
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        import aiohttp
        async with self._http_session.post(
            LINEAR_API_BASE,
            headers=headers,
            data=json.dumps(payload),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            data = await response.json()
            
            if "errors" in data:
                raise RuntimeError(f"Linear API error: {data['errors']}")
                
            return data.get("data", {})

    # ── Agent Integration ───────────────────────────────────────────

    def set_agent(self, agent: "Agent") -> None:
        """Set the agent that handles messages."""
        self._agent = agent

    def get_agent(self) -> Optional["Agent"]:
        """Get the current agent."""
        return self._agent

    # ── Message Sending ─────────────────────────────────────────────

    async def send_message(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        **kwargs
    ) -> BotMessage:
        """Send a message (comment) to a Linear issue."""
        text = content if isinstance(content, str) else str(content)
        try:
            await self._send_comment(channel_id, text)
            return BotMessage(
                message_id=f"linear-{channel_id}-{int(time.time())}",
                content=text,
                message_type=MessageType.TEXT,
                channel=BotChannel(channel_id=channel_id, name="Linear Issue"),
                sender=self._bot_user or BotUser(user_id="linear-bot", display_name="Linear Bot"),
                timestamp=time.time(),
                reply_to=reply_to,
                thread_id=thread_id,
                metadata={"linear_channel": channel_id}
            )
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            # Return a failed message rather than None to maintain protocol
            return BotMessage(
                message_id=f"linear-failed-{int(time.time())}",
                content=text,
                message_type=MessageType.TEXT,
                channel=BotChannel(channel_id=channel_id, name="Linear Issue"),
                sender=self._bot_user or BotUser(user_id="linear-bot", display_name="Linear Bot"),
                timestamp=time.time(),
                reply_to=reply_to,
                thread_id=thread_id,
                metadata={"error": str(e), "linear_channel": channel_id}
            )
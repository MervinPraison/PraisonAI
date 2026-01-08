"""
ACP Server implementation for PraisonAI.

This module implements the Agent Client Protocol server that allows
IDEs/editors to communicate with PraisonAI agents.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .config import ACPConfig
from .session import ACPSession, SessionStore

# Configure logging to stderr only (stdout reserved for JSON-RPC)
logger = logging.getLogger(__name__)


def _setup_stderr_logging(debug: bool = False) -> None:
    """Configure logging to stderr only."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    
    root_logger = logging.getLogger("praisonai.acp")
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)


class ACPServer:
    """
    ACP Server that exposes PraisonAI agents to IDE clients.
    
    Implements the Agent Client Protocol (JSON-RPC 2.0 over stdio).
    """
    
    def __init__(
        self,
        config: Optional[ACPConfig] = None,
        agent: Optional[Any] = None,
        agents: Optional[Any] = None,
    ):
        """
        Initialize ACP server.
        
        Args:
            config: ACP configuration
            agent: Optional pre-configured Agent instance
            agents: Optional pre-configured Agents instance
        """
        self.config = config or ACPConfig()
        self._agent = agent
        self._agents = agents
        self._session_store = SessionStore()
        self._sessions: Dict[str, ACPSession] = {}
        self._client = None  # ACP client connection
        self._cancelled_sessions: set = set()
        
        _setup_stderr_logging(self.config.debug)
    
    def _get_agent(self):
        """Lazy load or create agent."""
        if self._agent is not None:
            return self._agent
        
        if self._agents is not None:
            return self._agents
        
        # Create default agent
        try:
            from praisonaiagents import Agent
            self._agent = Agent(
                name="PraisonAI",
                instructions="You are a helpful AI coding assistant.",
                model=self.config.model or "gpt-4o-mini",
            )
            return self._agent
        except ImportError:
            logger.error("praisonaiagents not installed")
            raise RuntimeError("praisonaiagents package required")
    
    def on_connect(self, client) -> None:
        """Called when client connects."""
        self._client = client
        logger.info("Client connected")
    
    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Optional[Dict[str, Any]] = None,
        client_info: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Handle initialize request.
        
        Negotiate protocol version and exchange capabilities.
        """
        logger.info(f"Initialize: protocol_version={protocol_version}, client_info={client_info}")
        
        # Import here to avoid circular imports and check availability
        try:
            from acp import PROTOCOL_VERSION
        except ImportError:
            PROTOCOL_VERSION = 1
        
        return {
            "protocolVersion": min(protocol_version, PROTOCOL_VERSION),
            "agentCapabilities": {
                "loadSession": True,
                "promptCapabilities": {
                    "image": False,
                    "audio": False,
                    "embeddedContext": True,
                },
                "mcpCapabilities": {
                    "http": False,
                    "sse": False,
                },
            },
            "agentInfo": {
                "name": "praisonai",
                "title": "PraisonAI",
                "version": self._get_version(),
            },
            "authMethods": [],
        }
    
    async def authenticate(self, method_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Handle authenticate request (optional)."""
        logger.info(f"Authenticate: method_id={method_id}")
        return {}
    
    async def new_session(
        self,
        cwd: str,
        mcp_servers: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Create a new conversation session.
        
        Args:
            cwd: Working directory for the session
            mcp_servers: List of MCP server configurations
        """
        logger.info(f"New session: cwd={cwd}")
        
        workspace = Path(cwd).resolve()
        session = ACPSession.create(
            workspace=workspace,
            agent_id=self.config.agent,
        )
        session.mcp_servers = mcp_servers
        
        self._sessions[session.session_id] = session
        self._session_store.save(session)
        
        logger.info(f"Created session: {session.session_id}")
        
        return {
            "sessionId": session.session_id,
            "modes": self._get_available_modes(),
        }
    
    async def load_session(
        self,
        cwd: str,
        mcp_servers: List[Dict[str, Any]],
        session_id: str,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Load an existing session.
        
        Replays conversation history via session/update notifications.
        """
        logger.info(f"Load session: session_id={session_id}")
        
        # Try to load from store
        session = self._session_store.load(session_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None
        
        # Update workspace and MCP servers
        session.workspace = Path(cwd).resolve()
        session.mcp_servers = mcp_servers
        session.update_activity()
        
        self._sessions[session_id] = session
        
        # Replay conversation history
        await self._replay_session_history(session)
        
        return {}
    
    async def list_sessions(
        self,
        cursor: Optional[str] = None,
        cwd: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """List available sessions."""
        sessions = self._session_store.list_sessions()
        
        # Filter by cwd if provided
        if cwd:
            cwd_path = Path(cwd).resolve()
            sessions = [s for s in sessions if s.workspace == cwd_path]
        
        return {
            "sessions": [
                {
                    "sessionId": s.session_id,
                    "createdAt": s.created_at,
                    "lastActivity": s.last_activity,
                }
                for s in sessions
            ],
        }
    
    async def set_session_mode(
        self,
        mode_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Set the operating mode for a session."""
        logger.info(f"Set session mode: session_id={session_id}, mode_id={mode_id}")
        
        session = self._sessions.get(session_id)
        if session:
            session.mode = mode_id
            self._session_store.save(session)
        
        return {}
    
    async def set_session_model(
        self,
        model_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Set the LLM model for a session."""
        logger.info(f"Set session model: session_id={session_id}, model_id={model_id}")
        
        session = self._sessions.get(session_id)
        if session:
            session.model = model_id
            self._session_store.save(session)
        
        return {}
    
    async def prompt(
        self,
        prompt: List[Dict[str, Any]],
        session_id: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Handle user prompt.
        
        This is the main interaction method where the user sends a message
        and the agent processes it.
        """
        logger.info(f"Prompt: session_id={session_id}")
        
        session = self._sessions.get(session_id)
        if session is None:
            logger.error(f"Session not found: {session_id}")
            return {"stopReason": "refusal"}
        
        # Check if cancelled
        if session_id in self._cancelled_sessions:
            self._cancelled_sessions.discard(session_id)
            return {"stopReason": "cancelled"}
        
        # Extract text from prompt blocks
        user_message = self._extract_prompt_text(prompt)
        session.add_message("user", user_message)
        
        try:
            # Get agent response
            agent = self._get_agent()
            
            # Send thinking update
            await self._send_thought(session_id, "Processing your request...")
            
            # Generate response
            response = await self._generate_response(agent, user_message, session)
            
            # Send response as agent message chunks
            await self._send_agent_message(session_id, response)
            
            # Save session
            session.add_message("assistant", response)
            self._session_store.save(session)
            
            return {"stopReason": "end_turn"}
            
        except asyncio.CancelledError:
            return {"stopReason": "cancelled"}
        except Exception as e:
            logger.exception(f"Error processing prompt: {e}")
            await self._send_agent_message(session_id, f"Error: {str(e)}")
            return {"stopReason": "refusal"}
    
    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Fork an existing session."""
        logger.info(f"Fork session: session_id={session_id}")
        
        original = self._sessions.get(session_id)
        if original is None:
            original = self._session_store.load(session_id)
        
        if original is None:
            # Create new session if original not found
            return await self.new_session(cwd, mcp_servers or [])
        
        # Create forked session
        forked = ACPSession.create(
            workspace=Path(cwd).resolve(),
            agent_id=original.agent_id,
        )
        forked.messages = original.messages.copy()
        forked.mcp_servers = mcp_servers or original.mcp_servers
        
        self._sessions[forked.session_id] = forked
        self._session_store.save(forked)
        
        return {"sessionId": forked.session_id}
    
    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Resume an existing session."""
        return await self.load_session(cwd, mcp_servers or [], session_id)
    
    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Cancel ongoing operations for a session."""
        logger.info(f"Cancel: session_id={session_id}")
        self._cancelled_sessions.add(session_id)
    
    async def ext_method(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle extension method calls."""
        logger.info(f"Extension method: {method}")
        return {"error": f"Unknown extension method: {method}"}
    
    async def ext_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Handle extension notifications."""
        logger.info(f"Extension notification: {method}")
    
    # Helper methods
    
    def _get_version(self) -> str:
        """Get PraisonAI version."""
        try:
            from praisonai.version import __version__
            return __version__
        except ImportError:
            return "0.0.0"
    
    def _get_available_modes(self) -> Optional[List[Dict[str, Any]]]:
        """Get available operating modes."""
        return [
            {
                "id": "manual",
                "name": "Manual",
                "description": "Requires approval for all actions",
            },
            {
                "id": "auto",
                "name": "Auto",
                "description": "Auto-approve within workspace",
            },
        ]
    
    def _extract_prompt_text(self, prompt: List[Dict[str, Any]]) -> str:
        """Extract text content from prompt blocks."""
        texts = []
        for block in prompt:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    texts.append(block.get("text", ""))
                elif block_type == "resource":
                    resource = block.get("resource", {})
                    if "text" in resource:
                        texts.append(f"[File: {resource.get('uri', 'unknown')}]\n{resource['text']}")
        return "\n".join(texts)
    
    async def _generate_response(
        self,
        agent: Any,
        message: str,
        session: ACPSession,
    ) -> str:
        """Generate agent response."""
        try:
            # Try async chat first
            if hasattr(agent, "achat"):
                response = await agent.achat(message)
            elif hasattr(agent, "chat"):
                # Run sync chat in executor
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, agent.chat, message)
            else:
                response = "Agent does not support chat interface"
            
            return str(response) if response else ""
        except Exception as e:
            logger.exception(f"Error generating response: {e}")
            return f"Error generating response: {str(e)}"
    
    async def _send_agent_message(self, session_id: str, text: str) -> None:
        """Send agent message chunk to client."""
        if self._client is None:
            return
        
        try:
            from acp import update_agent_message_text
            update = update_agent_message_text(text)
            await self._client.session_update(session_id=session_id, update=update)
        except ImportError:
            # Fallback without ACP SDK
            logger.debug(f"Agent message: {text[:100]}...")
    
    async def _send_thought(self, session_id: str, text: str) -> None:
        """Send agent thought to client."""
        if self._client is None:
            return
        
        try:
            from acp import update_agent_thought_text
            update = update_agent_thought_text(text)
            await self._client.session_update(session_id=session_id, update=update)
        except ImportError:
            logger.debug(f"Agent thought: {text}")
    
    async def _replay_session_history(self, session: ACPSession) -> None:
        """Replay session history to client."""
        if self._client is None:
            return
        
        try:
            from acp import update_user_message_text, update_agent_message_text
            
            for msg in session.messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                
                if role == "user":
                    update = update_user_message_text(str(content))
                elif role == "assistant":
                    update = update_agent_message_text(str(content))
                else:
                    continue
                
                await self._client.session_update(
                    session_id=session.session_id,
                    update=update,
                )
        except ImportError:
            logger.debug("Skipping history replay (ACP SDK not available)")


async def _run_server(config: ACPConfig) -> None:
    """Run the ACP server."""
    try:
        from acp import Agent as ACPAgent, run_agent
    except ImportError:
        logger.error(
            "agent-client-protocol package not installed.\n"
            "Install with: pip install praisonai[acp]\n"
            "Or: pip install agent-client-protocol"
        )
        sys.exit(1)
    
    server = ACPServer(config=config)
    
    # Create ACP-compatible agent wrapper
    class PraisonACPAgent(ACPAgent):
        def on_connect(self, conn):
            server.on_connect(conn)
        
        async def initialize(self, protocol_version, client_capabilities=None, client_info=None, **kwargs):
            return await server.initialize(protocol_version, client_capabilities, client_info, **kwargs)
        
        async def authenticate(self, method_id, **kwargs):
            return await server.authenticate(method_id, **kwargs)
        
        async def new_session(self, cwd, mcp_servers, **kwargs):
            return await server.new_session(cwd, mcp_servers, **kwargs)
        
        async def load_session(self, cwd, mcp_servers, session_id, **kwargs):
            return await server.load_session(cwd, mcp_servers, session_id, **kwargs)
        
        async def list_sessions(self, cursor=None, cwd=None, **kwargs):
            return await server.list_sessions(cursor, cwd, **kwargs)
        
        async def set_session_mode(self, mode_id, session_id, **kwargs):
            return await server.set_session_mode(mode_id, session_id, **kwargs)
        
        async def set_session_model(self, model_id, session_id, **kwargs):
            return await server.set_session_model(model_id, session_id, **kwargs)
        
        async def prompt(self, prompt, session_id, **kwargs):
            return await server.prompt(prompt, session_id, **kwargs)
        
        async def fork_session(self, cwd, session_id, mcp_servers=None, **kwargs):
            return await server.fork_session(cwd, session_id, mcp_servers, **kwargs)
        
        async def resume_session(self, cwd, session_id, mcp_servers=None, **kwargs):
            return await server.resume_session(cwd, session_id, mcp_servers, **kwargs)
        
        async def cancel(self, session_id, **kwargs):
            return await server.cancel(session_id, **kwargs)
        
        async def ext_method(self, method, params):
            return await server.ext_method(method, params)
        
        async def ext_notification(self, method, params):
            return await server.ext_notification(method, params)
    
    logger.info("Starting PraisonAI ACP server...")
    await run_agent(PraisonACPAgent(), use_unstable_protocol=True)


def serve(
    workspace: Union[str, Path] = ".",
    agent: str = "default",
    model: Optional[str] = None,
    resume: Optional[str] = None,
    resume_last: bool = False,
    debug: bool = False,
    read_only: bool = True,
    allow_write: bool = False,
    allow_shell: bool = False,
    approval_mode: str = "manual",
    **kwargs: Any,
) -> None:
    """
    Start the ACP server.
    
    This is the main entry point for running PraisonAI as an ACP agent.
    
    Args:
        workspace: Working directory for the session
        agent: Agent name or configuration
        model: LLM model to use
        resume: Session ID to resume
        resume_last: Resume the last session
        debug: Enable debug logging
        read_only: Read-only mode (default True)
        allow_write: Allow file writes
        allow_shell: Allow shell commands
        approval_mode: Approval mode (manual, auto, scoped)
    """
    config = ACPConfig(
        workspace=Path(workspace).resolve(),
        agent=agent,
        model=model,
        resume_session=resume,
        resume_last=resume_last,
        debug=debug,
        read_only=read_only,
        allow_write=allow_write,
        allow_shell=allow_shell,
        approval_mode=approval_mode,
    )
    
    asyncio.run(_run_server(config))

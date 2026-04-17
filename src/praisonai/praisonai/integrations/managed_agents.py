"""
External Managed Agent Backends Integration.

Provides integration with Anthropic's Managed Agents API as an execution backend
for PraisonAI Agents. Uses the official Anthropic Python SDK (v0.94+) which handles
beta headers, authentication, and SSE streaming natively.

Implements ``ManagedBackendProtocol`` from the Core SDK.

Usage::

    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig
    from praisonaiagents import Agent

    # Create managed backend
    managed = ManagedAgent(
        config=ManagedConfig(
            model="claude-sonnet-4-6",
            system="You are a coding assistant.",
            tools=[{"type": "agent_toolset_20260401"}],
            packages={"pip": ["pandas"]},
        )
    )

    # Use with PraisonAI Agent
    agent = Agent(name="coder", backend=managed)
    result = agent.start("Create a Python script that prints hello")
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ManagedConfig — Anthropic-specific configuration dataclass
# Lives in the Wrapper (not Core SDK) because its fields map directly to
# the Anthropic Managed Agents API.  The Core SDK only defines the
# provider-agnostic ManagedBackendProtocol.
# ---------------------------------------------------------------------------

@dataclass
class ManagedConfig:
    """Configuration for Anthropic Managed Agent backends.

    Dataclass that describes *what* to create on Anthropic's managed
    infrastructure.  Provider-specific — not part of the Core SDK.

    Example::

        cfg = ManagedConfig(
            model="claude-haiku-4-5",
            system="You are a helpful coding assistant.",
            tools=[{"type": "agent_toolset_20260401"}],
            packages={"pip": ["pandas", "numpy"]},
            networking={"type": "unrestricted"},
        )
    """
    # ── Agent fields ──
    name: str = "Agent"
    model: str = "claude-haiku-4-5"
    system: str = "You are a helpful coding assistant."
    tools: List[Dict[str, Any]] = field(default_factory=lambda: [{"type": "agent_toolset_20260401"}])
    mcp_servers: List[Dict[str, Any]] = field(default_factory=list)
    skills: List[Dict[str, Any]] = field(default_factory=list)
    callable_agents: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── Environment fields ──
    env_name: str = "praisonai-env"
    packages: Optional[Dict[str, List[str]]] = None
    networking: Dict[str, Any] = field(default_factory=lambda: {"type": "unrestricted"})

    # ── Session fields ──
    session_title: str = "PraisonAI session"
    resources: List[Dict[str, Any]] = field(default_factory=list)
    vault_ids: List[str] = field(default_factory=list)


class AnthropicManagedAgent:
    """Anthropic Managed Agents backend for PraisonAI.

    Satisfies ``ManagedBackendProtocol`` (Core SDK).  All heavy SDK usage
    (``anthropic`` import) is lazy — import only on first use.

    Lifecycle:
        1. ``_ensure_agent()``       — create (or reuse) an agent definition
        2. ``_ensure_environment()``  — create (or reuse) a sandbox environment
        3. ``_ensure_session()``      — create (or reuse) a running session
        4. ``execute()`` / ``stream()`` — send user message, collect events

    Supports the full Managed Agents API surface:
    - Agent: model, system, tools (agent_toolset, mcp_toolset, custom),
      mcp_servers, skills, callable_agents, metadata
    - Environment: packages (pip/npm/apt/…), networking (unrestricted/limited)
    - Session: resources (files, memory_stores), vault_ids
    - Events: agent.message, agent.tool_use, agent.custom_tool_use,
      session.status_idle, tool confirmation
    - Usage tracking: input_tokens, output_tokens per turn
    """

    def __init__(
        self,
        provider: str = "anthropic",
        api_key: Optional[str] = None,
        config: Optional[Any] = None,
        timeout: int = 600,
        instructions: str = "You are a helpful coding assistant.",
        on_tool_confirmation: Optional[Callable[[Dict[str, Any]], bool]] = None,
        on_custom_tool: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ):
        self.provider = provider
        self.api_key = (
            api_key
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("CLAUDE_API_KEY")
        )
        self.timeout = timeout
        self.instructions = instructions
        self.on_tool_confirmation = on_tool_confirmation
        self.on_custom_tool = on_custom_tool

        # Accept ManagedConfig dataclass *or* plain dict
        if config is not None and not isinstance(config, dict):
            # Assume dataclass — convert to dict
            from dataclasses import asdict
            self._cfg = asdict(config)
        else:
            self._cfg: Dict[str, Any] = config or {}

        # Cached IDs for reuse across calls
        self.agent_id: Optional[str] = None
        self.agent_version: Optional[int] = None
        self.environment_id: Optional[str] = None
        self._session_id: Optional[str] = None
        self._client: Any = None

        # Usage tracking (accumulated per instance)
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    # ------------------------------------------------------------------
    # Client
    # ------------------------------------------------------------------
    def _get_client(self):
        """Lazy-init Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic SDK required for managed agents. "
                    "Install with: pip install 'anthropic>=0.94.0'"
                )
            if not self.api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. "
                    "Export it or pass api_key= to ManagedAgent."
                )
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    # ------------------------------------------------------------------
    # Agent
    # ------------------------------------------------------------------
    def _ensure_agent(self) -> str:
        """Create agent if not cached, return agent_id."""
        if self.agent_id:
            return self.agent_id

        client = self._get_client()
        c = self._cfg

        kwargs: Dict[str, Any] = {
            "name": c.get("name", "Agent"),
            "model": c.get("model", "claude-haiku-4-5"),
            "system": c.get("system", self.instructions),
            "tools": c.get("tools", [{"type": "agent_toolset_20260401"}]),
        }
        # Optional fields — only send if non-empty
        if c.get("mcp_servers"):
            kwargs["mcp_servers"] = c["mcp_servers"]
        if c.get("skills"):
            kwargs["skills"] = c["skills"]
        if c.get("callable_agents"):
            kwargs["callable_agents"] = c["callable_agents"]
        if c.get("metadata"):
            kwargs["metadata"] = c["metadata"]

        agent = client.beta.agents.create(**kwargs)
        self.agent_id = agent.id
        self.agent_version = getattr(agent, "version", None)
        logger.info(
            "[managed] agent created: %s (v%s)", agent.id, self.agent_version
        )
        return self.agent_id

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------
    def _ensure_environment(self) -> str:
        """Create environment if not cached, return environment_id."""
        if self.environment_id:
            return self.environment_id

        client = self._get_client()
        c = self._cfg

        env_config: Dict[str, Any] = {
            "type": "cloud",
            "networking": c.get("networking", {"type": "unrestricted"}),
        }
        if c.get("packages"):
            env_config["packages"] = c["packages"]

        environment = client.beta.environments.create(
            name=c.get("env_name", "praisonai-env"),
            config=env_config,
        )
        self.environment_id = environment.id
        logger.info("[managed] environment created: %s", environment.id)
        return self.environment_id

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    def _ensure_session(self) -> str:
        """Create session if not cached, return session_id."""
        if self._session_id:
            return self._session_id

        client = self._get_client()
        agent_id = self._ensure_agent()
        env_id = self._ensure_environment()
        c = self._cfg

        kwargs: Dict[str, Any] = {
            "agent": agent_id,
            "environment_id": env_id,
            "title": c.get("session_title", "PraisonAI session"),
        }
        if c.get("resources"):
            kwargs["resources"] = c["resources"]
        if c.get("vault_ids"):
            kwargs["vault_ids"] = c["vault_ids"]

        session = client.beta.sessions.create(**kwargs)
        self._session_id = session.id
        logger.info("[managed] session created: %s", session.id)
        return self._session_id

    # ------------------------------------------------------------------
    # Event processing helpers
    # ------------------------------------------------------------------
    def _process_events(self, client, session_id, stream, *, collect: bool = True, stream_live: bool = False, emitter=None):
        """Walk the SSE stream and return (text_parts, tool_log).

        Handles:
        - ``agent.message``          → collect text
        - ``agent.tool_use``         → log tool invocations
        - ``agent.custom_tool_use``  → call ``on_custom_tool`` callback
        - ``session.status_idle``    → break (turn is done)
        - tool confirmation requests → call ``on_tool_confirmation``
        - usage tracking             → accumulate token counts

        Args:
            stream_live: If True, print text chunks to stdout as they arrive.
            emitter: ContextTraceEmitter for trace events.
        """
        import sys as _sys
        import time

        text_parts: List[str] = []
        tool_log: List[str] = []
        tool_start_times = {}  # Track tool start times for duration calculation

        for event in stream:
            etype = getattr(event, "type", None)

            if etype == "agent.message":
                for block in getattr(event, "content", []):
                    text = getattr(block, "text", None)
                    if text and collect:
                        text_parts.append(text)
                    if text and stream_live:
                        _sys.stdout.write(text)
                        _sys.stdout.flush()

            elif etype == "agent.tool_use":
                name = getattr(event, "name", "unknown")
                tool_id = getattr(event, "id", "")
                tool_input = getattr(event, "input", {})
                
                tool_log.append(name)
                logger.debug("[managed] tool_use: %s", name)
                if stream_live:
                    _sys.stdout.write(f"\n[Using tool: {name}]\n")
                    _sys.stdout.flush()

                # Emit tool_call_start event
                if emitter:
                    agent_name = self._cfg.get("name", "Agent")
                    emitter.tool_call_start(agent_name, name, tool_input)
                    tool_start_times[tool_id] = time.time()

                # Handle tool confirmation (always_ask policy)
                if getattr(event, "needs_confirmation", False):
                    approved = True
                    if self.on_tool_confirmation:
                        info = {
                            "name": name,
                            "input": tool_input,
                            "tool_use_id": tool_id,
                        }
                        approved = self.on_tool_confirmation(info)
                    # Send confirmation back
                    client.beta.sessions.events.send(
                        session_id,
                        events=[{
                            "type": "user.tool_confirmation",
                            "tool_use_id": tool_id,
                            "allowed": approved,
                        }],
                    )

                # Emit synthetic tool_call_end since Anthropic doesn't provide a direct end event
                # We emit this immediately after the tool_use event for now
                if emitter and tool_id in tool_start_times:
                    duration_ms = (time.time() - tool_start_times[tool_id]) * 1000
                    agent_name = self._cfg.get("name", "Agent")
                    emitter.tool_call_end(agent_name, name, duration_ms=duration_ms)
                    del tool_start_times[tool_id]

            elif etype == "agent.custom_tool_use":
                tool_name = getattr(event, "name", "custom_tool")
                tool_input = getattr(event, "input", {})
                tool_use_id = getattr(event, "id", "")
                logger.debug("[managed] custom_tool_use: %s", tool_name)

                result = ""
                if self.on_custom_tool:
                    try:
                        result = self.on_custom_tool(tool_name, tool_input)
                    except Exception as exc:
                        result = f"Error: {exc}"
                        logger.warning("[managed] custom tool error: %s", exc)

                # Return custom tool result
                client.beta.sessions.events.send(
                    session_id,
                    events=[{
                        "type": "user.custom_tool_result",
                        "custom_tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": str(result)}],
                    }],
                )

            elif etype == "session.status_idle":
                logger.debug("[managed] session idle — turn done")
                break

            elif etype == "session.error":
                err = getattr(event, "error", None)
                error_msg = getattr(err, "message", None) or str(err) or "Unknown error"
                logger.error("[managed] session error: %s", error_msg)
                break

            # Usage tracking (from event.usage or span.model_usage)
            usage = getattr(event, "usage", None) or getattr(event, "model_usage", None)
            if usage:
                in_t = getattr(usage, "input_tokens", 0)
                out_t = getattr(usage, "output_tokens", 0)
                if isinstance(in_t, int):
                    self.total_input_tokens += in_t
                if isinstance(out_t, int):
                    self.total_output_tokens += out_t

        if tool_log:
            logger.info("[managed] tools used: %s", tool_log)

        return text_parts, tool_log

    # ------------------------------------------------------------------
    # execute() — ManagedBackendProtocol
    # ------------------------------------------------------------------
    async def execute(self, prompt: str, **kwargs) -> str:
        """Execute prompt on managed infrastructure and return the full response.

        Runs the synchronous Anthropic SDK in a thread executor to stay async-safe.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._execute_sync, prompt)

    def _execute_sync(self, prompt: str, stream_live: bool = False) -> str:
        """Synchronous execution using the SDK's native streaming.

        Args:
            stream_live: If True, print text chunks to stdout as they arrive
                         (token-by-token streaming). The full text is still returned.
        """
        import sys
        
        # Get context emitter (zero-overhead when no emitter is installed)
        try:
            from praisonaiagents.trace.context_events import get_context_emitter
            emitter = get_context_emitter()
        except ImportError:
            emitter = None

        client = self._get_client()
        session_id = self._ensure_session()
        agent_name = self._cfg.get("name", "Agent")

        # Emit agent_start event
        if emitter:
            emitter.agent_start(agent_name, {
                "input": prompt,
                "goal": self._cfg.get("system", self.instructions)
            })

        try:
            with client.beta.sessions.events.stream(session_id) as stream:
                client.beta.sessions.events.send(
                    session_id,
                    events=[{
                        "type": "user.message",
                        "content": [{"type": "text", "text": prompt}],
                    }],
                )
                text_parts, _ = self._process_events(
                    client, session_id, stream, collect=True,
                    stream_live=stream_live, emitter=emitter,
                )

            if stream_live:
                sys.stdout.write("\n")
                sys.stdout.flush()

            full_response = "".join(text_parts)
            
            # Emit llm_response event for aggregated text
            if emitter and full_response:
                emitter.llm_response(
                    agent_name, 
                    response_content=full_response,
                    prompt_tokens=self.total_input_tokens,
                    completion_tokens=self.total_output_tokens
                )

            return full_response
        
        finally:
            # Emit agent_end event
            if emitter:
                emitter.agent_end(agent_name)

    # ------------------------------------------------------------------
    # stream() — ManagedBackendProtocol
    # ------------------------------------------------------------------
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Yield text chunks as the managed agent produces them."""
        loop = asyncio.get_running_loop()
        import queue
        import threading

        q: queue.Queue[Optional[str]] = queue.Queue()

        def _producer():
            try:
                client = self._get_client()
                session_id = self._ensure_session()
                with client.beta.sessions.events.stream(session_id) as s:
                    client.beta.sessions.events.send(
                        session_id,
                        events=[{
                            "type": "user.message",
                            "content": [{"type": "text", "text": prompt}],
                        }],
                    )
                    for event in s:
                        etype = getattr(event, "type", None)
                        if etype == "agent.message":
                            for block in getattr(event, "content", []):
                                text = getattr(block, "text", None)
                                if text:
                                    q.put(text)
                        elif etype == "session.status_idle":
                            break
            finally:
                q.put(None)  # sentinel

        thread = threading.Thread(target=_producer, daemon=True)
        thread.start()

        while True:
            chunk = await loop.run_in_executor(None, q.get)
            if chunk is None:
                break
            yield chunk

    # ------------------------------------------------------------------
    # Session management — ManagedBackendProtocol
    # ------------------------------------------------------------------
    def reset_session(self) -> None:
        """Discard cached session; next execute() creates a fresh one."""
        self._session_id = None

    def reset_all(self) -> None:
        """Discard all cached state (agent, environment, session, client)."""
        self.agent_id = None
        self.agent_version = None
        self.environment_id = None
        self._session_id = None
        self._client = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    # ------------------------------------------------------------------
    # update_agent — ManagedBackendProtocol
    # ------------------------------------------------------------------
    def update_agent(self, **kwargs) -> None:
        """Update an existing managed agent's configuration.

        Wraps ``client.beta.agents.update(agent_id, ...)`` to change the
        system prompt, tools, model, etc. without recreating the agent.
        After update, a new session should be created (old one is stale).
        """
        if not self.agent_id:
            logger.warning("[managed] update_agent called but no agent exists yet")
            return
        client = self._get_client()
        if "version" not in kwargs and self.agent_version is not None:
            kwargs["version"] = self.agent_version
        updated = client.beta.agents.update(self.agent_id, **kwargs)
        self.agent_version = getattr(updated, "version", self.agent_version)
        logger.info(
            "[managed] agent updated: %s (v%s)", self.agent_id, self.agent_version
        )
        # Invalidate session — updated agent needs a fresh session
        self._session_id = None

    # ------------------------------------------------------------------
    # interrupt — ManagedBackendProtocol
    # ------------------------------------------------------------------
    def interrupt(self) -> None:
        """Send a user.interrupt event to the active session."""
        if not self._session_id:
            logger.warning("[managed] interrupt called but no active session")
            return
        client = self._get_client()
        client.beta.sessions.events.send(
            self._session_id,
            events=[{"type": "user.interrupt"}],
        )
        logger.info("[managed] interrupt sent to session %s", self._session_id)

    # ------------------------------------------------------------------
    # retrieve_session — ManagedBackendProtocol
    # ------------------------------------------------------------------
    def retrieve_session(self) -> Dict[str, Any]:
        """Retrieve current session metadata and usage from the API using unified schema."""
        if not self._session_id:
            return {}
        client = self._get_client()
        sess = client.beta.sessions.retrieve(self._session_id)
        
        # Build usage dict if available
        usage_dict = None
        usage = getattr(sess, "usage", None)
        if usage:
            usage_dict = {
                "input_tokens": getattr(usage, "input_tokens", 0),
                "output_tokens": getattr(usage, "output_tokens", 0),
            }
        
        # Use unified SessionInfo schema for consistency with Local backend
        try:
            from praisonaiagents.managed import SessionInfo
            session_info = SessionInfo(
                id=getattr(sess, "id", self._session_id),
                status=getattr(sess, "status", None),
                usage=usage_dict
            )
            return session_info.to_dict()
        except ImportError:
            # Fallback to old format if SessionInfo not available
            result: Dict[str, Any] = {
                "id": getattr(sess, "id", self._session_id),
                "status": getattr(sess, "status", None),
            }
            if usage_dict:
                result["usage"] = usage_dict
            return result

    # ------------------------------------------------------------------
    # list_sessions — ManagedBackendProtocol
    # ------------------------------------------------------------------
    def list_sessions(self, **kwargs) -> List[Dict[str, Any]]:
        """List sessions for the current agent."""
        if not self.agent_id:
            return []
        client = self._get_client()
        params: Dict[str, Any] = {"agent_id": self.agent_id}
        if "limit" in kwargs:
            params["limit"] = kwargs["limit"]
        sessions = client.beta.sessions.list(**params)
        result: List[Dict[str, Any]] = []
        for s in getattr(sessions, "data", sessions):
            result.append({
                "id": getattr(s, "id", None),
                "status": getattr(s, "status", None),
                "title": getattr(s, "title", None),
            })
        return result

    # ------------------------------------------------------------------
    # Session resume — attach to a known Anthropic session ID
    # ------------------------------------------------------------------
    def resume_session(self, session_id: str) -> None:
        """Resume an existing Anthropic session by ID.

        Anthropic assigns session IDs (``sesn_...``).  You cannot pick your own.
        But if you saved the ID from a previous run, pass it here to continue
        that session and preserve its context/memory.

        Also calls ``_ensure_agent()`` and ``_ensure_environment()`` so that
        agent_id and environment_id are populated (needed for list_sessions etc.).
        They are fetched lazily on the next real API call.

        Example::

            managed = ManagedAgent()
            managed.resume_session("sesn_01AbCdEf...")
            agent = Agent(name="coder", backend=managed)
            result = agent.start("Continue where we left off", stream=True)
        """
        self._session_id = session_id
        logger.info("[managed] resuming session: %s", session_id)

    # ------------------------------------------------------------------
    # ID persistence helpers — save/restore all Anthropic-assigned IDs
    # ------------------------------------------------------------------
    def save_ids(self) -> Dict[str, Any]:
        """Return a dict of all current Anthropic-assigned IDs.

        Anthropic assigns all IDs (agent, environment, session) — you cannot
        define your own.  Use this to snapshot them after the first run so you
        can restore them in a later process and avoid re-creating resources.

        Example::

            ids = managed.save_ids()
            # persist ids however you like: json file, env var, DB, etc.
            import json, pathlib
            pathlib.Path("managed_ids.json").write_text(json.dumps(ids))
        """
        return {
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "environment_id": self.environment_id,
            "session_id": self._session_id,
        }

    def restore_ids(self, ids: Dict[str, Any]) -> None:
        """Restore previously saved Anthropic-assigned IDs.

        Lets you skip agent/environment/session creation on subsequent runs
        by reusing IDs from ``save_ids()``.

        Args:
            ids: Dict returned by a previous ``save_ids()`` call.

        Example::

            import json, pathlib
            ids = json.loads(pathlib.Path("managed_ids.json").read_text())
            managed = ManagedAgent(config=cfg)
            managed.restore_ids(ids)
            agent = Agent(name="coder", backend=managed)
            result = agent.start("Continue the previous task", stream=True)
        """
        self.agent_id = ids.get("agent_id")
        self.agent_version = ids.get("agent_version")
        self.environment_id = ids.get("environment_id")
        self._session_id = ids.get("session_id")
        logger.info(
            "[managed] IDs restored — agent: %s  env: %s  session: %s",
            self.agent_id, self.environment_id, self._session_id,
        )

    # ------------------------------------------------------------------
    # PraisonAI session linkage
    # ------------------------------------------------------------------
    @property
    def session_id(self) -> Optional[str]:
        """The current Anthropic session ID (``sesn_...``)."""
        return self._session_id

    @property
    def managed_session_id(self) -> Optional[str]:
        """Backward-compatible alias for ``session_id``."""
        return self._session_id


# ---------------------------------------------------------------------------
# Tool mapping helpers
# ---------------------------------------------------------------------------
from ._tool_aliases import TOOL_ALIAS_MAP


def map_managed_tools(managed_tools: List[str]) -> List[str]:
    """Map managed agent tool names to PraisonAI tool names."""
    return [TOOL_ALIAS_MAP.get(tool, tool) for tool in managed_tools]


# ---------------------------------------------------------------------------
# Factory — ManagedAgent routes to the right backend by provider
# ---------------------------------------------------------------------------
def ManagedAgent(
    provider: Optional[str] = None,
    **kwargs,
):
    """Factory that returns the appropriate managed agent backend.

    Provider auto-detection:
        - ``ANTHROPIC_API_KEY`` set → ``AnthropicManagedAgent``
        - Otherwise → ``LocalManagedAgent``

    Explicit providers:
        - ``"anthropic"`` → ``AnthropicManagedAgent``
        - ``"local"``     → ``LocalManagedAgent`` (any LLM via litellm)
        - ``"openai"``    → ``LocalManagedAgent`` with OpenAI model
        - ``"ollama"``    → ``LocalManagedAgent`` with Ollama prefix
        - ``"gemini"``    → ``LocalManagedAgent`` with Gemini prefix

    Examples::

        # Auto-detect (Anthropic if key set, local otherwise)
        managed = ManagedAgent()

        # Explicit Anthropic
        managed = ManagedAgent(provider="anthropic", config=ManagedConfig(...))

        # Explicit local with OpenAI
        managed = ManagedAgent(provider="openai", config=LocalManagedConfig(model="gpt-4o"))

        # Ollama
        managed = ManagedAgent(provider="ollama", config=LocalManagedConfig(model="llama3"))

    Returns:
        An instance satisfying ``ManagedBackendProtocol``.
    """
    if provider is None:
        # Auto-detect
        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"):
            provider = "anthropic"
        else:
            provider = "local"

    if provider == "anthropic":
        return AnthropicManagedAgent(provider=provider, **kwargs)
    else:
        from .managed_local import LocalManagedAgent
        return LocalManagedAgent(provider=provider, **kwargs)


# ── Backward-compatible aliases ──
ManagedAgentIntegration = ManagedAgent
ManagedBackendConfig = ManagedConfig
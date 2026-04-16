"""
Local Managed Agent Backend — provider-agnostic self-hosted managed agents.

Replicates the Anthropic Managed Agents experience using any LLM provider
(OpenAI, Gemini, Ollama, local) with local sandbox execution.

Implements ``ManagedBackendProtocol`` from the Core SDK.

Usage::

    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonaiagents import Agent

    managed = LocalManagedAgent(
        config=LocalManagedConfig(
            model="gpt-4o",
            system="You are a coding assistant.",
        )
    )
    agent = Agent(name="coder", backend=managed)
    result = agent.start("Create a Python script that prints hello")
"""

import asyncio
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
)

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM = "You are a helpful coding assistant."

_DEFAULT_TOOLS = [
    "execute_command",
    "read_file",
    "write_file",
    "list_files",
    "search_web",
]

# Import unified mapping to consolidate with managed_agents
from ._tool_mapping import get_tool_alias, UNIFIED_TOOL_MAPPING

# Backward compatibility alias
TOOL_ALIAS_MAP = UNIFIED_TOOL_MAPPING


@dataclass
class LocalManagedConfig:
    """Configuration for local managed agent backends.

    Provider-agnostic — works with any LLM supported by litellm or
    OpenAI-compatible API.

    Example::

        cfg = LocalManagedConfig(
            model="gpt-4o",
            system="You are a coding assistant.",
            tools=["execute_command", "read_file", "write_file"],
        )
    """

    # ── Agent fields ──
    name: str = "Agent"
    model: str = "gpt-4o"
    system: str = _DEFAULT_SYSTEM
    tools: List[str] = field(default_factory=lambda: list(_DEFAULT_TOOLS))
    max_turns: int = 25
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── Environment fields ──
    sandbox_type: str = "subprocess"  # DEPRECATED: Use compute= parameter instead
    working_dir: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    packages: Optional[Dict[str, List[str]]] = None
    networking: Dict[str, Any] = field(default_factory=lambda: {"type": "unrestricted"})
    host_packages_ok: bool = False  # Allow pip install on host Python (unsafe)

    # ── Session fields ──
    session_title: str = "PraisonAI local session"

    # ── Callbacks ──
    on_tool_confirmation: Optional[Callable] = field(default=None, repr=False)
    on_custom_tool: Optional[Callable] = field(default=None, repr=False)


def _translate_anthropic_tools(tools_config: List) -> List[str]:
    """Translate Anthropic-format tool configs to local tool name list.

    Handles:
    - ``{"type": "agent_toolset_20260401"}`` → all defaults
    - ``{"type": "agent_toolset_20260401", "configs": [{"name": "bash", "enabled": True}]}``
    - ``{"type": "custom", "name": "..."}`` → kept as custom
    """
    if not tools_config:
        return list(_DEFAULT_TOOLS)

    # If it's already a simple list of strings, return as-is
    if tools_config and isinstance(tools_config[0], str):
        return tools_config

    enabled = set()
    disabled = set()
    custom_tools: List[Dict[str, Any]] = []
    has_agent_toolset = False

    for entry in tools_config:
        if not isinstance(entry, dict):
            continue
        t = entry.get("type", "")

        if t.startswith("agent_toolset"):
            has_agent_toolset = True
            default_enabled = entry.get("default_config", {}).get("enabled", True)
            for cfg in entry.get("configs", []):
                name = cfg.get("name", "")
                alias = get_tool_alias(name)
                if cfg.get("enabled", default_enabled):
                    enabled.add(alias)
                else:
                    disabled.add(alias)

        elif t == "custom":
            custom_tools.append(entry)

        elif t.startswith("mcp_toolset"):
            pass  # MCP handled separately

    if has_agent_toolset:
        if enabled:
            result = list(enabled - disabled)
        else:
            result = [t for t in _DEFAULT_TOOLS if t not in disabled]
    else:
        result = list(_DEFAULT_TOOLS)

    return result


# ── Custom tool builder with typed signature from JSON Schema ──

_JSON_TYPE_MAP = {"string": str, "integer": int, "number": float, "boolean": bool}


def _build_custom_tool_fn(
    tool_name: str,
    tool_desc: str,
    input_schema: Dict[str, Any],
    callback: Callable,
) -> Callable:
    """Build a callable with proper type annotations from a JSON-schema ``input_schema``.

    The Agent's tool-calling layer inspects function signatures to generate
    OpenAI-compatible function schemas.  A bare ``**kwargs`` function doesn't
    expose any parameters to the LLM, so we dynamically create a function
    whose signature mirrors the ``input_schema.properties``.
    """
    import inspect

    props = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    # Build inspect.Parameter list
    params = []
    annotations: Dict[str, Any] = {}
    for pname, pdef in props.items():
        ptype = _JSON_TYPE_MAP.get(pdef.get("type", "string"), str)
        annotations[pname] = ptype
        default = inspect.Parameter.empty if pname in required else None
        params.append(
            inspect.Parameter(pname, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default, annotation=ptype)
        )

    # Build the function
    def _custom_fn(**kwargs):
        return callback(tool_name, kwargs)

    _custom_fn.__name__ = tool_name
    _custom_fn.__qualname__ = tool_name
    _custom_fn.__doc__ = tool_desc
    _custom_fn.__signature__ = inspect.Signature(params, return_annotation=str)
    _custom_fn.__annotations__ = {**annotations, "return": str}
    return _custom_fn


class LocalManagedAgent:
    """Provider-agnostic local managed agent backend.

    Satisfies ``ManagedBackendProtocol`` (Core SDK).  Uses PraisonAI's own
    ``Agent.chat()`` loop internally to provide the full managed agent
    experience — tool calling, multi-turn, streaming — on any LLM.

    The agent loop runs locally (subprocess sandbox for tool execution).
    No external managed infrastructure required.
    """

    def __init__(
        self,
        provider: str = "local",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        config: Optional[Any] = None,
        timeout: int = 300,
        instructions: str = _DEFAULT_SYSTEM,
        on_tool_confirmation: Optional[Callable[[Dict[str, Any]], bool]] = None,
        on_custom_tool: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        compute: Optional[Any] = None,
        session_store: Optional[Any] = None,
        db: Optional[Any] = None,
    ):
        self.provider = provider
        self.api_key = api_key
        self.api_base = api_base
        self.timeout = timeout
        self.instructions = instructions
        self.on_tool_confirmation = on_tool_confirmation
        self.on_custom_tool = on_custom_tool

        if config is not None and not isinstance(config, dict):
            from dataclasses import asdict
            self._cfg = asdict(config)
        else:
            self._cfg: Dict[str, Any] = config or {}

        # Override callbacks from config if provided
        if self._cfg.get("on_tool_confirmation"):
            self.on_tool_confirmation = self._cfg.pop("on_tool_confirmation")
        if self._cfg.get("on_custom_tool"):
            self.on_custom_tool = self._cfg.pop("on_custom_tool")

        # IDs (local UUIDs, not Anthropic-assigned)
        self.agent_id: Optional[str] = None
        self.agent_version: Optional[int] = 1
        self.environment_id: Optional[str] = None
        self._session_id: Optional[str] = None

        # Usage tracking
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

        # Internal agent (lazy)
        self._inner_agent: Any = None

        # Session store: explicit > db-adapter > lazy default
        self._session_store: Any = None
        self._db: Any = db
        if session_store is not None:
            self._session_store = session_store
        elif db is not None:
            try:
                from praisonai.integrations.db_session_adapter import DbSessionAdapter
                self._session_store = DbSessionAdapter(db)
            except ImportError:
                logger.debug("[local_managed] DbSessionAdapter not available, will use file store")
        self._session_history: List[Dict[str, Any]] = []

        # Custom tool definitions from Anthropic-format config
        self._custom_tool_defs: List[Dict[str, Any]] = []

        # Compute provider (optional — for remote tool execution)
        self._compute = self._resolve_compute(compute)
        self._compute_instance_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Model resolution
    # ------------------------------------------------------------------
    def _resolve_model(self) -> str:
        """Resolve the model string from config, provider, or env."""
        model = self._cfg.get("model", "gpt-4o")

        # Provider-specific prefixes for litellm routing
        if self.provider == "ollama" and "/" not in model:
            model = f"ollama/{model}"
        elif self.provider == "gemini" and not model.startswith("gemini"):
            model = f"gemini/{model}"

        return model

    # ------------------------------------------------------------------
    # Tool resolution
    # ------------------------------------------------------------------
    def _resolve_tools(self) -> List:
        """Resolve tool names to actual PraisonAI tool functions."""
        raw_tools = self._cfg.get("tools", list(_DEFAULT_TOOLS))
        tool_names = _translate_anthropic_tools(raw_tools)

        # Normalize aliases
        resolved_names = []
        for name in tool_names:
            resolved_names.append(get_tool_alias(name))

        # Import tools lazily
        tools = []
        for name in resolved_names:
            try:
                from praisonaiagents import tools as tool_module
                func = getattr(tool_module, name, None)
                if func is not None:
                    tools.append(func)
                else:
                    logger.warning("[local_managed] tool not found: %s", name)
            except Exception as e:
                logger.warning("[local_managed] failed to load tool %s: %s", name, e)

        # Extract and wire custom tool definitions
        if isinstance(raw_tools, list):
            for entry in raw_tools:
                if isinstance(entry, dict) and entry.get("type") == "custom":
                    self._custom_tool_defs.append(entry)
                    if self.on_custom_tool:
                        tool_name = entry.get("name", "custom_tool")
                        tool_desc = entry.get("description", "")
                        input_schema = entry.get("input_schema", {})
                        callback = self.on_custom_tool

                        tools.append(
                            _build_custom_tool_fn(tool_name, tool_desc, input_schema, callback)
                        )

        return tools

    # ------------------------------------------------------------------
    # Inner agent (lazy)
    # ------------------------------------------------------------------
    def _get_session_store(self):
        """Get or create the session store."""
        if self._session_store is None:
            try:
                from praisonaiagents.session.store import get_default_session_store
                self._session_store = get_default_session_store()
            except ImportError:
                logger.debug("[local_managed] session store not available")
        return self._session_store

    # ------------------------------------------------------------------
    # State persistence — write all mutable state to session store
    # ------------------------------------------------------------------
    def _persist_state(self) -> None:
        """Persist all mutable agent state to the session store.

        Writes agent metadata (IDs, version), usage tokens, session history,
        and compute instance references into the session's metadata dict.
        """
        store = self._get_session_store()
        if not store or not self._session_id:
            return

        state = {
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "environment_id": self.environment_id,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "compute_instance_id": self._compute_instance_id,
            "compute_provider": self._compute.provider_name if self._compute and hasattr(self._compute, "provider_name") else None,
            "session_history": self._session_history,
            "config": {
                "model": self._cfg.get("model"),
                "system": self._cfg.get("system", self.instructions),
                "name": self._cfg.get("name", "Agent"),
                "provider": self.provider,
            },
        }

        # DbSessionAdapter path — has set_metadata/get_metadata
        if hasattr(store, "set_metadata"):
            store.set_metadata(self._session_id, state)
            return

        # DefaultSessionStore path — write into SessionData.metadata
        try:
            session = store.get_session(self._session_id)
            if session is not None:
                if not isinstance(session.metadata, dict):
                    session.metadata = {}
                session.metadata.update(state)
                store._save_session(session)
            else:
                from praisonaiagents.session.store import SessionData
                new_session = SessionData(session_id=self._session_id, metadata=state)
                store._save_session(new_session)
        except Exception as e:
            logger.debug("[local_managed] _persist_state failed: %s", e)

    def _restore_state(self) -> None:
        """Restore all mutable state from the session store.

        Called during ``resume_session()`` to recover agent metadata,
        usage tokens, compute refs, and session history.
        """
        store = self._get_session_store()
        if not store or not self._session_id:
            return

        meta: Dict[str, Any] = {}

        # DbSessionAdapter path
        if hasattr(store, "get_metadata"):
            meta = store.get_metadata(self._session_id) or {}
        else:
            # DefaultSessionStore path
            try:
                session = store.get_session(self._session_id)
                if session and isinstance(session.metadata, dict):
                    meta = session.metadata
            except Exception:
                pass

        if not meta:
            return

        # Restore IDs (only if not already set by restore_ids())
        if meta.get("agent_id") and not self.agent_id:
            self.agent_id = meta["agent_id"]
        if meta.get("agent_version") is not None and self.agent_version in (None, 1):
            self.agent_version = meta["agent_version"]
        if meta.get("environment_id") and not self.environment_id:
            self.environment_id = meta["environment_id"]

        # Restore usage
        self.total_input_tokens = meta.get("total_input_tokens", self.total_input_tokens)
        self.total_output_tokens = meta.get("total_output_tokens", self.total_output_tokens)

        # Restore compute ref
        if meta.get("compute_instance_id"):
            self._compute_instance_id = meta["compute_instance_id"]

        # Restore session history
        if meta.get("session_history"):
            self._session_history = meta["session_history"]

        # Restore config (so resume doesn't need config re-specified)
        saved_cfg = meta.get("config", {})
        if saved_cfg:
            if saved_cfg.get("model") and not self._cfg.get("model"):
                self._cfg["model"] = saved_cfg["model"]
            if saved_cfg.get("system") and not self._cfg.get("system"):
                self._cfg["system"] = saved_cfg["system"]
                self.instructions = saved_cfg["system"]
            if saved_cfg.get("name") and not self._cfg.get("name"):
                self._cfg["name"] = saved_cfg["name"]
            if saved_cfg.get("provider"):
                self.provider = saved_cfg["provider"]

    async def _install_packages(self) -> None:
        """Install packages specified in config before agent starts."""
        packages = self._cfg.get("packages")
        if not packages:
            return

        pip_pkgs = packages.get("pip", []) if isinstance(packages, dict) else []
        if not pip_pkgs:
            return

        # If compute provider is attached, install in sandbox
        if self._compute and self._compute_instance_id:
            logger.info("[local_managed] installing pip packages in sandbox: %s", pip_pkgs)
            cmd = f"{sys.executable} -m pip install -q " + " ".join(pip_pkgs)
            try:
                await self._compute.execute(self._compute_instance_id, cmd, timeout=120)
            except Exception as e:
                logger.warning("[local_managed] sandbox pip install failed: %s", e)
            return

        # No compute provider - check if host installation is allowed
        if not self._cfg.get("host_packages_ok", False):
            from praisonai.integrations.managed_agents import ManagedSandboxRequired
            raise ManagedSandboxRequired(
                "LocalManagedAgent: packages= requires compute= for safety. "
                "Either:\n"
                "1. Add compute='docker' (recommended), or\n" 
                "2. Set LocalManagedConfig(host_packages_ok=True) to allow host pip install (unsafe)"
            )

        # Host installation (unsafe but explicitly allowed)
        cmd = [sys.executable, "-m", "pip", "install", "-q"] + pip_pkgs
        logger.warning("[local_managed] installing pip packages on HOST (unsafe): %s", pip_pkgs)
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        except subprocess.CalledProcessError as e:
            logger.warning("[local_managed] pip install failed: %s", e.stderr)
        except subprocess.TimeoutExpired:
            logger.warning("[local_managed] pip install timed out")

    async def _ensure_compute(self) -> None:
        """Provision compute instance if compute provider is attached."""
        if not self._compute or self._compute_instance_id:
            return

        logger.info("[local_managed] provisioning compute instance")
        try:
            from praisonaiagents.managed.protocols import ComputeConfig
            
            # Create compute config with our environment settings
            config = ComputeConfig(
                packages=self._cfg.get("packages", {}),
                env=self._cfg.get("env", {}),
                working_dir=self._cfg.get("working_dir", "/workspace"),
            )
            
            instance_info = await self._compute.provision(config)
            self._compute_instance_id = instance_info.instance_id
            logger.info("[local_managed] compute instance provisioned: %s", self._compute_instance_id)
            
        except Exception as e:
            logger.error("[local_managed] failed to provision compute: %s", e)
            raise

    async def _ensure_agent(self) -> Any:
        """Create or return the inner PraisonAI Agent."""
        if self._inner_agent is not None:
            return self._inner_agent

        # Provision compute instance if needed
        await self._ensure_compute()

        # Install packages (in sandbox or host as configured)
        await self._install_packages()

        from praisonaiagents import Agent

        model = self._resolve_model()
        tools = self._resolve_tools()
        system = self._cfg.get("system", self.instructions)
        name = self._cfg.get("name", "Agent")

        agent_kwargs: Dict[str, Any] = {
            "name": name,
            "instructions": system,
            "llm": model,
            "tools": tools,
        }

        # Pass API key and base if provided
        if self.api_key:
            os.environ.setdefault("OPENAI_API_KEY", self.api_key)
        if self.api_base:
            os.environ.setdefault("OPENAI_API_BASE", self.api_base)

        self._inner_agent = Agent(**agent_kwargs)
        self.agent_id = self.agent_id or f"agent_{uuid.uuid4().hex[:12]}"
        self.environment_id = self.environment_id or f"env_{uuid.uuid4().hex[:12]}"
        logger.info("[local_managed] agent created: %s model=%s", self.agent_id, model)
        return self._inner_agent

    def _ensure_session(self) -> str:
        """Create a session ID if not set."""
        if self._session_id:
            return self._session_id
        self._session_id = f"session_{uuid.uuid4().hex[:12]}"
        self._session_history.append({
            "id": self._session_id,
            "status": "idle",
            "title": self._cfg.get("session_title", "PraisonAI local session"),
            "created_at": time.time(),
        })
        self._persist_state()
        logger.info("[local_managed] session created: %s", self._session_id)
        return self._session_id

    # ------------------------------------------------------------------
    # execute() — ManagedBackendProtocol
    # ------------------------------------------------------------------
    async def execute(self, prompt: str, **kwargs) -> str:
        """Execute prompt locally and return full response."""
        from praisonaiagents.trace.context_events import get_context_emitter

        emitter = get_context_emitter()
        agent_name = self._cfg.get("name", "Agent")

        # Emit agent_start event for managed level
        emitter.agent_start(
            agent_name=agent_name,
            metadata={
                "input": prompt,
                "provider": "local",
                "model": self._cfg.get("model", self._resolve_model()),
                "compute": "sandbox" if self._compute else "host",
                "session_id": getattr(self, "_session_id", "")
            }
        )

        try:
            agent = await self._ensure_agent()
            self._ensure_session()
            self._persist_message("user", prompt)

            # Execute via inner agent (which will emit its own context events)
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, agent.chat, prompt)
            
            self._persist_message("assistant", result)
            self._sync_usage()
            
            return result
            
        except Exception as e:
            emitter.agent_end(agent_name=agent_name, metadata={"error": str(e)})
            raise
        finally:
            emitter.agent_end(agent_name=agent_name, metadata={"status": "completed"})

    def _sync_usage(self) -> None:
        """Sync token usage from inner agent to managed backend counters."""
        if self._inner_agent and hasattr(self._inner_agent, '_total_tokens_in'):
            self.total_input_tokens = self._inner_agent._total_tokens_in
            self.total_output_tokens = self._inner_agent._total_tokens_out

    def _persist_message(self, role: str, content: str) -> None:
        """Persist a message to the session store if available."""
        store = self._get_session_store()
        if store and self._session_id:
            store.add_message(self._session_id, role, content)

    def _execute_sync(self, prompt: str, stream_live: bool = False) -> str:
        """Synchronous execution using PraisonAI Agent.chat()."""
        # Note: This method is kept for backwards compatibility but 
        # cannot provision compute instances. Use execute() instead.
        if self._inner_agent is None:
            # Try sync fallback for packages without compute
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                agent = loop.run_until_complete(self._ensure_agent())
                loop.close()
            except Exception as e:
                raise RuntimeError(f"Cannot initialize agent synchronously: {e}. Use async execute() instead.")
        else:
            agent = self._inner_agent
        
        self._ensure_session()
        self._persist_message("user", prompt)

        if stream_live:
            result_parts = []
            gen = agent.chat(prompt, stream=True)
            if hasattr(gen, '__iter__'):
                for chunk in gen:
                    if chunk:
                        sys.stdout.write(str(chunk))
                        sys.stdout.flush()
                        result_parts.append(str(chunk))
                sys.stdout.write("\n")
                sys.stdout.flush()
                full = "".join(result_parts)
            else:
                full = str(gen) if gen else ""
                sys.stdout.write(full + "\n")
                sys.stdout.flush()
        else:
            result = agent.chat(prompt)
            full = str(result) if result else ""

        self._persist_message("assistant", full)
        self._sync_usage()
        self._persist_state()
        return full

    # ------------------------------------------------------------------
    # stream() — ManagedBackendProtocol
    # ------------------------------------------------------------------
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Yield text chunks as the agent produces them."""
        import queue
        import threading

        loop = asyncio.get_running_loop()
        q: queue.Queue[Optional[str]] = queue.Queue()

        def _producer():
            try:
                agent = self._ensure_agent()
                self._ensure_session()
                gen = agent.chat(prompt, stream=True)
                if hasattr(gen, '__iter__'):
                    for chunk in gen:
                        if chunk:
                            q.put(str(chunk))
                else:
                    if gen:
                        q.put(str(gen))
            except Exception as e:
                logger.error("[local_managed] stream error: %s", e)
            finally:
                q.put(None)

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
        if self._inner_agent and hasattr(self._inner_agent, 'chat_history'):
            self._inner_agent.chat_history = []

    def reset_all(self) -> None:
        """Discard all cached state."""
        self.agent_id = None
        self.agent_version = 1
        self.environment_id = None
        self._session_id = None
        self._inner_agent = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._session_history = []

    # ------------------------------------------------------------------
    # update_agent — ManagedBackendProtocol
    # ------------------------------------------------------------------
    def update_agent(self, **kwargs) -> None:
        """Update agent configuration."""
        for key, value in kwargs.items():
            if key == "system":
                self._cfg["system"] = value
                if self._inner_agent:
                    self._inner_agent.instructions = value
            elif key == "model":
                self._cfg["model"] = value
            elif key == "tools":
                self._cfg["tools"] = value
            elif key == "name":
                self._cfg["name"] = value
            else:
                self._cfg[key] = value

        if self.agent_version is not None:
            self.agent_version += 1

        # Recreate inner agent on next call (keep session for continuity)
        self._inner_agent = None
        self._persist_state()
        logger.info("[local_managed] agent updated (v%s)", self.agent_version)

    # ------------------------------------------------------------------
    # interrupt — ManagedBackendProtocol
    # ------------------------------------------------------------------
    def interrupt(self) -> None:
        """Interrupt the current execution (best-effort)."""
        logger.info("[local_managed] interrupt requested")

    # ------------------------------------------------------------------
    # retrieve_session / list_sessions — ManagedBackendProtocol
    # ------------------------------------------------------------------
    def retrieve_session(self) -> Dict[str, Any]:
        """Retrieve current session metadata.
        
        Returns unified SessionInfo schema with all fields always present.
        """
        from ._session_info import SessionInfo, SessionUsage
        
        self._sync_usage()
        
        session_info = SessionInfo(
            id=self._session_id or "",
            status="idle" if self._session_id else "none", 
            title=self._cfg.get("session_title", ""),
            usage=SessionUsage(
                input_tokens=self.total_input_tokens,
                output_tokens=self.total_output_tokens
            )
        )
        
        return session_info.to_dict()

    def list_sessions(self, **kwargs) -> List[Dict[str, Any]]:
        """List all sessions created in this backend instance."""
        limit = kwargs.get("limit")
        result = list(self._session_history)
        if limit:
            result = result[:limit]
        return result

    # ------------------------------------------------------------------
    # Session resume / ID persistence
    # ------------------------------------------------------------------
    def resume_session(self, session_id: str) -> None:
        """Resume an existing session by ID.

        Restores chat history and all persisted state (agent metadata,
        usage tokens, compute refs, session history) from the session store.
        """
        self._session_id = session_id

        # Restore all persisted state (IDs, usage, compute refs, session history)
        self._restore_state()

        store = self._get_session_store()
        if store:
            history = store.get_chat_history(session_id)
            if history:
                agent = self._ensure_agent()
                if hasattr(agent, 'chat_history'):
                    agent.chat_history = list(history)
                logger.info("[local_managed] restored %d messages from session %s", len(history), session_id)

        logger.info("[local_managed] resuming session: %s", session_id)

    def save_ids(self) -> Dict[str, Any]:
        """Return all current IDs for persistence."""
        return {
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "environment_id": self.environment_id,
            "session_id": self._session_id,
        }

    def restore_ids(self, ids: Dict[str, Any]) -> None:
        """Restore previously saved IDs."""
        self.agent_id = ids.get("agent_id")
        self.agent_version = ids.get("agent_version")
        self.environment_id = ids.get("environment_id")
        self._session_id = ids.get("session_id")
        logger.info(
            "[local_managed] IDs restored — agent: %s  env: %s  session: %s",
            self.agent_id, self.environment_id, self._session_id,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def session_id(self) -> Optional[str]:
        """The current session ID."""
        return self._session_id

    @property
    def managed_session_id(self) -> Optional[str]:
        """Backward-compatible alias for ``session_id``."""
        return self._session_id

    # ------------------------------------------------------------------
    # Compute provider integration
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_compute(compute: Optional[Any]) -> Optional[Any]:
        """Resolve a compute provider from a string name or instance.

        Accepts:
        - None → no remote compute
        - A string: ``"local"``, ``"docker"``, ``"e2b"``, ``"modal"``,
          ``"daytona"``, ``"flyio"``
        - An already-instantiated compute provider object
        """
        if compute is None:
            return None
        if isinstance(compute, str):
            name = compute.lower()
            if name == "local":
                from praisonai.integrations.compute.local import LocalCompute
                return LocalCompute()
            elif name == "docker":
                from praisonai.integrations.compute.docker import DockerCompute
                return DockerCompute()
            elif name == "e2b":
                from praisonai.integrations.compute.e2b import E2BCompute
                return E2BCompute()
            elif name == "modal":
                from praisonai.integrations.compute.modal_compute import ModalCompute
                return ModalCompute()
            elif name == "daytona":
                from praisonai.integrations.compute.daytona import DaytonaCompute
                return DaytonaCompute()
            elif name == "flyio":
                from praisonai.integrations.compute.flyio import FlyioCompute
                return FlyioCompute()
            else:
                raise ValueError(f"Unknown compute provider: {name}")
        return compute  # Already an instance

    @property
    def compute_provider(self) -> Optional[Any]:
        """The attached compute provider (if any)."""
        return self._compute

    async def provision_compute(self, **kwargs) -> Any:
        """Provision compute infrastructure for remote tool execution.

        Returns the ``InstanceInfo`` from the compute provider.
        """
        if self._compute is None:
            raise RuntimeError("No compute provider attached.")

        from praisonaiagents.managed.protocols import ComputeConfig

        config = ComputeConfig(
            image=kwargs.get("image", "python:3.12-slim"),
            cpu=kwargs.get("cpu", 1),
            memory_mb=kwargs.get("memory_mb", 512),
            env=kwargs.get("env", self._cfg.get("env", {})),
            packages=kwargs.get("packages", self._cfg.get("packages")),
            working_dir=kwargs.get("working_dir", self._cfg.get("working_dir", "/workspace")),
            auto_shutdown=kwargs.get("auto_shutdown", True),
            idle_timeout_s=kwargs.get("idle_timeout_s", 300),
        )

        info = await self._compute.provision(config)
        self._compute_instance_id = info.instance_id
        logger.info(
            "[local_managed] compute provisioned: %s via %s",
            info.instance_id, self._compute.provider_name,
        )
        return info

    async def execute_in_compute(
        self, command: str, timeout: int = 300,
    ) -> Dict[str, Any]:
        """Execute a command in the remote compute environment."""
        if self._compute is None or self._compute_instance_id is None:
            raise RuntimeError(
                "No compute provisioned. Call provision_compute() first."
            )
        return await self._compute.execute(
            self._compute_instance_id, command, timeout=timeout,
        )

    async def shutdown_compute(self) -> None:
        """Shutdown the remote compute environment."""
        if self._compute and self._compute_instance_id:
            await self._compute.shutdown(self._compute_instance_id)
            logger.info(
                "[local_managed] compute shutdown: %s",
                self._compute_instance_id,
            )
            self._compute_instance_id = None

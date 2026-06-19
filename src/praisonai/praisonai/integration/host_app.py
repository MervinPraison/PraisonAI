"""Official PraisonAI → PraisonAIUI host bootstrap (Pattern B).

Wires ``PraisonAISessionDataStore`` + ``PraisonAIProvider`` before ``create_app()``.
Set ``PRAISONAI_HOST_LEGACY=1`` to skip provider wiring (callback-only mode).
"""

from __future__ import annotations

import os
import contextvars
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

# Use context variable instead of module-level global for multi-agent safety
_configured_context: contextvars.ContextVar[bool] = contextvars.ContextVar('host_configured', default=False)

# For testing: also maintain a module-level flag that can be accessed across contexts
_configured_global = False

# Backward compatibility for tests
def reset_configuration() -> None:
    """Reset configuration state for testing. Use instead of host_app._CONFIGURED = False."""
    global _configured_global
    _configured_context.set(False)
    _configured_global = False
    
    # Also clear any cached state that might be lingering
    try:
        import praisonaiui.server as srv
        if hasattr(srv, '_provider'):
            srv._provider = None
        if hasattr(srv, '_datastore'):
            srv._datastore = None
        # Clear any other potentially cached state
        if hasattr(srv, '_app'):
            srv._app = None
        # Clear backends registry if it exists
        try:
            import praisonaiui.backends as backends
            if hasattr(backends, 'clear_backends'):
                backends.clear_backends()
            elif hasattr(backends, '_backends'):
                backends._backends.clear()
        except (ImportError, AttributeError):
            pass
    except ImportError:
        pass

def is_configured() -> bool:
    """Check if configuration has been applied in current context."""
    return _configured_context.get() or _configured_global

# Backward compatibility shim for tests that assign host_app._CONFIGURED = False
class _ConfiguredShim:
    """Backward compatibility shim that proxies to both ContextVar and global."""
    def __get__(self, obj, objtype=None):
        return _configured_context.get() or _configured_global
    
    def __set__(self, obj, value):
        global _configured_global
        _configured_context.set(bool(value))
        _configured_global = bool(value)
        
    def __bool__(self):
        return _configured_context.get() or _configured_global

# Expose the shim so tests can still use host_app._CONFIGURED = False 
_CONFIGURED = _ConfiguredShim()


def is_legacy_host() -> bool:
    """True when callback-only ``@aiui.reply`` mode is requested."""
    return os.environ.get("PRAISONAI_HOST_LEGACY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def configure_host(
    *,
    pages: Optional[Sequence[str]] = None,
    title: str = "PraisonAI",
    logo: str = "🤖",
    sidebar: bool = True,
    page_header: bool = True,
    theme: Optional[Dict[str, Any]] = None,
    agents: Optional[List[Any]] = None,
    agent_kwargs: Optional[Dict[str, Any]] = None,
    gateway: Any = None,
    modules: Optional[Sequence[str]] = None,
    style: str = "dashboard",
    context_paths: Optional[Sequence[str]] = None,
    **kwargs: Any,
) -> None:
    """Apply PraisonAIUI host settings and wire L1 backends (unless legacy mode)."""
    global _configured_global
    
    # Check if already configured in this context to avoid duplicate configuration
    if _configured_context.get() or _configured_global:
        return

    import praisonaiui as aiui
    from praisonai.ui._aiui_datastore import PraisonAISessionDataStore

    aiui.set_datastore(PraisonAISessionDataStore())
    aiui.set_style(style)
    aiui.set_branding(title=title, logo=logo)

    if pages is not None:
        aiui.set_pages(list(pages))

    dashboard_opts: Dict[str, Any] = {"sidebar": sidebar, "page_header": page_header}
    if modules:
        dashboard_opts["modules"] = list(modules)
    aiui.set_dashboard(**dashboard_opts)

    if theme:
        aiui.set_theme(**theme)

    try:
        from praisonai.ui._external_agents import aiui_settings_entries

        external = aiui_settings_entries()
        if external and hasattr(aiui, "set_settings"):
            aiui.set_settings(external)
    except ImportError:
        pass

    if gateway is not None:
        try:
            from praisonaiui.features._gateway_ref import set_gateway

            set_gateway(gateway)
        except ImportError:
            pass

    if not is_legacy_host():
        from praisonaiui.providers import PraisonAIProvider
        from praisonaiui.server import set_provider
        import praisonaiui.server as srv
        
        # Check if a provider is already set (e.g., by tests)
        # Only set a new provider if none exists
        if not hasattr(srv, '_provider') or srv._provider is None:
            kwargs = dict(agent_kwargs or {})
            if agents:
                set_provider(PraisonAIProvider(agents=list(agents), **kwargs))
            else:
                # Load context files if specified
                instructions = kwargs.pop("instructions", "You are a helpful assistant.")
                if context_paths:
                    try:
                        from praisonai.integration.context_files import load_context_files
                        context = load_context_files(list(context_paths))
                        if context:
                            instructions = f"{instructions}\n\nContext:\n{context}"
                    except ImportError:
                        pass  # Context files helper is optional
                
                set_provider(
                    PraisonAIProvider(
                        name=kwargs.pop("name", "PraisonAI"),
                        instructions=instructions,
                        llm=kwargs.pop(
                            "llm", os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")
                        ),
                        **kwargs,
                    )
                )
        setup_bridges()

    # Register L3 dashboard pages
    try:
        from praisonai.integration.pages import workflow_runs, bot_health
    except ImportError:
        pass  # L3 pages are optional

    _configured_context.set(True)
    _configured_global = True


def setup_bridges() -> None:
    """Register optional L1→L2 bridge hooks (usage sink, schedules, aiui backends)."""
    import logging

    log = logging.getLogger(__name__)
    sink = None

    try:
        from praisonai.integration.bridges.usage_bridge import register_usage_sink

        sink = register_usage_sink()
    except ImportError as exc:
        log.debug("usage bridge unavailable: %s", exc)
    except Exception as exc:
        log.warning("usage bridge unavailable: %s", exc)

    try:
        from praisonai.integration.bridges.schedules_runner import ensure_schedule_runner

        ensure_schedule_runner()
    except ImportError as exc:
        log.debug("schedule runner unavailable: %s", exc)
    except Exception as exc:
        log.warning("schedule runner unavailable: %s", exc)

    try:
        import praisonaiui.backends as backends
        from praisonai.integration.bridges.hooks_query import list_hooks_for_api
        from praisonai.integration.bridges.workflows_service import run_workflow as svc_run

        def _workflow_backend(wf_id, *, workflow, input_data):
            text = (input_data or {}).get("text") or (input_data or {}).get("message") or ""
            return svc_run(wf_id, input_text=text, workflow_config=workflow)

        backends.set_backend("hooks", list_hooks_for_api)
        backends.set_backend("workflows", _workflow_backend)
        if sink is not None:
            backends.set_backend("usage_sink", sink)
        from praisonai.integration.bridges.usage_bridge import get_usage_query

        query = get_usage_query()
        if query is not None:
            backends.set_backend("usage_query", query)
        from praisonai.integration.bridges.approvals_bridge import (
            get_approval_policies,
            list_pending_approvals,
        )

        backends.set_backend("approvals_pending", list_pending_approvals)
        backends.set_backend("approvals_policies", get_approval_policies)
        
        # Kanban and jobs backends
        from praisonai.integration.bridges.kanban_bridge import register_kanban_backends
        register_kanban_backends()
        
    except Exception as exc:
        log.warning("aiui backend injection failed: %s", exc)


def create_host_app():
    """Return the Starlette app from PraisonAIUI (call after ``configure_host``)."""
    from praisonaiui.server import create_app

    if not (_configured_context.get() or _configured_global):
        configure_host()
    return create_app()


def build_host_app(**configure_kwargs):
    """One-shot: configure host + return ``create_app()``."""
    configure_host(**configure_kwargs)
    return create_host_app()


@dataclass
class UIPreset:
    """UI configuration preset for standardizing UI app creation."""
    title: str = "PraisonAI"
    logo: str = "🤖"
    pages: List[str] = field(default_factory=lambda: ["chat"])
    theme: Dict[str, Any] = field(default_factory=lambda: {"preset": "blue", "dark_mode": True, "radius": "lg"})
    agent_kwargs: Dict[str, Any] = field(default_factory=dict)
    starters: List[Dict[str, str]] = field(default_factory=list)
    welcome: str = "👋 Hi! I'm your PraisonAI assistant."
    sidebar: bool = True
    page_header: bool = True
    openai_fallback: bool = False
    settings_handler: Optional[Callable] = None
    agent_factory: Optional[Callable] = None
    realtime_manager: Optional[Any] = None  # For OpenAIRealtimeManager
    agent_loader: Optional[Callable] = None  # For loading agents from YAML


def build_ui_app(preset: UIPreset):
    """Build a UI app from a preset configuration."""
    import praisonaiui as aiui
    
    # Configure the host with preset values
    configure_host(
        title=preset.title,
        logo=preset.logo,
        pages=preset.pages,
        sidebar=preset.sidebar,
        page_header=preset.page_header,
        theme=preset.theme,
        agent_kwargs=preset.agent_kwargs,
    )
    
    # Set up starters if provided
    if preset.starters:
        @aiui.starters
        async def _starters():
            return preset.starters
    
    # Set up welcome message
    @aiui.welcome
    async def _welcome():
        await aiui.say(preset.welcome)
    
    # Set up realtime manager if provided
    if preset.realtime_manager:
        aiui.set_realtime_manager(preset.realtime_manager)
    
    # Load agents from YAML if loader provided
    if preset.agent_loader:
        preset.agent_loader()
    
    # Set up legacy host handlers if needed
    if is_legacy_host():
        _agents_cache = {}
        
        # Settings handler if provided
        if preset.settings_handler:
            @aiui.settings
            async def _settings(new_settings):
                session_id = getattr(aiui.current_session, "id", "default")
                _agents_cache.pop(session_id, None)
                if preset.settings_handler:
                    await preset.settings_handler(new_settings)
        
        # Reply handler with caching
        @aiui.reply
        async def _reply(message: str, settings: dict | None = None):
            session_id = getattr(aiui.current_session, "id", "default")
            settings_key = str(sorted((settings or {}).items()))
            cache_key = f"{session_id}:{settings_key}"
            
            # Get or create agent
            if cache_key not in _agents_cache:
                if preset.agent_factory:
                    _agents_cache[cache_key] = preset.agent_factory(settings)
                else:
                    # Default agent creation
                    from praisonaiagents import Agent
                    _agents_cache[cache_key] = Agent(**preset.agent_kwargs)
            
            agent = _agents_cache[cache_key]
            
            # Process with agent
            if agent is not None:
                try:
                    await aiui.think("Thinking...")
                    result = await agent.achat(str(message))
                    response_text = str(result) if result else ""
                    
                    # Stream response
                    words = response_text.split(" ")
                    for i, word in enumerate(words):
                        await aiui.stream_token(word + (" " if i < len(words) - 1 else ""))
                    return
                except Exception as e:
                    if not preset.openai_fallback:
                        await aiui.say(f"❌ Error: {e}")
                        return
                    await aiui.say(f"⚠️ Agent error: {e}. Falling back to OpenAI...")
            
            # OpenAI fallback if enabled
            if preset.openai_fallback:
                try:
                    from openai import AsyncOpenAI
                    api_key = os.getenv("OPENAI_API_KEY")
                    if not api_key:
                        await aiui.say("❌ Please set OPENAI_API_KEY environment variable.")
                        return
                    
                    client = AsyncOpenAI(api_key=api_key)
                    stream = await client.chat.completions.create(
                        model=os.getenv("PRAISONAI_MODEL", "gpt-4o-mini"),
                        messages=[
                            {"role": "system", "content": preset.agent_kwargs.get("instructions", "You are a helpful assistant.")},
                            {"role": "user", "content": str(message)},
                        ],
                        stream=True,
                    )
                    
                    async for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            await aiui.stream_token(delta.content)
                except ImportError:
                    await aiui.say("❌ Please install openai: `pip install openai`")
                except Exception as e:
                    await aiui.say(f"❌ OpenAI error: {e}")
        
        # Cancel handler
        @aiui.cancel
        async def _cancel():
            await aiui.say("⏹️ Stopped.")
    
    return create_host_app()

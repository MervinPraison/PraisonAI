"""Official PraisonAI → PraisonAIUI host bootstrap (Pattern B).

Wires ``PraisonAISessionDataStore`` + ``PraisonAIProvider`` before ``create_app()``.
Set ``PRAISONAI_HOST_LEGACY=1`` to skip provider wiring (callback-only mode).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

_CONFIGURED = False


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
) -> None:
    """Apply PraisonAIUI host settings and wire L1 backends (unless legacy mode)."""
    global _CONFIGURED

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

    _CONFIGURED = True


def setup_bridges() -> None:
    """Register optional L1→L2 bridge hooks (usage sink, schedules, aiui backends)."""
    import logging

    log = logging.getLogger(__name__)
    sink = None

    try:
        from praisonai.integration.bridges.usage_bridge import register_usage_sink

        sink = register_usage_sink()
    except Exception as exc:
        log.warning("usage bridge unavailable: %s", exc)

    try:
        from praisonai.integration.bridges.schedules_runner import ensure_schedule_runner

        ensure_schedule_runner()
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
    except Exception as exc:
        log.warning("aiui backend injection failed: %s", exc)


def create_host_app():
    """Return the Starlette app from PraisonAIUI (call after ``configure_host``)."""
    from praisonaiui.server import create_app

    if not _CONFIGURED:
        configure_host()
    return create_app()


def build_host_app(**configure_kwargs):
    """One-shot: configure host + return ``create_app()``."""
    configure_host(**configure_kwargs)
    return create_host_app()

"""Top-level convenience entry points for the Python API.

Keep this file minimal - it is part of the Minimal API surface and must defer
all heavy imports to call time.
"""
from __future__ import annotations

from typing import Any


def _build_config_list() -> list[dict[str, Any]]:
    """Reuse the same env/keyfile resolution the CLI already performs."""
    from praisonai.llm.config import build_config_list
    return build_config_list()


def _resolve_run_inputs(framework: str | None) -> tuple[str, list[dict[str, Any]]]:
    """Single source of truth for wrapper entry-point resolution.

    Resolves the framework (default selection or explicit validation) and builds
    the LLM config list. This performs synchronous work — including credential /
    config file I/O via ``_build_config_list`` — so async callers must invoke it
    off the event loop (see ``arun``).
    """
    from .framework_adapters.registry import get_default_registry

    if framework is None:
        # Single source of truth for default selection: the registry, which
        # honours entry-point plugins as well as the built-in priority order.
        framework = get_default_registry().pick_default()
    else:
        # Validate explicit framework like CLI does
        from .framework_adapters.validators import assert_framework_available
        assert_framework_available(framework)

    return framework, _build_config_list()


def run(agent_file: str,
        framework: str | None = None,
        *,
        tools: list | None = None,
        agent_yaml: str | None = None,
        cli_config: dict | None = None) -> str:
    """One-line Python entry point. Equivalent to `praisonai <agent_file>`."""
    from .agents_generator import AgentsGenerator

    framework, config_list = _resolve_run_inputs(framework)

    gen = AgentsGenerator(
        agent_file=agent_file,
        framework=framework,
        config_list=config_list,
        tools=tools,
        agent_yaml=agent_yaml,
        cli_config=cli_config,
    )
    return gen.generate_crew_and_kickoff()


async def arun(agent_file: str,
               framework: str | None = None,
               *,
               tools: list | None = None,
               agent_yaml: str | None = None,
               cli_config: dict | None = None) -> str:
    """Async equivalent of `run()` using native async framework adapters."""
    import asyncio

    from .agents_generator import AgentsGenerator

    # Resolve framework + build config_list off the caller's event loop so the
    # synchronous credential/config-file I/O does not block it. This is the
    # reason arun exists: a FastAPI handler awaiting arun must not stall the loop.
    framework, config_list = await asyncio.to_thread(_resolve_run_inputs, framework)

    gen = AgentsGenerator(
        agent_file=agent_file,
        framework=framework,
        config_list=config_list,
        tools=tools,
        agent_yaml=agent_yaml,
        cli_config=cli_config,
    )
    return await gen.agenerate_crew_and_kickoff()
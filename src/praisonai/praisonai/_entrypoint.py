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


def run(agent_file: str,
        framework: str | None = None,
        *,
        tools: list | None = None,
        agent_yaml: str | None = None,
        cli_config: dict | None = None) -> str:
    """One-line Python entry point. Equivalent to `praisonai <agent_file>`."""
    from .agents_generator import AgentsGenerator
    from .framework_adapters.registry import get_default_registry

    if framework is None:
        # Single source of truth for default selection: the registry, which
        # honours entry-point plugins as well as the built-in priority order.
        framework = get_default_registry().pick_default()
    else:
        # Validate explicit framework like CLI does
        from .framework_adapters.validators import assert_framework_available
        assert_framework_available(framework)

    gen = AgentsGenerator(
        agent_file=agent_file,
        framework=framework,
        config_list=_build_config_list(),
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
    from .agents_generator import AgentsGenerator
    from .framework_adapters.registry import get_default_registry

    if framework is None:
        # Single source of truth for default selection: the registry, which
        # honours entry-point plugins as well as the built-in priority order.
        framework = get_default_registry().pick_default()
    else:
        # Validate explicit framework like CLI does
        from .framework_adapters.validators import assert_framework_available
        assert_framework_available(framework)

    gen = AgentsGenerator(
        agent_file=agent_file,
        framework=framework,
        config_list=_build_config_list(),
        tools=tools,
        agent_yaml=agent_yaml,
        cli_config=cli_config,
    )
    return await gen.agenerate_crew_and_kickoff()
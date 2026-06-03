"""Top-level convenience entry points for the Python API.

Keep this file minimal - it is part of the Minimal API surface and must defer
all heavy imports to call time.
"""
from __future__ import annotations

from typing import Any


def _build_config_list() -> list[dict[str, Any]]:
    """Reuse the same env/keyfile resolution the CLI already performs."""
    # Import LLM endpoint resolution from the same path the CLI uses
    from praisonai.llm.env import resolve_llm_endpoint
    ep = resolve_llm_endpoint()
    
    return [{
        'model': ep.model,
        'base_url': ep.base_url,
        'api_key': ep.api_key,
        'api_type': 'openai'        # AutoGen expects this field
    }]


def run(agent_file: str,
        framework: str | None = None,
        *,
        tools: list | None = None,
        agent_yaml: str | None = None,
        cli_config: dict | None = None) -> str:
    """One-line Python entry point. Equivalent to `praisonai <agent_file>`."""
    from .agents_generator import AgentsGenerator
    from ._framework_availability import is_available

    if framework is None:
        # Mirror the CLI default-resolution order
        for candidate in ("crewai", "praisonaiagents", "autogen", "ag2"):
            if is_available(candidate):
                framework = "praisonai" if candidate == "praisonaiagents" else candidate
                break
        else:
            raise RuntimeError(
                "No supported framework installed. "
                "Install one of: crewai, praisonaiagents, autogen, ag2."
            )
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
    """Async equivalent of `run()` for FastAPI / Jupyter async callers."""
    import asyncio
    return await asyncio.to_thread(
        run, agent_file, framework,
        tools=tools, agent_yaml=agent_yaml, cli_config=cli_config,
    )
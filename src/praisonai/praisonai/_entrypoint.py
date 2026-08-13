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


def _resolve_run_inputs(framework: str | None) -> tuple[Any, list[dict[str, Any]]]:
    """Single source of truth for wrapper entry-point resolution.

    Resolves the framework (default selection or explicit validation), builds
    the resolved adapter once, and builds the LLM config list. Returning the
    adapter lets ``AgentsGenerator`` reuse it instead of constructing (and
    re-validating) the winning adapter a second time on the hot path.

    This performs synchronous work — including credential / config file I/O via
    ``_build_config_list`` — so async callers must invoke it off the event loop
    (see ``arun``).
    """
    from .framework_adapters.registry import get_default_registry

    registry = get_default_registry()
    if framework is None:
        # Single source of truth for default selection: the registry, which
        # honours entry-point plugins as well as the built-in priority order.
        framework = registry.pick_default()
    else:
        # Validate explicit framework like CLI does
        from .framework_adapters.validators import assert_framework_available
        assert_framework_available(framework, registry=registry)

    adapter = registry.create(framework)
    return adapter, _build_config_list()


# Loose kwargs whose CLI dest differs from the intuitive Python name. Mapping
# them keeps the documented option effective instead of silently dropping it
# into ``cli_config`` under a key no downstream consumer reads.
_CLI_KWARG_ALIASES = {"session": "resume_session"}


def _apply_model_override(config_list: list[dict[str, Any]], extra: dict) -> None:
    """Honour a loose ``model=``/``llm=`` kwarg by writing it onto the resolved
    ``config_list`` the generator reads model selection from.

    Mirrors the CLI's ``--llm`` behaviour (see ``direct_prompt`` /
    ``agents_generator``: model is taken from ``config_list[0]['model']``), so a
    Python caller's ``model=`` is actually applied instead of being ignored.
    Mutates ``extra`` in place, popping the consumed key so it is not also
    forwarded through ``cli_config``.
    """
    model = extra.pop("model", None)
    if model is None:
        model = extra.pop("llm", None)
    if model and config_list:
        config_list[0]["model"] = model


def _merge_cli_config(cli_config: dict | None, extra: dict) -> dict | None:
    """Merge loose ``run()``/``arun()`` kwargs into the ``cli_config`` escape
    hatch the CLI already forwards to ``AgentsGenerator``.

    This gives Python callers the same pass-through the CLI uses for advanced
    options without inventing a parallel option surface. Loose names whose CLI
    dest differs (e.g. ``session`` -> ``resume_session``) are normalised so they
    reach the consumer that reads them. Explicit ``cli_config`` keys win over
    loose kwargs.
    """
    if not extra:
        return cli_config
    merged = dict(cli_config or {})
    for key, value in extra.items():
        merged.setdefault(_CLI_KWARG_ALIASES.get(key, key), value)
    return merged


def run(agent_file: str,
        framework: str | None = None,
        *,
        tools: list | None = None,
        agent_yaml: str | None = None,
        cli_config: dict | None = None,
        **kwargs: Any) -> str:
    """One-line Python entry point. Equivalent to `praisonai <agent_file>`.

    Advanced ``praisonai run`` options can be passed as loose keyword arguments.
    ``model=`` (alias ``llm=``) selects the LLM like the CLI's ``--llm``;
    ``session=`` resumes a session like ``--resume``; any other option is
    forwarded through ``cli_config`` to the generator, mirroring the CLI's
    pass-through.
    """
    from .agents_generator import AgentsGenerator

    adapter, config_list = _resolve_run_inputs(framework)
    _apply_model_override(config_list, kwargs)
    cli_config = _merge_cli_config(cli_config, kwargs)

    # Own the generator's lifecycle so its lazily-allocated tool-timeout
    # executor is released once the single run completes, instead of leaking
    # daemon threads per call in long-lived server workers.
    with AgentsGenerator(
        agent_file=agent_file,
        framework=adapter.name,
        config_list=config_list,
        tools=tools,
        agent_yaml=agent_yaml,
        cli_config=cli_config,
        adapter=adapter,
    ) as gen:
        return gen.generate_crew_and_kickoff()


async def arun(agent_file: str,
               framework: str | None = None,
               *,
               tools: list | None = None,
               agent_yaml: str | None = None,
               cli_config: dict | None = None,
               **kwargs: Any) -> str:
    """Async equivalent of `run()` using native async framework adapters.

    Accepts the same loose keyword arguments as :func:`run`.
    """
    import asyncio

    from .agents_generator import AgentsGenerator

    # Resolve framework + build config_list off the caller's event loop so the
    # synchronous credential/config-file I/O does not block it. This is the
    # reason arun exists: a FastAPI handler awaiting arun must not stall the loop.
    adapter, config_list = await asyncio.to_thread(_resolve_run_inputs, framework)
    _apply_model_override(config_list, kwargs)
    cli_config = _merge_cli_config(cli_config, kwargs)

    # Own the generator's lifecycle so its lazily-allocated tool-timeout
    # executor is released once the single run completes, instead of leaking
    # daemon threads per call in long-lived async server workers.
    with AgentsGenerator(
        agent_file=agent_file,
        framework=adapter.name,
        config_list=config_list,
        tools=tools,
        agent_yaml=agent_yaml,
        cli_config=cli_config,
        adapter=adapter,
    ) as gen:
        return await gen.agenerate_crew_and_kickoff()
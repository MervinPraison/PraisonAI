"""Export an Agent or AgentTeam back to a config dict.

Config flowed one way. ``workflows/yaml_parser.py`` builds agents FROM YAML, and
nothing exported them back -- so you could not build a team in Python and hand
it to the visual builder, diff two team configs, or check into review what a
programmatically-assembled team actually became. This is the missing half of a
pipeline that already exists.

    blob = agent_to_dict(agent)         # JSON-safe
    same = agent_from_dict(blob)        # an equivalent Agent

What is deliberately NOT exported: anything that is a live object rather than
configuration -- an open session, a memory store, a resolved LLM client. A tool
is exported by NAME, because a callable cannot survive a round trip through
JSON and pretending otherwise would produce a config that imports as a
different agent. ``tools_resolvable`` says whether the names could be rebound,
so a caller is told rather than left to discover it.
"""

from typing import Any, Callable, Dict, List, Optional

__all__ = [
    "AGENT_CONFIG_VERSION",
    "SerializationError",
    "agent_to_dict",
    "agent_from_dict",
    "team_to_dict",
]

AGENT_CONFIG_VERSION = 1

#: Candidate fields worth carrying. Deliberately a list rather than "everything
#: on the object": an Agent holds runtime state (clients, caches, sessions) that
#: is meaningless -- and sometimes unserialisable -- in a config.
#:
#: Intersected with the CONSTRUCTOR SIGNATURE at export time, so an attribute
#: that still exists on the instance but is no longer a constructor argument
#: (several moved into `output=`) is not exported into a config that cannot be
#: imported. Hardcoding the list alone produced exactly that.
_AGENT_FIELDS = (
    "name", "role", "goal", "backstory", "instructions", "llm",
    "self_reflect", "max_reflect", "min_reflect", "respect_context_window",
    "max_iter", "reasoning_steps", "markdown", "stream", "verbose",
)


def _constructor_fields(agent_cls: type) -> set:
    """The subset of _AGENT_FIELDS this build's constructor still accepts."""
    import inspect
    try:
        params = inspect.signature(agent_cls.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - exotic callables
        return set(_AGENT_FIELDS)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        # **kwargs alone is not proof it is accepted: this class validates and
        # raises on unknown keys, so trust the named parameters only.
        pass
    return {f for f in _AGENT_FIELDS if f in params}


class SerializationError(ValueError):
    """Raised when a config cannot be exported or rebuilt."""


def _tool_name(tool: Any) -> Optional[str]:
    for attr in ("name", "__name__"):
        value = getattr(tool, attr, None)
        if isinstance(value, str) and value:
            return value
    if isinstance(tool, str):
        return tool
    return None


def agent_to_dict(agent: Any) -> Dict[str, Any]:
    """An Agent as a JSON-safe config dict."""
    if agent is None:
        raise SerializationError("Cannot export None as an agent config.")

    allowed = _constructor_fields(type(agent))
    config: Dict[str, Any] = {"version": AGENT_CONFIG_VERSION}
    for field in sorted(allowed):
        if not hasattr(agent, field):
            continue
        value = getattr(agent, field)
        if value is None:
            continue
        # An LLM object rather than a model string: keep its identity, not the
        # client. A resolved client cannot be rebuilt from JSON anyway.
        if field == "llm" and not isinstance(value, str):
            value = getattr(value, "model", None) or getattr(value, "name", None) or str(value)
        config[field] = value

    tools = getattr(agent, "tools", None) or []
    names = [_tool_name(t) for t in tools]
    config["tools"] = [n for n in names if n]
    # Say plainly whether the tools survived as names. A config whose tools
    # cannot be rebound imports as an agent that silently cannot act.
    config["tools_resolvable"] = all(n is not None for n in names)
    return config


def agent_from_dict(
    config: Dict[str, Any],
    *,
    tool_registry: Optional[Dict[str, Callable]] = None,
    agent_cls: Optional[type] = None,
) -> Any:
    """Rebuild an Agent from ``agent_to_dict`` output.

    ``tool_registry`` maps exported tool names back to callables. Without it an
    agent is rebuilt WITHOUT tools, and that is reported rather than assumed --
    an agent that silently lost its tools looks like an agent that chose not to
    use them.
    """
    if not isinstance(config, dict):
        raise SerializationError(f"Agent config must be a dict; got {type(config).__name__}")

    version = config.get("version", AGENT_CONFIG_VERSION)
    if version != AGENT_CONFIG_VERSION:
        raise SerializationError(
            f"Agent config is version {version!r}, this build reads {AGENT_CONFIG_VERSION}."
        )

    if agent_cls is None:
        from .agent import Agent as agent_cls  # type: ignore

    kwargs = {k: v for k, v in config.items() if k in _constructor_fields(agent_cls)}

    wanted: List[str] = list(config.get("tools") or [])
    if wanted:
        if tool_registry is None:
            raise SerializationError(
                f"This config declares tools {wanted} but no tool_registry was given, "
                f"so they cannot be rebound. Pass tool_registry={{name: callable}}, or "
                f"strip 'tools' from the config if a tool-less agent is intended."
            )
        missing = [n for n in wanted if n not in tool_registry]
        if missing:
            raise SerializationError(
                f"tool_registry is missing {missing}. Rebuilding without them would "
                f"produce an agent that silently cannot act."
            )
        kwargs["tools"] = [tool_registry[n] for n in wanted]

    return agent_cls(**kwargs)


def team_to_dict(team: Any) -> Dict[str, Any]:
    """An AgentTeam as a config dict, members included."""
    if team is None:
        raise SerializationError("Cannot export None as a team config.")
    return {
        "version": AGENT_CONFIG_VERSION,
        "name": getattr(team, "name", None),
        "process": getattr(team, "process", None),
        "agents": [agent_to_dict(a) for a in (getattr(team, "agents", None) or [])],
    }

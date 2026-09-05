"""One vocabulary for "where does this run?", shared by Agent, AgentFlow and AgentTeam.

Two questions get asked about placement and they have different answers:

``run_on=``
    Where the **whole agent** runs -- the model calls, the loop, the tools, all
    of it on someone else's machine. Only a *managed runtime* can answer this,
    because running the loop remotely means something has to host the loop.

``tools_run_on=``
    Where **the tools** run. Thinking stays on this machine; only the shell,
    the file writes and the code execution move. Any sandbox or compute place
    can answer this, because all it has to do is run a command.

Keeping the two words apart is the entire point. The old surface used one word
(``run_on=``) on ``AgentFlow``/``AgentTeam`` for the tools-only meaning, another
(``compute=``) on ``LocalAgent`` for exactly the same meaning, and a third
(``backend=``) for the whole-agent meaning -- so the same concept had two names
and one name had two concepts.

Because the two questions have disjoint answer sets, a wrong pairing is a typo
worth catching rather than a preference worth honouring. ``run_on="docker"``
cannot mean anything: Docker does not host agent loops. It gets a ``TypeError``
naming the parameter the user actually wanted, not a silent fallback.
"""

from __future__ import annotations

from typing import Any, Literal, NamedTuple, Optional, Union

# Runtimes that can host an entire agent loop. Resolved from the wrapper's
# entry-point registry when it is installed so third-party backends work with
# `run_on=` too; the literal is the floor, not the ceiling.
_FALLBACK_MANAGED = ("anthropic",)

# Static spellings so editors can autocomplete and type-checkers can reject a
# typo at the call site rather than at the first model turn. The runtime
# functions below stay the authority for validation -- these exist for tooling,
# which cannot call a function to learn a set.
# Keep in sync with _compute_bridge._PROVIDERS | _sandbox_adapter.SANDBOX_ONLY.
ManagedRuntime = Literal["anthropic"]

ToolPlace = Literal[
    "local", "subprocess", "sandlock", "docker", "e2b",
    "modal", "daytona", "flyio", "tenki", "novita", "ssh",
]


def managed_runtimes() -> tuple:
    """Names that ``run_on=`` accepts -- places that host a whole agent."""
    try:
        from praisonai.integrations.backend_registry import get_backend_registry

        names = tuple(get_backend_registry().list_all_names())
        if names:
            return tuple(sorted(set(names) | set(_FALLBACK_MANAGED)))
    except Exception:
        pass
    return _FALLBACK_MANAGED


def tool_places() -> list:
    """Names that ``tools_run_on=`` accepts -- places that can run a command.

    Includes the resolver's aliases. Validation runs before resolution, so
    leaving them out rejected spellings the resolver handles happily:
    ``tools_run_on="native"`` raised "not a known place" while
    ``resolve_compute("native")`` returned a working sandlock adapter.
    """
    try:
        from ..managed._compute_bridge import _ALIASES, available_providers

        return sorted(set(available_providers()) | set(_ALIASES))
    except Exception:
        return ["local", "docker"]


class Placement(NamedTuple):
    """The resolved answer to "where does this run?"."""

    whole: Optional[Any] = None   # managed runtime name/object, or None
    tools: Optional[Any] = None   # tools place name/object, or None


def _name_of(value: Any) -> Optional[str]:
    """The comparable name of a placement value, or None if it is an object.

    Objects (a built provider, a live ``SSHSandbox``) carry their own config and
    are never second-guessed -- only bare strings get routed by name.
    """
    return value.lower() if isinstance(value, str) else None


def _quote_list(names) -> str:
    return ", ".join(repr(n) for n in names)


def resolve_placement(
    owner: str,
    *,
    run_on: Any = None,
    tools_run_on: Any = None,
    backend: Any = None,
    supports_run_on: bool = True,
) -> Placement:
    """Validate placement arguments and return where things should run.

    ``owner`` is the class name, used only to make errors read naturally.
    ``supports_run_on`` is False for AgentFlow/AgentTeam, which can place tools
    but cannot (yet) hand a whole multi-agent run to a managed runtime.

    Raises:
        TypeError: on any combination that names two different places for the
            same thing, or a place that cannot do the job asked of it.
    """
    # ── a place that cannot do the job asked of it ───────────────────────────
    run_on_name = _name_of(run_on)
    tools_name = _name_of(tools_run_on)

    # The two lookups below feed only the branches guarded on run_on_name /
    # tools_name being set; the entry-point scan in tool_places() is the
    # dominant cost of Agent() construction, so skip both on the default
    # (no-placement) path rather than compute results that get discarded.
    if run_on_name is not None or tools_name is not None:
        managed = managed_runtimes()
        places = tool_places()
    else:
        managed = places = ()

    if run_on_name is not None and run_on_name not in managed:
        if run_on_name in places:
            raise TypeError(
                f"{owner}(run_on={run_on!r}) is not valid: run_on= places the "
                f"whole agent -- model calls, loop and tools -- on a managed "
                f"runtime, and {run_on_name!r} runs commands but cannot host an "
                f"agent loop.\n"
                f"  To run only the tools there:  {owner}(tools_run_on={run_on!r})\n"
                f"  Runtimes that host a whole agent: {_quote_list(managed)}"
            )
        raise TypeError(
            f"{owner}(run_on={run_on!r}) is not a known managed runtime.\n"
            f"  Runtimes that host a whole agent: {_quote_list(managed)}\n"
            f"  Places that can run tools:        {_quote_list(places)} "
            f"(pass those as tools_run_on=)"
        )

    if tools_name is not None and tools_name in managed and tools_name not in places:
        raise TypeError(
            f"{owner}(tools_run_on={tools_run_on!r}) is not valid: {tools_name!r} "
            f"hosts an entire agent, not individual tools.\n"
            f"  Did you mean:  {owner}(run_on={tools_run_on!r})"
        )

    # A typo here used to survive construction and only surface on the first
    # model turn -- after the prompt was built and, for a real run, after the
    # API spend. run_on= validates at the call site and YAML validates at load
    # time; this is the same standard for the third spelling.
    if tools_name is not None and tools_name not in places:
        raise TypeError(
            f"{owner}(tools_run_on={tools_run_on!r}) is not a known place.\n"
            f"  Places that can run tools: {_quote_list(places)}\n"
            f"  Runtimes that host a whole agent: {_quote_list(managed)} "
            f"(pass those as run_on=)"
        )

    # Names that cannot work as a bare string, because the connection details
    # live in the object. Catch it now rather than at first use.
    if tools_name is not None:
        try:
            from ..managed._sandbox_adapter import NEEDS_INSTANCE
        except Exception:
            NEEDS_INSTANCE = {}
        if tools_name in NEEDS_INSTANCE:
            raise TypeError(
                f"{owner}(tools_run_on={tools_run_on!r}) needs more than a name: "
                f"{NEEDS_INSTANCE[tools_name]}"
            )

    # ── two names for the same thing ─────────────────────────────────────────
    if run_on is not None and backend is not None:
        raise TypeError(
            f"{owner}(run_on=..., backend=...) sets the agent's runtime twice. "
            f"run_on={run_on!r} is the short form of backend=HostedAgent("
            f"provider={run_on!r}); pass one or the other.\n"
            f"  Use backend= only when you need to configure the runtime "
            f"(model, system prompt, tools)."
        )

    if run_on is not None and tools_run_on is not None:
        raise TypeError(
            f"{owner}(run_on={run_on!r}, tools_run_on={tools_run_on!r}) points "
            f"the tools at two machines. run_on= already runs everything -- "
            f"including tools -- on {run_on!r}.\n"
            f"  Whole agent remote:  {owner}(run_on={run_on!r})\n"
            f"  Only tools remote:   {owner}(tools_run_on={tools_run_on!r})"
        )

    if backend is not None and tools_run_on is not None:
        raise TypeError(
            f"{owner}(backend=..., tools_run_on={tools_run_on!r}) points the "
            f"tools at two machines: backend= runs the whole agent (tools "
            f"included) on its managed runtime, so the tools cannot also run on "
            f"{tools_run_on!r}.\n"
            f"  Drop tools_run_on= to keep the hosted runtime, or drop backend= "
            f"to keep local thinking with remote tools."
        )

    # ── a class that cannot answer this question ─────────────────────────────
    if run_on is not None and not supports_run_on:
        raise TypeError(
            f"{owner}(run_on={run_on!r}) is not supported: run_on= hands one "
            f"agent's whole loop to a managed runtime, and a {owner} "
            f"orchestrates several agents locally.\n"
            f"  To run every step's tools in one shared sandbox:\n"
            f"      {owner}(tools_run_on={run_on!r})\n"
            f"  To host a single agent's loop, put run_on= on that Agent."
        )

    return Placement(whole=run_on, tools=tools_run_on)

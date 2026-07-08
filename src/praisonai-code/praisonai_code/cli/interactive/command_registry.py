"""
Unified command registry for interactive slash commands.

This module aggregates invocable commands from several pluggable sources into
one namespace so every interactive surface (async TUI, REPL, and future
frontends) resolves ``/name``, ``/help``, and autocomplete from the same place.

Sources (later sources override earlier ones on name collision):

1. Built-in commands (registered by each interactive surface).
2. User/project custom commands discovered from ``.praisonai/commands/*.md``
   via :class:`CustomDefinitionsDiscovery` — the exact same commands that
   ``praisonai run --command <name>`` executes.
3. Skills (``praisonaiagents.skills``) — optional, discovered lazily.
4. MCP server prompts — optional, discovered lazily.
5. Third-party sources registered via the ``praisonai.commands`` entry-point
   group, mirroring the existing ``praisonai.tool_sources`` extensibility.

The registry is intentionally lightweight: it only *describes* commands.
Execution of custom commands reuses the shared ``interpolate_command_template``
path so interactive and CLI invocation are byte-for-byte identical.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CommandKind(str, Enum):
    """Origin of a command, used for help grouping and behaviour."""

    BUILTIN = "builtin"
    CUSTOM = "custom"
    SKILL = "skill"
    MCP = "mcp"
    PLUGIN = "plugin"


@dataclass
class Command:
    """A single invocable slash command descriptor.

    Attributes:
        name: Primary invocation name (without the leading ``/``).
        description: Short one-line help text.
        kind: Where the command came from.
        source: Free-form origin label (``user``/``project``/``builtin``/...).
        handler: Optional callable that performs the command. Built-in surfaces
            usually leave this ``None`` and dispatch via their own branches;
            custom/skill/mcp commands carry a handler that returns the prompt
            text (or performs the action) when invoked.
        aliases: Alternative names that resolve to this command.
    """

    name: str
    description: str = ""
    kind: CommandKind = CommandKind.BUILTIN
    source: str = "builtin"
    handler: Optional[Callable[[str], Any]] = None
    aliases: List[str] = field(default_factory=list)


class CommandSourceProtocol:
    """Structural protocol for a command source.

    A source yields :class:`Command` descriptors. Any object exposing a
    ``discover() -> List[Command]`` method is a valid source; using a plain
    base class (rather than ``typing.Protocol``) keeps runtime ``isinstance``
    checks cheap and avoids importing ``typing_extensions`` on older Pythons.
    """

    def discover(self) -> List[Command]:  # pragma: no cover - interface
        raise NotImplementedError


class BuiltinCommandSource:
    """Wraps a static mapping of built-in commands into a source.

    Interactive surfaces pass their existing hard-coded ``{name: description}``
    help mapping here so the built-ins become first-class registry entries with
    no behaviour change (the surface still dispatches them via its own
    branches; the registry only powers help/autocomplete/collision handling).
    """

    def __init__(self, commands: Dict[str, str]):
        self._commands = dict(commands)

    def discover(self) -> List[Command]:
        return [
            Command(
                name=name,
                description=description,
                kind=CommandKind.BUILTIN,
                source="builtin",
            )
            for name, description in self._commands.items()
        ]


class CustomCommandSource:
    """Source backed by ``.praisonai/commands/*.md`` custom command files.

    Reuses :class:`CustomDefinitionsDiscovery` (the same discovery that powers
    ``praisonai run --command``) so interactive ``/name`` invocation stays in
    lock-step with the CLI. Each command's handler interpolates the template
    via the shared ``interpolate_command_template`` helper.
    """

    def discover(self) -> List[Command]:
        try:
            from ..features.custom_definitions import (
                CustomDefinitionsDiscovery,
                interpolate_command_template,
            )
        except ImportError:  # pragma: no cover - defensive
            return []

        try:
            discovery = CustomDefinitionsDiscovery()
            discovery.discover()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Custom command discovery failed: %s", exc)
            return []

        commands: List[Command] = []
        for cmd in discovery.list_commands():
            def make_handler(cmd_name: str) -> Callable[[str], Optional[str]]:
                def handler(args: str) -> Optional[str]:
                    return interpolate_command_template(cmd_name, args)

                return handler

            commands.append(
                Command(
                    name=cmd.name,
                    description=cmd.description
                    or f"Custom command from {cmd.source}",
                    kind=CommandKind.CUSTOM,
                    source=cmd.source,
                    handler=make_handler(cmd.name),
                )
            )
        return commands


class SkillCommandSource:
    """Optional source exposing discovered skills as invocable commands.

    Skills live in the core SDK (``praisonaiagents.skills``); this source only
    *consumes* them. It fails silently (returns ``[]``) when the skills module
    or any project skills are unavailable, so it never adds import cost or
    breaks surfaces that do not use skills.
    """

    def discover(self) -> List[Command]:
        try:
            from praisonaiagents.skills.discovery import discover_skills
        except Exception:
            return []

        try:
            skills = discover_skills()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Skill discovery unavailable: %s", exc)
            return []

        commands: List[Command] = []
        for skill in skills or []:
            name = getattr(skill, "name", None)
            if not name:
                continue
            commands.append(
                Command(
                    name=str(name),
                    description=getattr(skill, "description", "") or "Skill",
                    kind=CommandKind.SKILL,
                    source="skill",
                )
            )
        return commands


class MCPPromptCommandSource:
    """Optional source exposing MCP server prompts as invocable commands.

    MCP is a core protocol; this source consumes prompts exposed by configured
    MCP servers. It is best-effort and lazy: any failure yields ``[]`` so the
    registry degrades gracefully when MCP is not configured or installed.
    """

    def __init__(self, prompts: Optional[List[Any]] = None):
        self._prompts = prompts

    def discover(self) -> List[Command]:
        prompts = self._prompts
        if prompts is None:
            return []

        commands: List[Command] = []
        for prompt in prompts:
            name = getattr(prompt, "name", None) or (
                prompt.get("name") if isinstance(prompt, dict) else None
            )
            if not name:
                continue
            description = getattr(prompt, "description", None) or (
                prompt.get("description") if isinstance(prompt, dict) else ""
            )
            commands.append(
                Command(
                    name=str(name),
                    description=description or "MCP prompt",
                    kind=CommandKind.MCP,
                    source="mcp",
                )
            )
        return commands


# Entry-point group third parties use to contribute command sources, mirroring
# the existing ``praisonai.tool_sources`` extensibility for tools.
ENTRY_POINT_GROUP = "praisonai.commands"


def _discover_entry_point_sources() -> List[Any]:
    """Load command sources registered via the ``praisonai.commands`` group.

    Each entry point may resolve to either a source instance or a
    zero-argument callable/class returning a source. Failures are logged and
    skipped so a broken third-party plugin never takes down the registry.
    """
    sources: List[Any] = []
    try:
        from importlib.metadata import entry_points
    except Exception:  # pragma: no cover - very old Pythons
        return sources

    try:
        eps = entry_points()
        # Python 3.10+ returns a SelectableGroups object.
        if hasattr(eps, "select"):
            group = eps.select(group=ENTRY_POINT_GROUP)
        else:  # pragma: no cover - legacy mapping API
            group = eps.get(ENTRY_POINT_GROUP, [])
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Entry-point command discovery failed: %s", exc)
        return sources

    for ep in group:
        try:
            obj = ep.load()
            source = obj() if callable(obj) else obj
            if hasattr(source, "discover"):
                sources.append(source)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load command source %r: %s", ep, exc)
    return sources


class CommandRegistry:
    """Aggregates command sources into a single ``/name`` namespace.

    Later sources override earlier ones on name collision, matching the
    user/project override semantics of :class:`CustomDefinitionsDiscovery`.
    """

    def __init__(
        self,
        sources: Optional[List[Any]] = None,
        *,
        discover_entry_points: bool = True,
    ):
        self._sources: List[Any] = list(sources or [])
        self._discover_entry_points = discover_entry_points
        self._commands: Dict[str, Command] = {}
        self._aliases: Dict[str, str] = {}
        self._discovered = False

    def add_source(self, source: Any) -> None:
        """Append a command source (invalidates the discovery cache)."""
        self._sources.append(source)
        self._discovered = False

    def discover(self, force: bool = False) -> Dict[str, Command]:
        """Resolve all sources into ``{name: Command}`` (cached)."""
        if self._discovered and not force:
            return self._commands

        self._commands.clear()
        self._aliases.clear()

        sources = list(self._sources)
        if self._discover_entry_points:
            sources.extend(_discover_entry_point_sources())

        for source in sources:
            try:
                for command in source.discover():
                    self._commands[command.name] = command
                    for alias in command.aliases:
                        self._aliases[alias] = command.name
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Command source %r failed: %s", source, exc)

        self._discovered = True
        return self._commands

    def get(self, name: str) -> Optional[Command]:
        """Look up a command by name or alias."""
        self.discover()
        if name in self._commands:
            return self._commands[name]
        primary = self._aliases.get(name)
        if primary:
            return self._commands.get(primary)
        return None

    def has(self, name: str) -> bool:
        """Return True if ``name`` resolves to a command."""
        return self.get(name) is not None

    def list_commands(self) -> List[Command]:
        """Return all commands sorted by name."""
        self.discover()
        return sorted(self._commands.values(), key=lambda c: c.name)

    def names(self) -> List[str]:
        """Return all command names and aliases, sorted."""
        self.discover()
        return sorted(set(self._commands) | set(self._aliases))

    def completions(self, partial: str) -> List[str]:
        """Return ``/name`` completions for a partial ``/`` input."""
        if not partial.startswith("/"):
            return []
        stub = partial[1:].lower()
        return sorted(
            f"/{name}" for name in self.names() if name.lower().startswith(stub)
        )


def create_default_registry(
    builtins: Optional[Dict[str, str]] = None,
    *,
    include_custom: bool = True,
    include_skills: bool = False,
    include_mcp: bool = False,
    mcp_prompts: Optional[List[Any]] = None,
    discover_entry_points: bool = True,
) -> CommandRegistry:
    """Build a registry wired with the standard sources.

    Args:
        builtins: Optional ``{name: description}`` mapping of a surface's
            built-in commands, registered first (lowest precedence).
        include_custom: Register the ``.praisonai/commands/*.md`` source.
        include_skills: Register the (optional) skills source.
        include_mcp: Register the (optional) MCP prompt source.
        mcp_prompts: Pre-resolved MCP prompts to expose (avoids a live probe).
        discover_entry_points: Scan the ``praisonai.commands`` entry-point group.
    """
    sources: List[Any] = []
    if builtins:
        sources.append(BuiltinCommandSource(builtins))
    if include_custom:
        sources.append(CustomCommandSource())
    if include_skills:
        sources.append(SkillCommandSource())
    if include_mcp:
        sources.append(MCPPromptCommandSource(mcp_prompts))
    return CommandRegistry(sources, discover_entry_points=discover_entry_points)

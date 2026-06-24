"""
Blueprint protocol definitions for PraisonAI Agents.

This module defines the thin protocol layer for automation blueprints —
data structures that carry metadata about parameterized automation
templates without any execution logic.  Heavy resolution and resource
handling lives in ``praisonai.scheduler.blueprint_catalogue``.

Usage::

    from praisonaiagents.scheduler.blueprint_defs import Blueprint, BlueprintSlot

    bp = Blueprint(
        name="morning-brief",
        description="Daily morning briefing",
        slots=[BlueprintSlot(name="hour", type="int", default=8)],
        prompt_template="Provide a briefing. Focus: {focus}",
        schedule_template="cron:{minute} {hour} * * {weekdays_expression}",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ── Slot definition ──────────────────────────────────────────────────────────


@dataclass
class BlueprintSlot:
    """A fillable parameter slot in a blueprint template.

    Each slot represents one user-configurable parameter.  Slots
    have types, defaults, and optional choice constraints that the
    catalogue layer validates at resolution time.
    """

    name: str
    """Machine-readable slot name (e.g. ``"hour"``, ``"focus"``)."""

    type: str = "str"
    """Slot type: ``"int"``, ``"str"``, ``"choice"``, ``"time"``."""

    label: str = ""
    """Human-readable label for UI surfaces."""

    default: Any = None
    """Default value when the user does not provide one."""

    required: bool = True
    """If True, the user must supply a value (unless ``default`` is set)."""

    choices: Optional[List[str]] = None
    """Allowed values for ``type="choice"`` slots."""

    description: str = ""
    """Help text explaining what this slot controls."""


# ── Blueprint definition ─────────────────────────────────────────────────────


@dataclass
class Blueprint:
    """A parameterized automation template.

    Blueprints are named templates with fillable slots.  They carry
    enough metadata for CLI, YAML, and Python surfaces to present a
    consistent authoring experience.  The catalogue layer resolves
    slots, materializes prompts, and produces concrete schedule
    expressions.

    This is a protocol-level dataclass — no execution logic here.
    """

    name: str
    """Unique blueprint identifier (e.g. ``"morning-brief"``)."""

    version: str = "1.0.0"
    """SemVer version string."""

    description: str = ""
    """One-paragraph summary shown in listings and help."""

    tags: List[str] = field(default_factory=list)
    """Search tags (e.g. ``["daily", "news"]``)."""

    category: str = "general"
    """Grouping label for UI surfaces (``"daily"``, ``"monitoring"``, …)."""

    slots: List[BlueprintSlot] = field(default_factory=list)
    """Fillable parameters the user can configure."""

    default_deliver: str = ""
    """Default delivery target (``"telegram"``, ``"origin"``, etc.)."""

    default_agent: str = ""
    """Default agent ID to execute this blueprint."""

    prompt_template: str = ""
    """Prompt string with ``{slot_name}`` placeholders filled at resolution."""

    schedule_template: str = ""
    """Schedule string with ``{slot_name}`` placeholders.

    Supports a special ``{weekdays_expression}`` placeholder that the
    catalogue layer converts to a cron day-of-week field.
    """

    builtin: bool = True
    """True for the built-in catalogue; False for user-provided YAML blueprints."""


# ── Store protocol ───────────────────────────────────────────────────────────


@runtime_checkable
class BlueprintStoreProtocol(Protocol):
    """Minimal protocol for discovering and registering blueprints.

    Any object that satisfies this protocol can serve as a blueprint
    source for the catalogue.  The built-in :class:`BlueprintCatalogue`
    implements this, as could a remote registry or dashboard backend.
    """

    def list_blueprints(self, category: Optional[str] = None) -> List[Blueprint]:
        """Return all known blueprints, optionally filtered by *category*."""
        ...

    def get_blueprint(self, name: str) -> Optional[Blueprint]:
        """Return the blueprint named *name*, or ``None`` if not found."""
        ...

    def register_blueprint(self, bp: Blueprint) -> None:
        """Register (or replace) *bp* in the store."""
        ...

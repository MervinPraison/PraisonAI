"""
Blueprint Catalogue — discovery, registration, slot resolution, and
schedule materialization for parameterized automation templates.

This module provides the heavy implementation side of the blueprint
system.  The thin protocol dataclasses live in
``praisonaiagents.scheduler.blueprint_defs``.

Built-in blueprints are defined here as an in-memory dictionary.
The catalogue also discovers user-provided YAML blueprints from
``~/.praisonai/blueprints/`` and custom directories.

Usage::

    from praisonai.scheduler.blueprint_catalogue import BlueprintCatalogue

    catalogue = BlueprintCatalogue()
    bp = catalogue.get_blueprint("morning-brief")
    resolved = catalogue.resolve_slots(bp, {"hour": 8, "weekdays": "mon-fri"})
    prompt  = catalogue.materialize_prompt(bp, resolved)
    schedule = catalogue.materialize_schedule(bp, resolved)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from praisonaiagents.scheduler.blueprint_defs import Blueprint, BlueprintSlot

logger = logging.getLogger(__name__)

# ── Built-in blueprints ─────────────────────────────────────────────────────


BUILTIN_BLUEPRINTS: Dict[str, Blueprint] = {
    "morning-brief": Blueprint(
        name="morning-brief",
        version="1.0.0",
        description="Daily morning briefing with news and priorities",
        tags=["daily", "news", "briefing"],
        category="daily",
        default_deliver="telegram",
        prompt_template=(
            "You are a morning briefing assistant. "
            "Provide a concise summary of today's priorities and news. "
            "Focus area: {focus}. "
            "Be brief but comprehensive."
        ),
        schedule_template="cron:{minute} {hour} * * {weekdays_expression}",
        slots=[
            BlueprintSlot(
                name="hour", type="int", label="Delivery hour (0-23)",
                default=8, description="Hour in 24h format",
            ),
            BlueprintSlot(
                name="minute", type="int", label="Delivery minute (0-59)",
                default=0, description="Minute of the hour",
            ),
            BlueprintSlot(
                name="weekdays", type="choice", label="Days of week",
                default="mon-fri",
                choices=["mon-fri", "daily", "weekends",
                         "mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                description="Which days to run",
            ),
            BlueprintSlot(
                name="focus", type="choice", label="Focus area",
                default="general",
                choices=["general", "tech", "business", "science", "custom"],
                description="News focus area",
            ),
        ],
        builtin=True,
    ),
    "important-mail": Blueprint(
        name="important-mail",
        version="1.0.0",
        description="Check for important emails at a regular interval",
        tags=["email", "notification"],
        category="monitoring",
        default_deliver="telegram",
        prompt_template=(
            "Check the user's email for any important unread messages. "
            "Summarize the most critical ones. "
            "Priority keywords: {keywords}. "
            "Be concise."
        ),
        schedule_template="*/{interval_minutes}m",
        slots=[
            BlueprintSlot(
                name="interval_minutes", type="int",
                label="Check interval (minutes)",
                default=30, description="How often to check",
            ),
            BlueprintSlot(
                name="keywords", type="str",
                label="Priority keywords",
                default="urgent,important,deadline",
                description="Comma-separated priority keywords",
            ),
        ],
        builtin=True,
    ),
    "weekly-review": Blueprint(
        name="weekly-review",
        version="1.0.0",
        description="End-of-week summary and review",
        tags=["weekly", "review", "summary"],
        category="weekly",
        default_deliver="telegram",
        prompt_template=(
            "Prepare an end-of-week review covering: "
            "1) Key accomplishments. "
            "2) Pending items. "
            "3) Priorities for next week. "
            "Focus on: {focus}."
        ),
        schedule_template="cron:{minute} {hour} * * {weekdays_expression}",
        slots=[
            BlueprintSlot(
                name="hour", type="int", label="Delivery hour (0-23)",
                default=17, description="Hour in 24h format",
            ),
            BlueprintSlot(
                name="minute", type="int", label="Delivery minute",
                default=0,
            ),
            BlueprintSlot(
                name="weekdays", type="choice", label="Day of week",
                default="fri",
                choices=["fri", "sat", "sun", "mon", "tue", "wed", "thu"],
                description="Which day to deliver",
            ),
            BlueprintSlot(
                name="focus", type="choice", label="Focus area",
                default="general",
                choices=["general", "tech", "business", "work"],
            ),
        ],
        builtin=True,
    ),
}


# ── Catalogue ────────────────────────────────────────────────────────────────


class BlueprintCatalogue:
    """Registry and resolver for automation blueprints.

    Discovery order (last wins):
      1. Built-in blueprints (in-memory dict above)
      2. YAML blueprint files from ``~/.praisonai/blueprints/``
      3. YAML blueprint files from custom directories

    Custom blueprints override builtins of the same name.
    """

    BLUEPRINTS_DIR_NAME: str = "blueprints"
    BLUEPRINT_FILE: str = "blueprint.yaml"

    def __init__(self, custom_dirs: Optional[List[str]] = None):
        self._blueprints: Dict[str, Blueprint] = {}
        self._custom_dirs = custom_dirs or []
        self._loaded = False

    # -- discovery -----------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Lazy-load the catalogue (builtins + user dirs) on first access."""
        if self._loaded:
            return

        # 1. Builtins
        self._blueprints.update(BUILTIN_BLUEPRINTS)

        # 2. User blueprints from ~/.praisonai/blueprints/
        try:
            from praisonaiagents.paths import get_data_dir
            user_dir = get_data_dir() / self.BLUEPRINTS_DIR_NAME
            self._load_from_directory(user_dir, custom=True)
        except Exception as e:
            logger.debug("Skipping user blueprint dir: %s", e)

        # 3. Custom directories
        for d in self._custom_dirs:
            self._load_from_directory(Path(d), custom=True)

        self._loaded = True

    def _load_from_directory(self, directory: Path, *, custom: bool) -> None:
        """Scan *directory* for ``<name>/blueprint.yaml`` subdirectories."""
        if not directory.is_dir():
            return
        for item in sorted(directory.iterdir()):
            if not item.is_dir():
                continue
            bp_file = item / self.BLUEPRINT_FILE
            if bp_file.is_file():
                bp = self._parse_blueprint_yaml(bp_file, custom=custom)
                if bp is not None:
                    self._blueprints[bp.name] = bp

    def _parse_blueprint_yaml(
        self, path: Path, *, custom: bool
    ) -> Optional[Blueprint]:
        """Parse a ``blueprint.yaml`` file into a :class:`Blueprint`."""
        import yaml

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Failed to read blueprint YAML %s: %s", path, e)
            return None

        try:
            slots = []
            for s in data.get("slots", []):
                slots.append(BlueprintSlot(
                    name=s["name"],
                    type=s.get("type", "str"),
                    label=s.get("label", s["name"]),
                    default=s.get("default"),
                    required=s.get("required", True),
                    choices=s.get("choices"),
                    description=s.get("description", ""),
                ))
            return Blueprint(
                name=data["name"],
                version=data.get("version", "1.0.0"),
                description=data.get("description", ""),
                tags=data.get("tags", []),
                category=data.get("category", "general"),
                slots=slots,
                default_deliver=data.get("default_deliver", ""),
                default_agent=data.get("default_agent", ""),
                prompt_template=data.get("prompt_template", ""),
                schedule_template=data.get("schedule_template", ""),
                builtin=not custom,
            )
        except KeyError as e:
            logger.warning("Missing required key %s in %s", e, path)
            return None

    # -- public API ----------------------------------------------------------

    def list_blueprints(self, category: Optional[str] = None) -> List[Blueprint]:
        """Return all known blueprints, optionally filtered by *category*."""
        self._ensure_loaded()
        if category:
            return [bp for bp in self._blueprints.values()
                    if bp.category == category]
        return list(self._blueprints.values())

    def get_blueprint(self, name: str) -> Optional[Blueprint]:
        """Return the blueprint named *name*, or ``None`` if not found."""
        self._ensure_loaded()
        return self._blueprints.get(name)

    def register_blueprint(self, bp: Blueprint) -> None:
        """Register (or replace) a blueprint in the catalogue."""
        self._ensure_loaded()
        self._blueprints[bp.name] = bp

    # -- slot resolution -----------------------------------------------------

    def resolve_slots(
        self, bp: Blueprint, slots: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge user-provided *slots* with blueprint defaults.

        Validates that all required slots are satisfied and that choice
        values are within the allowed set.

        Raises:
            ValueError: If a required slot is missing or a choice value
                        is not in the allowed list.
        """
        resolved: Dict[str, Any] = {}
        for slot in bp.slots:
            value = slots.get(slot.name, slot.default)
            if slot.required and value is None:
                raise ValueError(
                    f"Required slot '{slot.name}' is missing "
                    f"for blueprint '{bp.name}'"
                )
            if slot.choices and value is not None and value not in slot.choices:
                raise ValueError(
                    f"Slot '{slot.name}' value '{value}' is not in "
                    f"allowed choices {slot.choices}"
                )
            resolved[slot.name] = value
        return resolved

    # -- materialization -----------------------------------------------------

    def materialize_prompt(
        self, bp: Blueprint, resolved: Dict[str, Any]
    ) -> str:
        """Fill the prompt template with resolved slot values.

        Uses Python's ``str.format()`` — *resolved* must contain every
        key referenced in ``bp.prompt_template``.
        """
        return bp.prompt_template.format(**resolved)

    def materialize_schedule(
        self, bp: Blueprint, resolved: Dict[str, Any]
    ) -> str:
        """Fill the schedule template with resolved slot values.

        Special handling for ``{weekdays_expression}``: when the template
        contains this placeholder, the ``weekdays`` slot value is
        converted to a cron day-of-week field before substitution.
        """
        materialized = dict(resolved)
        if "{weekdays_expression}" in bp.schedule_template:
            raw = self._weekdays_to_cron(
                str(resolved.get("weekdays", "mon-fri"))
            )
            materialized["weekdays_expression"] = raw
        return bp.schedule_template.format(**materialized)

    @staticmethod
    def _weekdays_to_cron(weekdays: str) -> str:
        """Convert a friendly weekday spec to a cron day-of-week field."""
        mapping: Dict[str, str] = {
            "mon-fri": "1-5",
            "daily": "*",
            "weekends": "0,6",
            "mon": "1",
            "tue": "2",
            "wed": "3",
            "thu": "4",
            "fri": "5",
            "sat": "6",
            "sun": "0",
        }
        lower = weekdays.lower().strip()
        return mapping.get(lower, lower)

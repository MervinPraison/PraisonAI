"""
Shared automation-suggestion & blueprint chat helpers for PraisonAI bots.

Surfaces the already-built consent-first suggestion/blueprint engine
(``praisonai.scheduler.suggestion_engine.SuggestionEngine`` +
``praisonai.scheduler.blueprint_catalogue.BlueprintCatalogue``) through the
conversational gateway. The gap this closes is purely *wiring*: every primitive
already exists; these helpers keep the accept/dismiss/blueprint glue in one
place so Telegram, Discord and Slack adapters stay DRY (same pattern as
``_commands.py``).

Nothing is ever auto-created here — the engine only materialises a scheduled
job on an explicit ``accept``. ``MAX_PENDING_CAP`` and dedup are enforced by the
underlying store, so the chat layer inherits safe-by-default behaviour.

Scope note: the underlying ``SuggestionStore`` is a single, global,
single-tenant store (``~/.praisonai/suggestions.json``) with no per-user field
on :class:`~praisonaiagents.scheduler.suggestion_store.Suggestion`. Suggestions
are therefore shared across everyone who can reach the gateway — exactly like
the ``praisonai schedule`` CLI. Access is gated by ``CommandAccessPolicy`` (the
``automations`` permission is re-checked on every accept/dismiss tap); restrict
that policy to admins for multi-user bots. Per-user scoping would require a core
data-model change to ``Suggestion``/``SuggestionStore`` and is intentionally out
of scope for this wrapper wiring.

Callback contract (reused by every platform's inline-keyboard path):
    ``sug:accept:<id>``   → accept a suggestion (materialises exactly one job)
    ``sug:dismiss:<id>``  → dismiss a suggestion (latches the dedup key)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Callback namespace + prefixes shared across platforms. The interactive
# registry decodes ``sug:accept:<id>`` as namespace ``sug`` with the remainder
# as the payload value (see praisonaiagents.bots.interactive.decode_callback).
CALLBACK_NAMESPACE = "sug"


def _engine():
    """Lazy-import and return a SuggestionEngine, or ``None`` if unavailable."""
    try:
        from praisonai.scheduler.suggestion_engine import SuggestionEngine
    except Exception as e:  # noqa: BLE001 - wrapper/scheduler may be absent
        logger.debug("SuggestionEngine unavailable: %s", e)
        return None
    try:
        return SuggestionEngine()
    except Exception as e:  # noqa: BLE001
        logger.debug("Failed to construct SuggestionEngine: %s", e)
        return None


def _catalogue():
    """Lazy-import and return a BlueprintCatalogue, or ``None`` if unavailable."""
    try:
        from praisonai.scheduler.blueprint_catalogue import BlueprintCatalogue
    except Exception as e:  # noqa: BLE001
        logger.debug("BlueprintCatalogue unavailable: %s", e)
        return None
    try:
        return BlueprintCatalogue()
    except Exception as e:  # noqa: BLE001
        logger.debug("Failed to construct BlueprintCatalogue: %s", e)
        return None


def accept_callback(suggestion_id: str) -> str:
    """Return the callback token that accepts *suggestion_id*."""
    return f"{CALLBACK_NAMESPACE}:accept:{suggestion_id}"


def dismiss_callback(suggestion_id: str) -> str:
    """Return the callback token that dismisses *suggestion_id*."""
    return f"{CALLBACK_NAMESPACE}:dismiss:{suggestion_id}"


def parse_callback(value: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse the payload of a ``sug`` callback into ``(action, suggestion_id)``.

    The interactive registry strips the ``sug:`` namespace and hands the
    remainder (``accept:<id>`` / ``dismiss:<id>``) here.

    Args:
        value: The decoded callback payload, e.g. ``"accept:sug_ab12"``.

    Returns:
        ``(action, suggestion_id)`` where *action* is ``"accept"`` or
        ``"dismiss"``; ``(None, None)`` when the payload is malformed.
    """
    if not value:
        return (None, None)
    parts = value.split(":", 1)
    if len(parts) != 2:
        return (None, None)
    action, sug_id = parts[0].strip(), parts[1].strip()
    if action not in ("accept", "dismiss") or not sug_id:
        return (None, None)
    return (action, sug_id)


def _suggestion_line(sug: Any) -> str:
    """Render a one-suggestion summary line for chat display."""
    slot_str = ", ".join(f"{k}={v}" for k, v in (sug.slots or {}).items())
    reason = getattr(sug, "reason", "") or "Suggested automation"
    detail = f"{sug.blueprint_name}"
    if slot_str:
        detail += f" · {slot_str}"
    return f"💡 {reason}\n{detail}"


def list_suggestions() -> List[Dict[str, Any]]:
    """Return pending suggestions as render-ready dicts for the chat layer.

    Each item carries the display ``text`` plus the Accept/Dismiss button
    ``(label, callback)`` tuples so every platform adapter can post inline
    keyboards without re-implementing the formatting.

    Returns:
        A list of ``{"id", "text", "buttons"}`` dicts. Empty when there are no
        pending suggestions or the engine is unavailable.
    """
    engine = _engine()
    if engine is None:
        return []
    try:
        pending = engine.pending()
    except Exception as e:  # noqa: BLE001
        logger.debug("Failed to list pending suggestions: %s", e)
        return []

    items: List[Dict[str, Any]] = []
    for sug in pending:
        items.append({
            "id": sug.id,
            "text": _suggestion_line(sug),
            "buttons": [
                ("✓ Accept", accept_callback(sug.id)),
                ("✕ Dismiss", dismiss_callback(sug.id)),
            ],
        })
    return items


def accept_suggestion(suggestion_id: str, deliver: str = "") -> str:
    """Accept a suggestion and materialise exactly one scheduled job.

    Mirrors the CLI ``schedule suggestion-accept`` path: resolves the
    blueprint, materialises the prompt + schedule, and calls ``schedule_add``
    with ``accept_suggestion`` so the store marks the suggestion accepted.

    Args:
        suggestion_id: The suggestion to accept.
        deliver: Optional delivery-target override (falls back to the
            suggestion's own target, then the blueprint default).

    Returns:
        A user-facing confirmation or error string.
    """
    engine = _engine()
    if engine is None:
        return "❌ Automations are not available (scheduler not installed)."

    try:
        sug = engine.get_suggestion(suggestion_id)
    except Exception as e:  # noqa: BLE001
        return f"❌ Could not read suggestion: {e}"

    if sug is None or getattr(sug, "dismissed", False) or getattr(sug, "accepted", False):
        return "ℹ️ That suggestion was not found or has already been handled."

    import time as _time
    expires_at = getattr(sug, "expires_at", 0) or 0
    if expires_at and expires_at <= _time.time():
        return "⌛ That suggestion has expired."

    catalogue = _catalogue()
    if catalogue is None:
        return "❌ Blueprint catalogue is not available."

    bp = catalogue.get_blueprint(sug.blueprint_name)
    if bp is None:
        return f"❌ Blueprint '{sug.blueprint_name}' for this suggestion was not found."

    try:
        from praisonaiagents.tools.schedule_tools import schedule_add as _schedule_add
    except Exception as e:  # noqa: BLE001
        return f"❌ Scheduler tools unavailable: {e}"

    try:
        resolved = catalogue.resolve_slots(bp, sug.slots)
        prompt = catalogue.materialize_prompt(bp, resolved)
        schedule_expr = catalogue.materialize_schedule(bp, resolved)
        final_deliver = deliver or sug.deliver or bp.default_deliver
        result = _schedule_add(
            name=sug.blueprint_name,
            schedule=schedule_expr,
            message=prompt,
            deliver=final_deliver,
            accept_suggestion=suggestion_id,
        )
    except Exception as e:  # noqa: BLE001
        return f"❌ Could not create automation: {e}"

    if str(result).startswith("Error") or "already exists" in str(result):
        return f"❌ {result}"
    return f"✅ Automation scheduled. {result}"


def dismiss_suggestion(suggestion_id: str) -> str:
    """Dismiss a suggestion so it is not re-offered.

    Args:
        suggestion_id: The suggestion to dismiss.

    Returns:
        A user-facing confirmation or error string.
    """
    engine = _engine()
    if engine is None:
        return "❌ Automations are not available (scheduler not installed)."
    try:
        ok = engine.dismiss(suggestion_id)
    except Exception as e:  # noqa: BLE001
        return f"❌ Could not dismiss suggestion: {e}"
    return "✕ Dismissed. I won't suggest that again." if ok else \
        "ℹ️ That suggestion was not found."


def blueprint_help_text() -> str:
    """Return usage guidance listing the available blueprints."""
    catalogue = _catalogue()
    if catalogue is None:
        return "❌ Blueprints are not available (scheduler not installed)."
    try:
        blueprints = catalogue.list_blueprints()
    except Exception as e:  # noqa: BLE001
        return f"❌ Could not list blueprints: {e}"
    if not blueprints:
        return "No blueprints available."
    lines = ["📋 Create an automation from a template:", ""]
    for bp in blueprints:
        lines.append(f"• {bp.name} — {bp.description}")
    lines.append("")
    lines.append("Usage: /blueprint <name> [slot=value ...]")
    lines.append("Example: /blueprint morning-brief hour=8 weekdays=mon-fri")
    return "\n".join(lines)


def _parse_slot_args(args: str) -> Dict[str, Any]:
    """Parse ``key=value key2=value2`` slot overrides from a chat command.

    Values are coerced to ``int`` when they look numeric so integer slots
    (hour, minute, interval_minutes) resolve correctly.
    """
    slots: Dict[str, Any] = {}
    for token in (args or "").split():
        if "=" not in token:
            continue
        key, _, raw = token.partition("=")
        key = key.strip()
        raw = raw.strip()
        if not key:
            continue
        if raw.lstrip("-").isdigit():
            slots[key] = int(raw)
        else:
            slots[key] = raw
    return slots


def create_from_blueprint(
    blueprint_name: str,
    args: str = "",
    deliver: str = "",
) -> str:
    """Create an automation directly from a blueprint via chat.

    Parses ``key=value`` slot overrides from *args*, resolves them against the
    blueprint's typed slots (defaults fill the rest), and schedules the job via
    the existing catalogue — the chat equivalent of
    ``praisonai schedule blueprint``.

    Args:
        blueprint_name: The blueprint to instantiate (empty → usage help).
        args: Space-separated ``key=value`` slot overrides.
        deliver: Optional delivery-target override.

    Returns:
        A user-facing confirmation or error/usage string.
    """
    if not blueprint_name or not blueprint_name.strip():
        return blueprint_help_text()

    blueprint_name = blueprint_name.strip()
    catalogue = _catalogue()
    if catalogue is None:
        return "❌ Blueprints are not available (scheduler not installed)."

    bp = catalogue.get_blueprint(blueprint_name)
    if bp is None:
        try:
            available = ", ".join(b.name for b in catalogue.list_blueprints())
        except Exception:  # noqa: BLE001
            available = ""
        avail_msg = f" Available: {available}" if available else ""
        return f"❌ Blueprint '{blueprint_name}' not found.{avail_msg}"

    try:
        from praisonaiagents.tools.schedule_tools import schedule_add as _schedule_add
    except Exception as e:  # noqa: BLE001
        return f"❌ Scheduler tools unavailable: {e}"

    try:
        slots = _parse_slot_args(args)
        resolved = catalogue.resolve_slots(bp, slots)
        prompt = catalogue.materialize_prompt(bp, resolved)
        schedule_expr = catalogue.materialize_schedule(bp, resolved)
        final_deliver = deliver or bp.default_deliver
        result = _schedule_add(
            name=blueprint_name,
            schedule=schedule_expr,
            message=prompt,
            deliver=final_deliver,
            agent_id=bp.default_agent,
        )
    except ValueError as e:
        # Slot validation failed (bad choice / missing required slot).
        return f"❌ {e}"
    except Exception as e:  # noqa: BLE001
        return f"❌ Could not create automation: {e}"

    if str(result).startswith("Error") or "already exists" in str(result):
        return f"❌ {result}"
    return f"✅ Automation scheduled from '{blueprint_name}'. {result}"


def format_automations_header(count: int) -> str:
    """Return the header line shown before listing pending suggestions."""
    if count == 0:
        return (
            "You have no pending automation suggestions.\n"
            "Use /blueprint to create one from a template."
        )
    plural = "s" if count != 1 else ""
    return f"💡 You have {count} pending automation suggestion{plural}:"

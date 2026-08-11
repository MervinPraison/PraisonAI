"""
Shared base class for messaging-platform approval backends.

Extracts the common sync-wrapper, timeout, poll_interval, and keyword
matching logic so that SlackApproval, TelegramApproval, and DiscordApproval
only need to implement the platform-specific bits.

This is an internal module — end users import the concrete classes.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Single source of truth for the human-in-the-loop wait window shared by the
# chat channel backends (Slack, Telegram, Discord, Webhook, HTTP). Individual
# backends may still override via ``timeout=``.
DEFAULT_APPROVAL_TIMEOUT: float = 300.0

APPROVE_KEYWORDS: Set[str] = {
    "yes", "y", "approve", "approved", "ok", "allow", "go", "proceed", "confirm",
}
DENY_KEYWORDS: Set[str] = {
    "no", "n", "deny", "denied", "reject", "block", "stop", "cancel", "refuse",
}


def classify_keyword(text: str) -> str | None:
    """Classify *text* as ``'approve'``, ``'deny'``, or ``None``."""
    t = text.strip().lower()
    if t in APPROVE_KEYWORDS:
        return "approve"
    if t in DENY_KEYWORDS:
        return "deny"
    return None


def normalize_approvers(
    allowed_approvers: Optional[Union[Iterable[str], str]],
) -> Optional[Set[str]]:
    """Normalise an allowed-approver allowlist to a ``set`` of ``str`` IDs.

    Returns ``None`` when *allowed_approvers* is ``None`` (no restriction —
    legacy behaviour). Otherwise returns a set of stringified IDs so
    cross-platform user IDs (int Telegram ids, str Slack/Discord ids) compare
    consistently.
    """
    if allowed_approvers is None:
        return None
    if isinstance(allowed_approvers, str):
        allowed_approvers = allowed_approvers.split(",")
    return {str(a).strip() for a in allowed_approvers if str(a).strip()}


def is_authorized_actor(
    actor: Optional[str],
    allowed_approvers: Optional[Set[str]],
) -> bool:
    """Return whether *actor* may resolve an approval.

    This is the security boundary for chat-native (inline button / keyword
    reply) approvals: when an allowlist is configured, only an actor in it may
    approve or deny a gated tool, so an unauthorised group member's tap/reply
    can never resolve the request.

    Args:
        actor: The resolving user's ID (may be ``None`` if the channel could
            not determine it).
        allowed_approvers: Normalised allowlist (see :func:`normalize_approvers`).
            ``None`` means no restriction (any actor allowed — legacy
            behaviour). An empty set denies everyone.

    Returns:
        ``True`` when there is no restriction, or *actor* is in the allowlist;
        ``False`` otherwise (including when *actor* is ``None`` but an
        allowlist is configured).
    """
    if allowed_approvers is None:
        return True
    return actor is not None and str(actor) in allowed_approvers


async def classify_with_llm(
    text: str,
    tool_name: str,
    arguments: dict,
    risk_level: str = "medium",
) -> dict:
    """Classify a free-text approval response using an LLM.

    When a user replies with something richer than a simple yes/no (e.g.
    *"yes, but path is ~/Downloads"*), we ask a lightweight LLM to:

    1. Determine intent: ``approved`` (bool).
    2. Extract any **modified arguments** the user specified.

    Args:
        text:       The raw user reply text.
        tool_name:  Name of the tool awaiting approval.
        arguments:  Original arguments dict the tool would be called with.
        risk_level: Risk classification string.

    Returns:
        ``{"approved": bool, "reason": str, "modified_args": dict}``
        where *modified_args* may be empty if no modifications were requested.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — cannot classify with LLM")
        return {"approved": False, "reason": "LLM classification unavailable", "modified_args": {}}

    import json as _json
    import os as _os

    args_str = _json.dumps(arguments, indent=2, default=str)

    system_prompt = (
        "You are a tool-approval classifier. A human was asked to approve or deny "
        "a tool execution and replied with a free-text message. Your job:\n"
        "1. Determine if the human APPROVED or DENIED the execution.\n"
        "2. Extract any MODIFIED ARGUMENTS from their reply.\n\n"
        "Respond with ONLY valid JSON (no markdown fences):\n"
        '{"approved": true/false, "reason": "short explanation", '
        '"modified_args": {"arg_name": "new_value", ...}}\n\n'
        "Rules:\n"
        '- If the reply clearly means yes/approve/go ahead (even with extra context), set approved=true.\n'
        '- If the reply clearly means no/deny/reject, set approved=false.\n'
        "- If the reply contains corrections or new values for any of the original arguments, "
        "include them in modified_args using the EXACT original argument key names.\n"
        "- modified_args should be empty {} if no modifications were mentioned.\n"
        "- Only include arguments that were actually changed, not unchanged ones.\n"
    )

    user_prompt = (
        f"Tool: {tool_name}\n"
        f"Risk: {risk_level}\n"
        f"Original arguments:\n{args_str}\n\n"
        f"Human reply: \"{text}\"\n\n"
        "Classify this reply as JSON:"
    )

    try:
        from praisonai_bot._code_bridge import import_code_module

        resolve_llm_endpoint = import_code_module("praisonai_code.llm.env").resolve_llm_endpoint
        ep = resolve_llm_endpoint()
        
        client = OpenAI(
            api_key=ep.api_key or "",
            base_url=ep.base_url,
        )
        response = client.chat.completions.create(
            model=_os.environ.get("APPROVAL_LLM_MODEL", ep.model),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = _json.loads(raw)
        return {
            "approved": bool(result.get("approved", False)),
            "reason": str(result.get("reason", text)),
            "modified_args": result.get("modified_args", {}),
        }
    except Exception as e:
        logger.warning(f"LLM approval classification failed: {e}")
        return {"approved": False, "reason": f"Could not classify response: {text}", "modified_args": {}}


class DurableApprovalMixin:
    """Optional durability for chat-channel approval backends.

    Pending approvals are normally held only in the per-call coroutine that
    polls the platform for a reply; a gateway/bot restart while an approval is
    outstanding strands the blocked agent run. Mixing this in gives every chat
    backend a uniform, opt-in persistence path backed by the existing
    :class:`ApprovalStore` (SQLite+WAL) without changing its transport logic:

    * :meth:`_persist_pending` records the request before the backend starts
      polling, so it survives a restart.
    * :meth:`_resolve_pending` records the final decision as a durable audit
      trail (and closes the row so a late reply can't re-resolve it).
    * :meth:`rehydrate` lists still-pending approvals on startup so an operator
      / caller can re-attach to them after a restart.

    When no ``store`` is configured every method is a no-op, so existing
    behaviour is unchanged and the feature is fully backward-compatible.
    """

    _approval_store: Optional[Any] = None

    def _init_store(self, store: Optional[Any]) -> None:
        """Record the optional durable store (call from ``__init__``)."""
        self._approval_store = store

    async def _persist_pending(self, request: Any, timeout: float) -> None:
        """Durably persist *request* before waiting for a decision."""
        store = getattr(self, "_approval_store", None)
        if store is None or getattr(request, "approval_id", None) is None:
            return
        try:
            expires_at = time.time() + float(timeout)
            await store.persist(request.approval_id, request, expires_at=expires_at)
        except Exception:  # persistence must never break the live approval
            logger.warning(
                "Failed to persist pending approval %s",
                getattr(request, "approval_id", "?"),
                exc_info=True,
            )

    async def _resolve_pending(self, request: Any, decision: Any) -> None:
        """Record the final *decision* for *request* in the durable store."""
        store = getattr(self, "_approval_store", None)
        if store is None or getattr(request, "approval_id", None) is None:
            return
        try:
            await store.resolve(request.approval_id, decision)
        except Exception:
            logger.warning(
                "Failed to record approval decision %s",
                getattr(request, "approval_id", "?"),
                exc_info=True,
            )

    async def rehydrate(self) -> List[Tuple[str, Any]]:
        """Return still-pending approvals from the durable store on startup.

        Call once after a restart to recover outstanding approvals. Returns an
        empty list when no store is configured.
        """
        store = getattr(self, "_approval_store", None)
        if store is None:
            return []
        try:
            return await store.list_pending()
        except Exception:
            logger.warning("Failed to rehydrate pending approvals", exc_info=True)
            return []


def sync_wrapper(async_fn, timeout: float):
    """Run *async_fn* (a coroutine) synchronously, handling nested loops."""
    from .._async_bridge import run_sync
    return run_sync(async_fn, timeout=timeout)

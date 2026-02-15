"""
Shared base class for messaging-platform approval backends.

Extracts the common sync-wrapper, timeout, poll_interval, and keyword
matching logic so that SlackApproval, TelegramApproval, and DiscordApproval
only need to implement the platform-specific bits.

This is an internal module — end users import the concrete classes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Set

logger = logging.getLogger(__name__)

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
        client = OpenAI(
            api_key=_os.environ.get("OPENAI_API_KEY", ""),
            base_url=_os.environ.get("OPENAI_BASE_URL"),
        )
        response = client.chat.completions.create(
            model=_os.environ.get("APPROVAL_LLM_MODEL", "gpt-4o-mini"),
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


def sync_wrapper(async_fn, timeout: float):
    """Run *async_fn* (a coroutine) synchronously, handling nested loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, async_fn)
            return future.result(timeout=timeout + 10)
    else:
        return asyncio.run(async_fn)

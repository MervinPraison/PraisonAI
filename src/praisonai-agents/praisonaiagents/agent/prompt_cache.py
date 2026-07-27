"""Prompt-cache-stability contract for the Agent turn (Issue #3352).

Provider prompt caching (Anthropic/OpenAI) only hits when the *leading* bytes
of a request are byte-identical to the previous request. For a long-lived
conversation the cached prefix — the system instructions, the serialised tool
schemas, and the model identity — is the dominant cost and latency lever.

Gateways run many users on a single shared ``Agent`` instance and swap
``tools``/``llm`` in and out per turn (per-route tool scoping, per-user
``/model`` override). Those swaps silently change the cached prefix and the
provider cache misses with zero operator visibility.

``prompt_prefix_signature`` gives callers a single, cheap, deterministic
fingerprint of exactly the cache-relevant inputs — model, the sorted set of
tool names, and a fingerprint of the system instructions — and *nothing*
volatile per-turn (arrival time, routing facts, memory/RAG recall). When the
signature is unchanged across turns the prefix is guaranteed stable, so the
provider cache keeps hitting; when it changes, that is the one auditable point
at which cache warmth is knowingly sacrificed.
"""

from __future__ import annotations

import hashlib
from typing import Any


def _tool_name(tool: Any) -> str:
    """Best-effort stable name for a tool entry.

    Tools may be plain callables, dicts holding an OpenAI-style function
    schema, or objects exposing ``__name__``/``name``. The name identifies the
    schema slot in the serialised tool block.
    """
    if isinstance(tool, dict):
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return str(fn["name"])
        for key in ("name", "type"):
            if tool.get(key):
                return str(tool[key])
        return str(sorted(tool.keys()))
    for attr in ("__name__", "name"):
        value = getattr(tool, attr, None)
        if value:
            return str(value)
    return str(tool)


def _tool_fingerprint(tool: Any) -> str:
    """Best-effort stable fingerprint of a tool's *provider-visible* schema.

    The serialised tool block sent to the provider is not just the tool name —
    it is the full function schema (name + description + parameters). A change
    to a tool's description, parameters, or required fields *without* a rename
    changes those bytes and therefore invalidates the prompt cache, so the
    fingerprint must reflect the whole schema, not only the name (Issue #3352
    review). Falls back to the name when no richer schema is exposed.
    """
    name = _tool_name(tool)

    # Dict tools already carry an OpenAI-style function schema — fingerprint the
    # description + parameters alongside the name so a same-name schema edit is
    # detected. ``json.dumps(sort_keys=True)`` makes the render deterministic.
    if isinstance(tool, dict):
        fn = tool.get("function")
        schema = fn if isinstance(fn, dict) else tool
        desc = schema.get("description") if isinstance(schema, dict) else None
        params = schema.get("parameters") if isinstance(schema, dict) else None
        try:
            import json

            return "\x01".join(
                (
                    name,
                    str(desc or ""),
                    json.dumps(params or {}, sort_keys=True, default=str),
                )
            )
        except Exception:  # pragma: no cover — defensive
            return name

    # Callable/object tools: fold in the docstring (the description the schema
    # generator emits) so an edited tool doc flips the signature too.
    doc = getattr(tool, "__doc__", None)
    if doc:
        return f"{name}\x01{doc}"
    return name


def prompt_prefix_signature(agent: Any) -> str:
    """Return a sha256 signature of an agent's cache-relevant prompt prefix.

    The signature is computed over, and only over:

    * the model identity (``agent.llm``),
    * the sorted set of tool *schema fingerprints* (name + description +
      parameters, ``agent.tools``) — so a same-name schema edit is detected,
    * a fingerprint of the system instructions (``agent.instructions``).

    Volatile per-turn data is intentionally excluded so that an unchanged
    route/model keeps a byte-identical prefix and the provider cache keeps
    hitting. Callers compare the signature turn-over-turn: an unchanged value
    means the cached prefix is reused; a changed value is the single auditable
    point of prompt-cache invalidation.

    Best-effort and never raises: any attribute access failure degrades the
    corresponding component to an empty string rather than breaking the turn.
    """
    try:
        llm = getattr(agent, "llm", None)
        model = llm if isinstance(llm, str) else getattr(llm, "model", None) or str(llm)
    except Exception:
        model = ""

    try:
        tools = getattr(agent, "tools", None) or []
        tool_fps = sorted(_tool_fingerprint(t) for t in tools)
    except Exception:
        tool_fps = []

    try:
        instructions = getattr(agent, "instructions", None) or ""
        instructions = str(instructions)
    except Exception:
        instructions = ""

    hasher = hashlib.sha256()
    hasher.update(b"model\x00")
    hasher.update(str(model).encode("utf-8", "replace"))
    hasher.update(b"\x00tools\x00")
    hasher.update("\x00".join(tool_fps).encode("utf-8", "replace"))
    hasher.update(b"\x00instructions\x00")
    hasher.update(instructions.encode("utf-8", "replace"))
    return hasher.hexdigest()


__all__ = ["prompt_prefix_signature"]

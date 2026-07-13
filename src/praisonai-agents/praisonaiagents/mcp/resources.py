"""Normalisation helpers for MCP resource and prompt contents.

MCP servers can return resources as text, binary blobs, or embedded resources,
and prompts as a sequence of role-tagged messages. These helpers convert those
raw SDK result objects into plain, agent-consumable strings with size and mime
guards, mirroring how tool results are normalised in ``mcp.py``.
"""

import base64
import json

# Byte cap for inlined resource/blob contents. Larger payloads are summarised
# with their size and mime type instead of being dumped into the context.
MAX_INLINE_BYTES = 100_000


def _truncate(text, limit=MAX_INLINE_BYTES):
    """Return ``text`` truncated to ``limit`` characters with a marker."""
    if text is None:
        return ""
    if len(text) > limit:
        return text[:limit] + f"\n...[truncated, {len(text)} chars total]"
    return text


def _normalize_content_item(item):
    """Normalise a single resource content item into a string."""
    # Text content
    text = getattr(item, "text", None)
    if text is not None:
        return _truncate(text)

    # Binary content: resource blobs use ``blob``; image/audio content blocks
    # use ``data``. Both are base64-encoded strings with a ``mimeType``.
    binary = getattr(item, "blob", None)
    if binary is None:
        binary = getattr(item, "data", None)
    if binary is not None:
        mime = getattr(item, "mimeType", None) or "application/octet-stream"
        try:
            raw = base64.b64decode(binary) if isinstance(binary, str) else binary
            size = len(raw)
        except Exception:
            size = len(binary) if hasattr(binary, "__len__") else 0
        return f"[binary resource: {mime}, {size} bytes]"

    # Embedded resource content wraps a nested resource under ``resource``.
    embedded = getattr(item, "resource", None)
    if embedded is not None:
        return _normalize_content_item(embedded)

    return _truncate(str(item))


def normalize_resource_result(result):
    """Convert a ``read_resource`` result into agent-consumable text.

    Handles the ``contents`` list (text/blob/embedded) returned by the MCP SDK.
    """
    if result is None:
        return ""

    contents = getattr(result, "contents", None)
    if contents:
        parts = [_normalize_content_item(item) for item in contents]
        return "\n\n".join(p for p in parts if p)

    # Fall back to a stringified representation for unexpected shapes.
    return _truncate(str(result))


def normalize_prompt_result(result):
    """Convert a ``get_prompt`` result into agent-consumable text.

    Renders each message as ``<role>: <text>`` and preserves the optional
    prompt description as a header.
    """
    if result is None:
        return ""

    lines = []
    description = getattr(result, "description", None)
    if description:
        lines.append(str(description))

    messages = getattr(result, "messages", None) or []
    for message in messages:
        role = getattr(message, "role", "user")
        content = getattr(message, "content", None)
        text = getattr(content, "text", None)
        if text is not None:
            rendered = _truncate(text)
        elif content is not None:
            # Non-text content (image/audio/blob/embedded resource): reuse the
            # resource content normaliser so binary payloads become size/mime
            # summaries instead of raw object reprs.
            rendered = _normalize_content_item(content)
        else:
            rendered = ""
        lines.append(f"{role}: {rendered}")

    if lines:
        return "\n".join(lines)
    return _truncate(str(result))


def resources_to_dicts(resources):
    """Serialise a list of resource descriptors into JSON-friendly dicts."""
    out = []
    for res in resources or []:
        out.append(
            {
                "uri": str(getattr(res, "uri", "")),
                "name": getattr(res, "name", None),
                "description": getattr(res, "description", None),
                "mimeType": getattr(res, "mimeType", None),
            }
        )
    return out


def resource_templates_to_dicts(templates):
    """Serialise resource templates into JSON-friendly dicts."""
    out = []
    for tmpl in templates or []:
        out.append(
            {
                "uriTemplate": str(getattr(tmpl, "uriTemplate", "")),
                "name": getattr(tmpl, "name", None),
                "description": getattr(tmpl, "description", None),
                "mimeType": getattr(tmpl, "mimeType", None),
            }
        )
    return out


def prompts_to_dicts(prompts):
    """Serialise prompt descriptors (with argument hints) into dicts."""
    out = []
    for prompt in prompts or []:
        arguments = []
        for arg in getattr(prompt, "arguments", None) or []:
            arguments.append(
                {
                    "name": getattr(arg, "name", None),
                    "description": getattr(arg, "description", None),
                    "required": getattr(arg, "required", False),
                }
            )
        out.append(
            {
                "name": getattr(prompt, "name", None),
                "description": getattr(prompt, "description", None),
                "arguments": arguments,
            }
        )
    return out


def to_json(data):
    """Compact, deterministic JSON dump used by the synthetic listing tools."""
    return json.dumps(data, indent=2, default=str)

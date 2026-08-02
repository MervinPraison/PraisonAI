"""Declarative webhook filter — a tiny, import-light matcher for HTTP events.

A generic webhook channel needs to decide, purely from configuration, whether
an inbound HTTP event should trigger an agent. This module provides that
decision as a small, side-effect-free predicate tree so the heavy HTTP-serving
ingress (in ``praisonai-bot``) — and any third-party channel — can reuse one
canonical filter semantics instead of re-implementing payload matching.

The filter is expressed as plain dict/JSON so it round-trips through YAML:

    when:
      all:
        - { field: headers.X-GitHub-Event, equals: issues }
        - { field: payload.action, in: [opened, reopened] }

Grammar
-------
A node is either a *combinator* or a *leaf*.

Combinators (compose sub-nodes)::

    {"all": [<node>, ...]}   # AND — every child must match (empty = True)
    {"any": [<node>, ...]}   # OR  — at least one child matches (empty = False)
    {"not": <node>}          # negation

Leaf (a single field test)::

    {"field": "payload.action", "<op>": <value>}

where ``<op>`` is one of:

- ``exists``  — truthy check the field is present (value: bool, default True)
- ``equals``  — equality (string-insensitive for headers is *not* implied;
                 compares the resolved value to ``value``)
- ``contains``— substring / membership (``value in resolved``)
- ``in``      — resolved value is one of ``value`` (a list)
- ``regex``   — ``re.search(value, str(resolved))``

``field`` is a dotted path into the event mapping, e.g. ``payload.issue.number``
or ``headers.X-GitHub-Event``. Header lookup is case-insensitive. A missing path
resolves to ``None`` and simply fails the leaf (fail-safe), it never raises.

This module has no third-party imports and does not perform any I/O, so it is
safe to keep in the core SDK; the wrapper composes it with HMAC verification and
the ingress journal.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

__all__ = ["WebhookFilter", "evaluate_webhook_filter", "resolve_field"]


def resolve_field(event: Mapping[str, Any], path: str) -> Any:
    """Resolve a dotted ``path`` into ``event``, case-insensitively for headers.

    Args:
        event: The normalised event mapping, typically
            ``{"payload": ..., "headers": ..., "query": ...}``.
        path: A dotted path like ``payload.issue.number`` or
            ``headers.X-GitHub-Event``.

    Returns:
        The resolved value, or ``None`` if any segment is missing. Never raises.
    """
    if not path:
        return None
    parts = path.split(".")
    current: Any = event
    header_section = parts[0] == "headers"
    for i, part in enumerate(parts):
        if isinstance(current, Mapping):
            if part in current:
                current = current[part]
                continue
            # Headers are case-insensitive: fall back to a lowered-key match for
            # the segment directly under ``headers``.
            if header_section and i == 1:
                lowered = {str(k).lower(): v for k, v in current.items()}
                if part.lower() in lowered:
                    current = lowered[part.lower()]
                    continue
            return None
        return None
    return current


def _match_leaf(event: Mapping[str, Any], node: Mapping[str, Any]) -> bool:
    """Evaluate a single ``{"field": ..., "<op>": value}`` leaf. Fail-safe."""
    field = node.get("field")
    if not isinstance(field, str):
        return False
    resolved = resolve_field(event, field)

    if "exists" in node:
        want = node["exists"]
        present = resolved is not None
        return present if bool(want) else (not present)

    if "equals" in node:
        return resolved == node["equals"]

    if "contains" in node:
        needle = node["contains"]
        try:
            return needle in resolved  # type: ignore[operator]
        except TypeError:
            return False

    if "in" in node:
        options = node["in"]
        if isinstance(options, (list, tuple, set)):
            return resolved in options
        return False

    if "regex" in node:
        pattern = node["regex"]
        if not isinstance(pattern, str) or resolved is None:
            return False
        try:
            return re.search(pattern, str(resolved)) is not None
        except re.error:
            return False

    # A leaf with only ``field`` and no operator is treated as an existence
    # check — matches when the field is present.
    return resolved is not None


def evaluate_webhook_filter(
    event: Mapping[str, Any], node: Optional[Any]
) -> bool:
    """Evaluate a declarative filter ``node`` against a normalised ``event``.

    Args:
        event: Normalised event, e.g. ``{"payload", "headers", "query"}``.
        node: The filter tree (dict). ``None`` or ``{}`` matches everything so a
            route with no ``when`` is an unconditional catch-all.

    Returns:
        True if the event matches. Never raises on malformed input — an
        unrecognised node fails closed to ``False`` (except the empty/None
        catch-all above).
    """
    if node is None or node == {}:
        return True
    if not isinstance(node, Mapping):
        return False

    if "all" in node:
        children = node["all"] or []
        return all(evaluate_webhook_filter(event, c) for c in children)
    if "any" in node:
        children = node["any"] or []
        return any(evaluate_webhook_filter(event, c) for c in children)
    if "not" in node:
        return not evaluate_webhook_filter(event, node["not"])

    if "field" in node:
        return _match_leaf(event, node)

    return False


class WebhookFilter:
    """A reusable, config-driven predicate over a normalised webhook event.

    Wraps a declarative filter tree so callers can validate it once and match
    many events::

        f = WebhookFilter({"all": [
            {"field": "headers.X-GitHub-Event", "equals": "issues"},
            {"field": "payload.action", "in": ["opened", "reopened"]},
        ]})
        if f.matches({"headers": {...}, "payload": {...}}):
            ...

    A ``None``/empty tree is an unconditional match (catch-all route).
    """

    __slots__ = ("_tree",)

    def __init__(self, tree: Optional[Any] = None) -> None:
        self._tree = tree

    @property
    def tree(self) -> Optional[Any]:
        return self._tree

    def matches(self, event: Mapping[str, Any]) -> bool:
        """Return whether ``event`` satisfies the filter tree."""
        return evaluate_webhook_filter(event, self._tree)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"WebhookFilter({self._tree!r})"

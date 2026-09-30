"""Canonical session-address grammar for the Gateway (Issue #5383).

A pure, dependency-free grammar that maps between an opaque runtime
``session_key`` (a UUID, or an ``agent:<id>:<uuid>``-style key) and a stable,
human-readable, reconnect-survivable path — e.g. ``chat/<agentId>/<slug>-<shortId>``.
It gives every surface (dashboard deep-links, bot channels, the CLI, the
``praisonai-ts`` mirror, reconnecting clients) a single addressing contract to
agree on, instead of each one carrying the raw UUID or re-inventing a resolver.

This module lives in **core** because the grammar is a set of pure functions
that define a protocol/contract every surface must share. It has **no**
third-party dependencies and does no I/O — the concrete store-backed lookup
(``session.resolve``) is implemented in the wrapper behind this contract.

The grammar is deliberately lossy in one direction: ``build_session_path``
derives a short id from the trailing UUID so the whole opaque instance id never
appears in a URL, and an optional slug from the session label. ``parse_session_path``
recovers a :class:`SessionRef` (agent id + short id + slug hint) that a resolver
maps back to the concrete ``session_id``; it never assumes it can reconstruct the
key byte-for-byte, except via the exact-key escape hatch (a ``!``-prefixed final
segment) for sessions that must keep their literal key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, unquote

__all__ = [
    "SessionRef",
    "SHORT_ID_LEN",
    "RESERVED_NAMES",
    "derive_short_id",
    "slugify",
    "build_session_path",
    "parse_session_path",
]

# Length of the short id derived from the trailing hex of a session key. Eight
# hex chars (32 bits) keeps URLs terse while staying collision-resistant enough
# for a per-agent namespace, where a resolver disambiguates the rare clash.
SHORT_ID_LEN = 8

# Reserved final-segment names that denote a well-known / sentinel session
# (e.g. the agent's ``main`` conversation) rather than a ``slug-shortId`` pair.
# A resolver treats these as a friendly sentinel, not a short-id lookup.
RESERVED_NAMES = frozenset({"main", "global", "default", "root"})

# Trailing run of hex digits in a key — the opaque UUID tail we shorten from.
_HEX_TAIL_RE = re.compile(r"([0-9a-fA-F]{%d,})[^0-9a-fA-F]*$" % SHORT_ID_LEN)

# A ``slug-shortId`` final segment: optional slug, then a hex short id.
_SLUG_SHORT_RE = re.compile(r"^(?:(?P<slug>.+)-)?(?P<short>[0-9a-fA-F]{%d})$" % SHORT_ID_LEN)

# Characters allowed verbatim in a slug; everything else collapses to ``-``.
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")

# Exact-key escape hatch: a final segment prefixed with ``!`` carries the
# percent-encoded literal key verbatim (for sessions that must not be shortened).
_LITERAL_PREFIX = "!"


@dataclass(frozen=True)
class SessionRef:
    """A parsed friendly reference to a session, for a resolver to map to an id.

    Exactly one of the resolution hints is authoritative depending on how the
    path was written:

    - ``literal_key`` set  -> resolve by exact key (escape hatch).
    - ``short_id`` set     -> resolve by short id (optionally aided by ``slug_hint``).
    - ``slug_hint`` only, matching a reserved name -> resolve the sentinel session.

    ``agent_id`` scopes the lookup so short ids only need to be unique per agent.
    """

    agent_id: str
    short_id: Optional[str] = None
    slug_hint: Optional[str] = None
    literal_key: Optional[str] = None


def derive_short_id(session_key: str) -> Optional[str]:
    """Derive a stable short id from the trailing hex of ``session_key``.

    Returns the last :data:`SHORT_ID_LEN` hex chars of the key's trailing hex
    run (e.g. the UUID tail), lower-cased. Returns ``None`` when the key has no
    hex tail long enough to shorten — the caller then falls back to the literal
    key or reserved-name form.
    """
    if not session_key:
        return None
    match = _HEX_TAIL_RE.search(session_key)
    if not match:
        return None
    hex_tail = match.group(1)
    return hex_tail[-SHORT_ID_LEN:].lower()


def slugify(display_name: Optional[str], max_len: int = 48) -> Optional[str]:
    """Turn a human label into a lowercase, dash-separated URL slug.

    Non-alphanumeric runs collapse to a single ``-``; leading/trailing dashes are
    trimmed. Returns ``None`` for an empty/whitespace-only or unusable name so
    the path omits the slug rather than emitting an empty segment.
    """
    if not display_name:
        return None
    slug = _SLUG_STRIP_RE.sub("-", display_name.strip().lower()).strip("-")
    if not slug:
        return None
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or None


def build_session_path(
    agent_id: str,
    session_key: str,
    display_name: Optional[str] = None,
    namespace: str = "chat",
) -> Optional[str]:
    """Build a stable, shareable path for a session.

    Produces ``<namespace>/<agentId>/<slug>-<shortId>`` when a short id can be
    derived (with the slug omitted when there is no usable ``display_name``), so
    the whole opaque UUID never appears in the URL. When the key has no hex tail
    to shorten, falls back to an exact-key segment (``!<percent-encoded-key>``)
    so the address round-trips losslessly. Returns ``None`` if ``agent_id`` or
    ``session_key`` is empty.

    Path segments are percent-escaped, so a key that looks like a file
    (e.g. ``report.js``) is never mistaken for a static asset.
    """
    if not agent_id or not session_key:
        return None
    ns = _seg(namespace) or "chat"
    agent_seg = _seg(agent_id)
    if not agent_seg:
        return None

    short_id = derive_short_id(session_key)
    if short_id:
        slug = slugify(display_name)
        tail = f"{slug}-{short_id}" if slug else short_id
    else:
        # No hex tail to shorten: keep the literal key behind the escape hatch.
        tail = _LITERAL_PREFIX + quote(session_key, safe="")
    return f"{ns}/{agent_seg}/{tail}"


def parse_session_path(path: str) -> Optional[SessionRef]:
    """Parse a session path back into a :class:`SessionRef`.

    Accepts the forms produced by :func:`build_session_path`, with or without a
    leading namespace segment:

    - ``chat/<agent>/<slug>-<shortId>`` / ``<agent>/<slug>-<shortId>``
    - ``chat/<agent>/<shortId>`` / ``<agent>/<shortId>``
    - ``chat/<agent>/main`` (reserved sentinel) / ``<agent>/main``
    - ``chat/<agent>/!<percent-encoded-key>`` (exact-key escape hatch)

    Returns ``None`` when the path has no agent segment or is otherwise
    unparseable. A resolver combines the returned hints with its store to reach
    the concrete ``session_id``.
    """
    if not path:
        return None
    parts = [p for p in path.strip().strip("/").split("/") if p]
    if len(parts) >= 3:
        # Drop a leading namespace segment; agent + final ref remain.
        agent_id = unquote(parts[-2])
        final = parts[-1]
    elif len(parts) == 2:
        agent_id = unquote(parts[0])
        final = parts[1]
    else:
        return None

    agent_id = agent_id.strip()
    if not agent_id or not final:
        return None

    # Exact-key escape hatch.
    if final.startswith(_LITERAL_PREFIX):
        literal = unquote(final[len(_LITERAL_PREFIX):])
        if not literal:
            return None
        return SessionRef(agent_id=agent_id, literal_key=literal)

    final = unquote(final)

    # Reserved sentinel (main/global/...): a friendly named session.
    if final.lower() in RESERVED_NAMES:
        return SessionRef(agent_id=agent_id, slug_hint=final.lower())

    match = _SLUG_SHORT_RE.match(final)
    if match:
        return SessionRef(
            agent_id=agent_id,
            short_id=match.group("short").lower(),
            slug_hint=match.group("slug") or None,
        )

    # No short id present: treat the whole segment as a slug hint the resolver
    # can match against session labels.
    return SessionRef(agent_id=agent_id, slug_hint=final)


def _seg(value: Optional[str]) -> str:
    """Percent-escape a single path segment (``/`` and dots are encoded)."""
    if not value:
        return ""
    return quote(value.strip(), safe="")

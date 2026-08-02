"""Shared tool-source resolution helpers (internal).

Single owner for the small presentation-layer helper that ``cli/features/tools.py``,
``templates/tools_doctor.py`` and ``templates/dependency_checker.py`` each used to
reimplement independently:

- build a guarded :class:`ToolResolver`,
- bucket its ``list_available_sources()`` by source, and
- fall back to a ``TOOL_MAPPINGS`` + ``praisonai_tools`` scan.

The canonical resolver (``praisonai_code.tool_resolver.ToolResolver``, re-exported via
``praisonai.tool_resolver``) remains the sole owner of resolution itself — this module
only centralises the thin, previously-triplicated wrapper around it so a change to
bucketing or to the built-in/external fallback lives in one place.
"""

from typing import Any, Dict, List, Optional


def get_resolver() -> Optional[Any]:
    """Lazily construct the canonical ToolResolver (None if unavailable)."""
    try:
        from praisonai.tool_resolver import ToolResolver
        return ToolResolver()
    except Exception:
        return None


def resolver_source_buckets(resolver: Optional[Any] = None) -> Dict[str, List[str]]:
    """Group the resolver's discovered tools by their source bucket.

    Buckets mirror :meth:`ToolResolver.list_available_sources` values
    (``local`` / ``builtin`` / ``external`` / ``registered``). Returns an
    empty mapping when the resolver is unavailable or the scan fails so
    callers can fall back to their legacy per-source listing.

    Args:
        resolver: Optional pre-built resolver; constructed lazily when omitted.
    """
    if resolver is None:
        resolver = get_resolver()
    buckets: Dict[str, List[str]] = {}
    if resolver is not None:
        try:
            for name, src in resolver.list_available_sources().items():
                buckets.setdefault(src, []).append(name)
        except Exception:
            buckets = {}
    return buckets


def resolver_source_map(resolver: Optional[Any] = None) -> Dict[str, str]:
    """Return the resolver's raw ``{tool_name: source}`` map.

    Returns an empty mapping when the resolver is unavailable or the scan
    fails.

    Args:
        resolver: Optional pre-built resolver; constructed lazily when omitted.
    """
    if resolver is None:
        resolver = get_resolver()
    if resolver is None:
        return {}
    try:
        return dict(resolver.list_available_sources())
    except Exception:
        return {}


def builtin_tool_names() -> List[str]:
    """Fallback ``praisonaiagents.tools.TOOL_MAPPINGS`` scan (built-in tools).

    Returns an empty list when praisonaiagents is unavailable.
    """
    try:
        from praisonaiagents.tools import TOOL_MAPPINGS
        return list(TOOL_MAPPINGS.keys())
    except ImportError:
        return []


def external_tool_names() -> List[str]:
    """Fallback ``praisonai_tools`` scan (external tools).

    Returns an empty list when praisonai-tools is unavailable.
    """
    tools: List[str] = []
    try:
        import praisonai_tools
        for name in dir(praisonai_tools):
            if not name.startswith("_"):
                obj = getattr(praisonai_tools, name, None)
                if callable(obj):
                    tools.append(name)
    except ImportError:
        pass
    return tools

"""Small helpers shared by ``llm.py``, ``openai_client.py`` and ``agent/tool_execution.py``.

Each had its own copy (G-30); this keeps one. Stdlib only, so importing it is free.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def inject_steering(msgs: List[Dict[str, Any]], steering_drain: Optional[Callable[[], Any]]) -> None:
    """Append queued steering notes as user messages; a failing drain is ignored."""
    if steering_drain is None:
        return
    try:
        for note in (steering_drain() or []):
            if note:
                msgs.append({"role": "user", "content": f"[steering] {note}"})
    except Exception as err:  # noqa: BLE001 - steering must never break a turn
        logger.debug("Steering drain failed (ignored): %s", err)


def usage_value(usage: Any, *names: str) -> int:
    """First non-None token count under any of *names*, from a dict or an object."""
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value is not None:
            return int(value or 0)
    return 0


def usage_detail(usage: Any, detail_names: tuple, name: str) -> int:
    """*name* inside the first present ``*_tokens_details`` block, from a dict or an object."""
    for detail_name in detail_names:
        details = usage.get(detail_name) if isinstance(usage, dict) else getattr(usage, detail_name, None)
        if details:
            value = details.get(name) if isinstance(details, dict) else getattr(details, name, None)
            if value is not None:
                return int(value or 0)
    return 0

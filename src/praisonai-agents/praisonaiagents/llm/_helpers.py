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

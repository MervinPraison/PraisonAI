"""Outbound delivery mirror for bot sessions.

W1 — When a bot pushes a message via ``Bot.send_message()`` (notifications,
scheduled deliveries, cross-platform replies), this module appends an
``{"role": "assistant", "mirror": True}`` entry to the user's session
so the next inbound turn carries that context.

Standalone helper — designed to be safe to call from any context (sync
handler, async coroutine, cron job, scheduled delivery). Errors are
swallowed and logged: a mirror failure must never break the outbound
delivery itself.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Global lock to protect mirror operations from racing with chat() calls
# This is a simple solution since mirror_to_session is designed for
# relatively infrequent use (scheduled deliveries, cross-platform replies)
_mirror_lock = threading.RLock()


def mirror_to_session(
    session_mgr: Any,
    user_id: str,
    message_text: str,
    source_label: str = "delivery",
    metadata: Optional[dict] = None,
) -> bool:
    """Append a mirror entry to ``user_id``'s session history.

    Parameters
    ----------
    session_mgr
        A ``BotSessionManager``-shaped object that exposes
        ``_storage_key(user_id)``, ``_load_history(user_id)``, and
        ``_save_history(user_id, history)``. Any object with these three
        methods is acceptable (duck-typed, no Protocol required).
    user_id
        Raw platform user id. Will be passed through the manager's
        identity resolver if one is configured.
    message_text
        The outbound message text to mirror.
    source_label
        Free-form tag identifying the source of the delivery
        (e.g. ``"cron"``, ``"web"``, ``"cross_platform"``).
    metadata
        Optional extra metadata to merge into the mirror entry.

    Returns
    -------
    bool
        ``True`` on success, ``False`` if anything went wrong. Errors
        are logged at WARN level and never raised.
    """
    if not message_text:
        return False

    try:
        # Verify that session_mgr is a compatible BotSessionManager-shaped
        # object by probing its _storage_key method (duck-typing check).
        session_mgr._storage_key(user_id)
    except Exception as e:
        logger.warning("mirror: storage_key failed: %s", e)
        return False

    # Check if the session manager has a thread-safe mirror method
    # This allows the session manager to handle synchronization properly
    # with its internal asyncio locks.
    if hasattr(session_mgr, '_add_mirror_entry_sync'):
        try:
            entry: dict = {
                "role": "assistant",
                "content": message_text,
                "timestamp": datetime.now().isoformat(),
                "mirror": True,
                "mirror_source": source_label,
            }
            if metadata:
                entry.update(metadata)
            
            return session_mgr._add_mirror_entry_sync(user_id, entry)
        except Exception as e:
            logger.warning("mirror: _add_mirror_entry_sync failed: %s", e)
            return False
    
    # Fallback: Use global lock to prevent race conditions between mirror operations
    # and concurrent chat() calls. This provides basic protection but is not ideal.
    logger.warning(
        "mirror_to_session using fallback synchronization - "
        "session manager should implement _add_mirror_entry_sync for better safety"
    )
    with _mirror_lock:
        try:
            # Load current history
            history = list(session_mgr._load_history(user_id))
            
            # Create mirror entry
            entry: dict = {
                "role": "assistant",
                "content": message_text,
                "timestamp": datetime.now().isoformat(),
                "mirror": True,
                "mirror_source": source_label,
            }
            if metadata:
                entry.update(metadata)
            history.append(entry)
            
            # Save updated history atomically within the lock
            session_mgr._save_history(user_id, history)
            
        except Exception as e:
            logger.warning("mirror: save_history failed: %s", e)
            return False

    return True


__all__ = ["mirror_to_session"]

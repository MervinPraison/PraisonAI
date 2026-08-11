"""
Shared conversation-store operations.

Single owner for the *create-or-resume session* flow over a
``ConversationStore``. Both ``PraisonAIDB`` (``db/adapter.py``) and
``PersistenceOrchestrator`` (``persistence/orchestrator.py``) call these helpers
so the store-level session semantics live in one place instead of being copied
across the sync/async surfaces of both classes.

The helpers only touch the store (``get_session`` / ``create_session`` /
``get_messages``); each caller keeps its own return-type contract, caching, and
lock/cooldown machinery by wrapping the result.
"""

from typing import Any, Awaitable, Callable, List, Optional

from .base import ConversationSession, ConversationMessage


def resume_or_create_session(
    store: Any,
    session: Optional[ConversationSession],
    session_id: str,
    build_session: Callable[[], ConversationSession],
    get_messages: Callable[[], List[ConversationMessage]],
    create_session: Optional[Callable[[ConversationSession], Any]] = None,
) -> Optional[List[ConversationMessage]]:
    """Create the session if missing, else return its messages (sync).

    Args:
        store: The conversation store.
        session: Result of the caller's ``get_session`` lookup (``None`` when
            the session does not yet exist).
        session_id: The session identifier (unused directly; kept for parity
            and readability at call sites).
        build_session: Factory returning the ``ConversationSession`` to create
            when ``session`` is ``None`` — lets each caller keep its own name/
            metadata conventions.
        get_messages: Callable returning the existing messages when resuming.
        create_session: Optional callable used to persist the built session.
            Defaults to ``store.create_session``. Callers wired to an
            ``AsyncConversationStore`` MUST pass a dispatcher (e.g. one that runs
            the returned coroutine to completion), otherwise the bare
            ``store.create_session`` returns an un-awaited coroutine that is
            silently dropped and the session row is never written.

    Returns:
        ``None`` when a new session was created (no history), otherwise the list
        of previously persisted messages.
    """
    if session is None:
        target = create_session if create_session is not None else store.create_session
        target(build_session())
        return None
    return get_messages()


async def aresume_or_create_session(
    store: Any,
    session: Optional[ConversationSession],
    session_id: str,
    build_session: Callable[[], ConversationSession],
    create_session: Callable[[ConversationSession], Awaitable[Any]],
    get_messages: Callable[[], Awaitable[List[ConversationMessage]]],
) -> Optional[List[ConversationMessage]]:
    """Async variant of :func:`resume_or_create_session`.

    ``create_session`` and ``get_messages`` are awaitables supplied by the
    caller so each keeps its own async-dispatch discipline (dedicated async
    method vs. ``asyncio.to_thread`` off-loading).
    """
    if session is None:
        await create_session(build_session())
        return None
    return await get_messages()

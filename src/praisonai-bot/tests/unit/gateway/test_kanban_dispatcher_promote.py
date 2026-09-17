"""Unit tests for kanban dispatcher dependency promotion tick."""

from praisonai_bot.gateway.kanban_dispatcher import KanbanDispatcher


class _FakeTask:
    def __init__(self, task_id, status="ready"):
        self.id = task_id
        self.status = status

    def to_dict(self):
        return {"id": self.id, "status": self.status}


class _FakeStore:
    def __init__(self, promoted):
        self._promoted = list(promoted)
        self.recompute_calls = 0

    def recompute_ready(self):
        self.recompute_calls += 1
        return list(self._promoted)

    def get_task(self, task_id):
        return _FakeTask(task_id, status="ready")


def test_promote_ready_fires_moved_event():
    """_promote_ready calls store.recompute_ready and fires move events."""
    dispatcher = KanbanDispatcher()
    store = _FakeStore(promoted=["t_child"])

    fired = []
    dispatcher._fire_hook_event = lambda event_type, data: fired.append((event_type, data))

    promoted = dispatcher._promote_ready(store)

    assert promoted == ["t_child"]
    assert store.recompute_calls == 1
    assert len(fired) == 1
    event_type, data = fired[0]
    assert event_type == "kanban_task_moved"
    assert data["task_id"] == "t_child"
    assert data["to_status"] == "ready"
    assert data["task"] == {"id": "t_child", "status": "ready"}


def test_promote_ready_skips_event_when_task_unreadable():
    """A promoted task that can't be read back fires no (empty) move event."""
    dispatcher = KanbanDispatcher()

    class _UnreadableStore(_FakeStore):
        def get_task(self, task_id):
            return None

    store = _UnreadableStore(promoted=["t_child"])

    fired = []
    dispatcher._fire_hook_event = lambda event_type, data: fired.append((event_type, data))

    promoted = dispatcher._promote_ready(store)

    assert promoted == ["t_child"]
    assert fired == []


def test_promote_ready_no_promotions_no_events():
    """No promotions => no events fired."""
    dispatcher = KanbanDispatcher()
    store = _FakeStore(promoted=[])

    fired = []
    dispatcher._fire_hook_event = lambda event_type, data: fired.append((event_type, data))

    promoted = dispatcher._promote_ready(store)

    assert promoted == []
    assert fired == []


def test_promote_ready_handles_missing_method():
    """Stores without recompute_ready degrade gracefully."""
    dispatcher = KanbanDispatcher()

    class _NoPromote:
        pass

    fired = []
    dispatcher._fire_hook_event = lambda event_type, data: fired.append((event_type, data))

    assert dispatcher._promote_ready(_NoPromote()) == []
    assert fired == []


def test_promote_ready_reaches_a_real_hook_subscriber():
    """The dispatcher's emission must land on a genuinely registered hook.

    ``_fire_hook_event`` imported a ``fire_hook`` symbol that did not exist,
    so every dispatcher event died in an ``except ImportError: log.debug``.
    Use the real emitter (no monkeypatching) against the real registry.
    """
    from praisonaiagents.hooks.registry import (
        HookRegistry,
        add_hook,
        get_default_registry,
        set_default_registry,
    )
    from praisonaiagents.hooks.types import HookEvent, HookResult

    previous = get_default_registry()
    set_default_registry(HookRegistry())
    try:
        seen = []
        add_hook(
            HookEvent.KANBAN_TASK_MOVED,
            lambda data: seen.append(data.to_dict()) or HookResult.allow(),
        )

        dispatcher = KanbanDispatcher()
        assert dispatcher._promote_ready(_FakeStore(promoted=["t_child"])) == ["t_child"]

        assert len(seen) == 1, "dispatcher promotion never reached a KANBAN_TASK_MOVED hook"
        assert seen[0]["task_id"] == "t_child"
        assert seen[0]["to_status"] == "ready"
        assert seen[0]["event_name"] == "kanban_task_moved"
    finally:
        set_default_registry(previous)

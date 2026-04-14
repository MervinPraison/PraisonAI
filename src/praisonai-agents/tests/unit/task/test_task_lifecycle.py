"""Tests for Task Lifecycle State Machine (Gap 1).

Validates:
- TaskStatus enum values and string compatibility
- Valid state transitions
- Invalid state transitions raise errors
- EventBus integration on transitions
- Backward compatibility with raw string status
"""
import pytest


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_enum_values(self):
        from praisonaiagents.task.protocols import TaskStatus
        assert TaskStatus.NOT_STARTED == "not started"
        assert TaskStatus.IN_PROGRESS == "in progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"

    def test_string_equality(self):
        """TaskStatus must compare equal to raw strings for backward compat."""
        from praisonaiagents.task.protocols import TaskStatus
        assert TaskStatus.NOT_STARTED == "not started"
        assert "not started" == TaskStatus.NOT_STARTED
        assert TaskStatus.COMPLETED == "completed"

    def test_str_representation(self):
        from praisonaiagents.task.protocols import TaskStatus
        assert str(TaskStatus.NOT_STARTED) == "not started"
        assert str(TaskStatus.IN_PROGRESS) == "in progress"


class TestTaskLifecycleManager:
    """Test TaskLifecycleManager transition validation."""

    def test_valid_transitions(self):
        from praisonaiagents.task.protocols import TaskLifecycleManager, TaskStatus
        mgr = TaskLifecycleManager()
        # not started -> in progress
        assert mgr.can_transition(TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS)
        # not started -> cancelled
        assert mgr.can_transition(TaskStatus.NOT_STARTED, TaskStatus.CANCELLED)
        # in progress -> completed
        assert mgr.can_transition(TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED)
        # in progress -> failed
        assert mgr.can_transition(TaskStatus.IN_PROGRESS, TaskStatus.FAILED)
        # in progress -> cancelled
        assert mgr.can_transition(TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED)
        # failed -> in progress (retry)
        assert mgr.can_transition(TaskStatus.FAILED, TaskStatus.IN_PROGRESS)
        # not started -> failed (import error etc)
        assert mgr.can_transition(TaskStatus.NOT_STARTED, TaskStatus.FAILED)

    def test_invalid_transitions(self):
        from praisonaiagents.task.protocols import TaskLifecycleManager, TaskStatus
        mgr = TaskLifecycleManager()
        # completed -> in progress (can't resume completed)
        assert not mgr.can_transition(TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS)
        # cancelled -> in progress
        assert not mgr.can_transition(TaskStatus.CANCELLED, TaskStatus.IN_PROGRESS)
        # completed -> failed
        assert not mgr.can_transition(TaskStatus.COMPLETED, TaskStatus.FAILED)

    def test_transition_executes(self):
        from praisonaiagents.task.protocols import TaskLifecycleManager, TaskStatus
        mgr = TaskLifecycleManager()
        new_status = mgr.transition(TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS)
        assert new_status == TaskStatus.IN_PROGRESS

    def test_invalid_transition_raises(self):
        from praisonaiagents.task.protocols import TaskLifecycleManager, TaskStatus, InvalidTransitionError
        mgr = TaskLifecycleManager()
        with pytest.raises(InvalidTransitionError):
            mgr.transition(TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS)

    def test_transition_callback(self):
        """Callback fires on valid transition."""
        from praisonaiagents.task.protocols import TaskLifecycleManager, TaskStatus
        events = []
        def on_transition(old, new, task_id):
            events.append((old, new, task_id))
        mgr = TaskLifecycleManager(on_transition=on_transition)
        mgr.transition(TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS, task_id="t1")
        assert len(events) == 1
        assert events[0] == (TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS, "t1")


class TestTaskStatusIntegration:
    """Test that Task class uses lifecycle manager."""

    def test_task_initial_status(self):
        from praisonaiagents.task.task import Task
        from praisonaiagents.task.protocols import TaskStatus
        t = Task(description="Test task")
        assert t.status == TaskStatus.NOT_STARTED
        assert t.status == "not started"  # backward compat

    def test_task_set_status_valid(self):
        from praisonaiagents.task.task import Task
        from praisonaiagents.task.protocols import TaskStatus
        t = Task(description="Test task")
        t.set_status(TaskStatus.IN_PROGRESS)
        assert t.status == TaskStatus.IN_PROGRESS

    def test_task_set_status_with_string(self):
        """Backward compat: can set status with raw strings."""
        from praisonaiagents.task.task import Task
        t = Task(description="Test task")
        t.set_status("in progress")
        assert t.status == "in progress"

    def test_task_invalid_transition_still_sets(self):
        """Invalid transitions log warning but don't crash (backward compat)."""
        from praisonaiagents.task.task import Task
        t = Task(description="Test task")
        t.set_status("completed")  # not started -> completed is VALID via in_progress
        # Force to completed state
        t.status = "completed"
        # Now try completed -> in progress (invalid)
        # Should still set for backward compat (logs warning internally)
        t.set_status("in progress")
        assert t.status == "in progress"

    def test_task_direct_assignment_still_works(self):
        """Direct task.status = 'x' still works for backward compat."""
        from praisonaiagents.task.task import Task
        t = Task(description="Test task")
        t.status = "in progress"
        assert t.status == "in progress"

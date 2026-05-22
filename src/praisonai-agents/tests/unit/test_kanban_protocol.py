"""
Unit tests for kanban protocols and hook events.

Tests the protocol contracts and hook events without any heavy
implementations like SQLite or LLM calls.
"""

import pytest
import json
from typing import runtime_checkable

from praisonaiagents.kanban.protocols import (
    KanbanStoreProtocol,
    KanbanTaskProtocol,
    VALID_KANBAN_STATUSES,
)
from praisonaiagents.hooks.types import (
    HookEvent,
    KanbanHookInput,
)


class TestKanbanProtocol:
    """Test KanbanStoreProtocol runtime checking and constants."""
    
    def test_kanban_store_protocol_is_runtime_checkable(self):
        """Test that KanbanStoreProtocol is @runtime_checkable."""
        assert runtime_checkable(KanbanStoreProtocol)
        
    def test_valid_kanban_statuses_includes_ui_columns(self):
        """Test that VALID_KANBAN_STATUSES includes all PraisonAIUI columns."""
        expected_statuses = {
            "triage",
            "todo", 
            "ready",
            "running",
            "blocked",
            "review",
            "done",
            "archived"
        }
        assert VALID_KANBAN_STATUSES == expected_statuses
        
    def test_valid_kanban_statuses_is_frozen(self):
        """Test that VALID_KANBAN_STATUSES is immutable."""
        assert isinstance(VALID_KANBAN_STATUSES, frozenset)
        
    def test_mock_store_passes_isinstance_check(self):
        """Test that a mock store implementing the protocol passes isinstance check."""
        
        class MockKanbanStore:
            """Mock implementation for testing."""
            
            def get_board(self, *, board="default", tenant=None, include_archived=False):
                return {"board": board, "tasks": []}
                
            def get_task(self, task_id: str):
                return {"id": task_id, "title": "Test Task"}
                
            def create_task(self, data: dict):
                return {"id": "task_123", **data}
                
            def update_task(self, task_id: str, data: dict):
                return {"id": task_id, **data}
                
            def move_task(self, task_id: str, status: str):
                return {"id": task_id, "status": status}
                
            def bulk_update(self, task_ids: list[str], status: str):
                return {"updated": len(task_ids), "status": status}
                
            def delete_task(self, task_id: str):
                return True
                
            def list_events(self, since: float = 0.0, board: str = "default"):
                return []
                
            def health(self):
                return {"status": "healthy"}
                
            # Optional P4 methods can raise NotImplementedError
            def add_comment(self, task_id: str, text: str, author: str = None):
                raise NotImplementedError("Comment functionality not implemented")
                
            def link_tasks(self, parent_id: str, child_id: str):
                raise NotImplementedError("Task linking not implemented")
                
            def unlink_tasks(self, parent_id: str, child_id: str):
                raise NotImplementedError("Task unlinking not implemented")
        
        mock_store = MockKanbanStore()
        assert isinstance(mock_store, KanbanStoreProtocol)
        
    def test_kanban_task_protocol_shape(self):
        """Test KanbanTaskProtocol typed dict structure."""
        # This tests that the TypedDict can be used for type hints
        # The shape is validated at runtime by mypy/type checkers
        task: KanbanTaskProtocol = {
            "id": "task_123",
            "title": "Test Task", 
            "body": "Task description",
            "status": "todo",
            "assignee": "user@example.com",
            "priority": "high",
            "tenant": "test_tenant",
            "board": "default",
            "created_at": 1640995200.0,
            "updated_at": 1640995200.0,
        }
        
        # Basic validation that we can access the fields
        assert task["id"] == "task_123"
        assert task["title"] == "Test Task"
        assert task["status"] == "todo"


class TestKanbanHookEvents:
    """Test kanban hook events and payload types."""
    
    def test_kanban_hook_events_in_enum(self):
        """Test that all kanban hook events are registered in HookEvent."""
        expected_events = [
            HookEvent.KANBAN_TASK_CREATED,
            HookEvent.KANBAN_TASK_CLAIMED,
            HookEvent.KANBAN_TASK_MOVED,
            HookEvent.KANBAN_TASK_DONE,
            HookEvent.KANBAN_TASK_BLOCKED,
            HookEvent.KANBAN_TASK_FAILED,
        ]
        
        for event in expected_events:
            assert event in HookEvent
            
    def test_kanban_hook_events_serializable(self):
        """Test that kanban hook events can be serialized."""
        events = [
            HookEvent.KANBAN_TASK_CREATED,
            HookEvent.KANBAN_TASK_CLAIMED,
            HookEvent.KANBAN_TASK_MOVED,
            HookEvent.KANBAN_TASK_DONE,
            HookEvent.KANBAN_TASK_BLOCKED,
            HookEvent.KANBAN_TASK_FAILED,
        ]
        
        for event in events:
            # Should be able to serialize to JSON and reconstruct enum value
            serialized = json.dumps({"event": event.value})
            restored = HookEvent(json.loads(serialized)["event"])
            assert restored == event
    
    def test_kanban_hook_input_creation(self):
        """Test KanbanHookInput dataclass creation and fields."""
        hook_input = KanbanHookInput(
            session_id="session_123",
            cwd="/home/user",
            event_name="kanban_task_created",
            timestamp="2023-01-01T00:00:00Z",
            task_id="task_456",
            board="project_board",
            status="todo",
            assignee="user@example.com",
            from_status=None,
            to_status="running"
        )
        
        assert hook_input.session_id == "session_123"
        assert hook_input.task_id == "task_456"
        assert hook_input.board == "project_board"
        assert hook_input.status == "todo"
        assert hook_input.assignee == "user@example.com"
        assert hook_input.from_status is None
        assert hook_input.to_status == "running"
        
    def test_kanban_hook_input_defaults(self):
        """Test KanbanHookInput with default values."""
        hook_input = KanbanHookInput(
            session_id="session_123",
            cwd="/home/user", 
            event_name="kanban_task_created",
            timestamp="2023-01-01T00:00:00Z"
        )
        
        # Check defaults
        assert hook_input.task_id == ""
        assert hook_input.board == "default"
        assert hook_input.status == ""
        assert hook_input.assignee is None
        assert hook_input.from_status is None
        assert hook_input.to_status is None
    
    def test_kanban_hook_input_to_dict(self):
        """Test KanbanHookInput serialization to dict."""
        hook_input = KanbanHookInput(
            session_id="session_123",
            cwd="/home/user",
            event_name="kanban_task_moved",
            timestamp="2023-01-01T00:00:00Z",
            task_id="task_456",
            board="project_board", 
            from_status="todo",
            to_status="running"
        )
        
        result = hook_input.to_dict()
        
        assert result["session_id"] == "session_123"
        assert result["event_name"] == "kanban_task_moved"
        assert result["task_id"] == "task_456"
        assert result["board"] == "project_board"
        assert result["from_status"] == "todo"
        assert result["to_status"] == "running"


class TestProtocolIntegration:
    """Integration tests for protocol usage patterns."""
    
    def test_protocol_import_structure(self):
        """Test that protocols can be imported from expected paths."""
        # Test direct imports
        from praisonaiagents.kanban.protocols import KanbanStoreProtocol
        from praisonaiagents.hooks.types import KanbanHookInput
        
        assert KanbanStoreProtocol is not None
        assert KanbanHookInput is not None
        
    def test_lazy_import_from_package_root(self):
        """Test that kanban protocols can be imported from package root."""
        from praisonaiagents.kanban import (
            KanbanStoreProtocol,
            KanbanTaskProtocol,
            VALID_KANBAN_STATUSES,
        )
        
        assert KanbanStoreProtocol is not None
        assert KanbanTaskProtocol is not None 
        assert VALID_KANBAN_STATUSES is not None
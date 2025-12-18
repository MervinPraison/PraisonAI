"""
Tests for A2A Task Store

TDD: Write tests first, then implement task_store module.
"""


class TestTaskStore:
    """Tests for TaskStore class."""
    
    def test_create_task(self):
        """Test creating a new task."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart, TaskState
        
        store = TaskStore()
        msg = Message(
            message_id="msg-1",
            role=Role.USER,
            parts=[TextPart(text="Hello")]
        )
        
        task = store.create_task(msg)
        
        assert task.id is not None
        assert task.status.state == TaskState.SUBMITTED
    
    def test_create_task_with_context(self):
        """Test creating task with context_id."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        store = TaskStore()
        msg = Message(
            message_id="msg-2",
            role=Role.USER,
            parts=[TextPart(text="Hello")],
            context_id="ctx-123"
        )
        
        task = store.create_task(msg)
        
        assert task.context_id == "ctx-123"
    
    def test_get_task(self):
        """Test retrieving a task by ID."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        store = TaskStore()
        msg = Message(
            message_id="msg-3",
            role=Role.USER,
            parts=[TextPart(text="Hello")]
        )
        
        created = store.create_task(msg)
        retrieved = store.get_task(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
    
    def test_get_task_not_found(self):
        """Test getting non-existent task returns None."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        
        store = TaskStore()
        result = store.get_task("non-existent-id")
        
        assert result is None
    
    def test_update_status(self):
        """Test updating task status."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart, TaskState
        
        store = TaskStore()
        msg = Message(
            message_id="msg-4",
            role=Role.USER,
            parts=[TextPart(text="Hello")]
        )
        
        task = store.create_task(msg)
        updated = store.update_status(task.id, TaskState.WORKING)
        
        assert updated.status.state == TaskState.WORKING
    
    def test_update_status_to_completed(self):
        """Test updating task to completed state."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart, TaskState
        
        store = TaskStore()
        msg = Message(
            message_id="msg-5",
            role=Role.USER,
            parts=[TextPart(text="Hello")]
        )
        
        task = store.create_task(msg)
        store.update_status(task.id, TaskState.WORKING)
        updated = store.update_status(task.id, TaskState.COMPLETED)
        
        assert updated.status.state == TaskState.COMPLETED
    
    def test_add_artifact(self):
        """Test adding artifact to task."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart, Artifact
        
        store = TaskStore()
        msg = Message(
            message_id="msg-6",
            role=Role.USER,
            parts=[TextPart(text="Hello")]
        )
        
        task = store.create_task(msg)
        artifact = Artifact(
            artifact_id="art-1",
            parts=[TextPart(text="Result")]
        )
        
        updated = store.add_artifact(task.id, artifact)
        
        assert updated.artifacts is not None
        assert len(updated.artifacts) == 1
    
    def test_add_message_to_history(self):
        """Test adding message to task history."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        store = TaskStore()
        msg1 = Message(
            message_id="msg-7",
            role=Role.USER,
            parts=[TextPart(text="Question")]
        )
        
        task = store.create_task(msg1)
        
        msg2 = Message(
            message_id="msg-8",
            role=Role.AGENT,
            parts=[TextPart(text="Answer")]
        )
        
        updated = store.add_to_history(task.id, msg2)
        
        assert updated.history is not None
        assert len(updated.history) >= 1
    
    def test_list_tasks(self):
        """Test listing all tasks."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        store = TaskStore()
        
        for i in range(3):
            msg = Message(
                message_id=f"msg-{i}",
                role=Role.USER,
                parts=[TextPart(text=f"Message {i}")]
            )
            store.create_task(msg)
        
        tasks = store.list_tasks()
        
        assert len(tasks) == 3
    
    def test_cancel_task(self):
        """Test cancelling a task."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart, TaskState
        
        store = TaskStore()
        msg = Message(
            message_id="msg-cancel",
            role=Role.USER,
            parts=[TextPart(text="Hello")]
        )
        
        task = store.create_task(msg)
        cancelled = store.cancel_task(task.id)
        
        assert cancelled.status.state == TaskState.CANCELLED


class TestTaskStoreContextManagement:
    """Tests for context management in TaskStore."""
    
    def test_tasks_grouped_by_context(self):
        """Test getting tasks by context_id."""
        from praisonaiagents.ui.a2a.task_store import TaskStore
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        store = TaskStore()
        
        # Create tasks in context A
        for i in range(2):
            msg = Message(
                message_id=f"msg-a-{i}",
                role=Role.USER,
                parts=[TextPart(text=f"A{i}")],
                context_id="context-a"
            )
            store.create_task(msg)
        
        # Create task in context B
        msg_b = Message(
            message_id="msg-b-1",
            role=Role.USER,
            parts=[TextPart(text="B1")],
            context_id="context-b"
        )
        store.create_task(msg_b)
        
        tasks_a = store.list_tasks(context_id="context-a")
        tasks_b = store.list_tasks(context_id="context-b")
        
        assert len(tasks_a) == 2
        assert len(tasks_b) == 1

"""
Unit tests for Message Queue feature.

Tests for:
1. MessageQueue - FIFO queue for messages
2. ProcessingState - State management
3. QueuedMessage - Message with metadata
4. MessageQueueHandler - Main handler class
"""

import time
import threading


# ============================================================================
# 1. MessageQueue Tests - FIFO operations
# ============================================================================

class TestMessageQueue:
    """Test MessageQueue FIFO operations."""
    
    def test_create_empty_queue(self):
        """Queue should start empty."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        assert queue.is_empty
        assert queue.count == 0
    
    def test_add_message(self):
        """Should add message to queue."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("Hello")
        assert not queue.is_empty
        assert queue.count == 1
    
    def test_add_multiple_messages(self):
        """Should add multiple messages in order."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("First")
        queue.add("Second")
        queue.add("Third")
        assert queue.count == 3
    
    def test_pop_message_fifo(self):
        """Should pop messages in FIFO order."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("First")
        queue.add("Second")
        msg = queue.pop()
        assert msg == "First"
        assert queue.count == 1
    
    def test_pop_empty_queue(self):
        """Should return None when popping empty queue."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        msg = queue.pop()
        assert msg is None
    
    def test_peek_message(self):
        """Should peek without removing."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("First")
        queue.add("Second")
        msg = queue.peek()
        assert msg == "First"
        assert queue.count == 2  # Not removed
    
    def test_peek_empty_queue(self):
        """Should return None when peeking empty queue."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        msg = queue.peek()
        assert msg is None
    
    def test_clear_queue(self):
        """Should clear all messages."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("First")
        queue.add("Second")
        queue.clear()
        assert queue.is_empty
        assert queue.count == 0
    
    def test_get_all_messages(self):
        """Should get all messages as list."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("First")
        queue.add("Second")
        messages = queue.get_all()
        assert messages == ["First", "Second"]
        assert queue.count == 2  # Not removed
    
    def test_remove_at_index(self):
        """Should remove message at specific index."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("First")
        queue.add("Second")
        queue.add("Third")
        removed = queue.remove_at(1)
        assert removed == "Second"
        assert queue.count == 2
        assert queue.get_all() == ["First", "Third"]
    
    def test_remove_at_invalid_index(self):
        """Should return None for invalid index."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("First")
        removed = queue.remove_at(5)
        assert removed is None
        assert queue.count == 1
    
    def test_add_empty_message_ignored(self):
        """Should ignore empty messages."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        queue.add("")
        queue.add("   ")
        assert queue.is_empty
    
    def test_thread_safety(self):
        """Queue should be thread-safe."""
        from praisonai.cli.features.message_queue import MessageQueue
        queue = MessageQueue()
        results = []
        
        def add_messages():
            for i in range(100):
                queue.add(f"msg-{i}")
        
        def pop_messages():
            for _ in range(100):
                msg = queue.pop()
                if msg:
                    results.append(msg)
        
        t1 = threading.Thread(target=add_messages)
        t2 = threading.Thread(target=pop_messages)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        # All messages should be accounted for
        total = len(results) + queue.count
        assert total == 100


# ============================================================================
# 2. ProcessingState Tests
# ============================================================================

class TestProcessingState:
    """Test ProcessingState enum and state management."""
    
    def test_state_enum_values(self):
        """Should have correct state values."""
        from praisonai.cli.features.message_queue import ProcessingState
        assert ProcessingState.IDLE.value == "idle"
        assert ProcessingState.PROCESSING.value == "processing"
        assert ProcessingState.WAITING_APPROVAL.value == "waiting_approval"
    
    def test_state_manager_initial_state(self):
        """Should start in IDLE state."""
        from praisonai.cli.features.message_queue import StateManager, ProcessingState
        manager = StateManager()
        assert manager.current_state == ProcessingState.IDLE
    
    def test_state_transition(self):
        """Should transition between states."""
        from praisonai.cli.features.message_queue import StateManager, ProcessingState
        manager = StateManager()
        manager.set_state(ProcessingState.PROCESSING)
        assert manager.current_state == ProcessingState.PROCESSING
    
    def test_is_idle(self):
        """Should correctly report idle state."""
        from praisonai.cli.features.message_queue import StateManager, ProcessingState
        manager = StateManager()
        assert manager.is_idle
        manager.set_state(ProcessingState.PROCESSING)
        assert not manager.is_idle
    
    def test_is_processing(self):
        """Should correctly report processing state."""
        from praisonai.cli.features.message_queue import StateManager, ProcessingState
        manager = StateManager()
        assert not manager.is_processing
        manager.set_state(ProcessingState.PROCESSING)
        assert manager.is_processing
    
    def test_state_callback(self):
        """Should call callback on state change."""
        from praisonai.cli.features.message_queue import StateManager, ProcessingState
        callback_called = []
        
        def on_state_change(old_state, new_state):
            callback_called.append((old_state, new_state))
        
        manager = StateManager(on_state_change=on_state_change)
        manager.set_state(ProcessingState.PROCESSING)
        
        assert len(callback_called) == 1
        assert callback_called[0] == (ProcessingState.IDLE, ProcessingState.PROCESSING)


# ============================================================================
# 3. QueuedMessage Tests
# ============================================================================

class TestQueuedMessage:
    """Test QueuedMessage dataclass."""
    
    def test_create_queued_message(self):
        """Should create message with content."""
        from praisonai.cli.features.message_queue import QueuedMessage
        msg = QueuedMessage(content="Hello")
        assert msg.content == "Hello"
        assert msg.timestamp is not None
    
    def test_message_has_timestamp(self):
        """Should have creation timestamp."""
        from praisonai.cli.features.message_queue import QueuedMessage
        before = time.time()
        msg = QueuedMessage(content="Hello")
        after = time.time()
        assert before <= msg.timestamp <= after
    
    def test_message_priority(self):
        """Should support priority levels."""
        from praisonai.cli.features.message_queue import QueuedMessage, MessagePriority
        msg = QueuedMessage(content="Hello", priority=MessagePriority.HIGH)
        assert msg.priority == MessagePriority.HIGH
    
    def test_default_priority_normal(self):
        """Should default to NORMAL priority."""
        from praisonai.cli.features.message_queue import QueuedMessage, MessagePriority
        msg = QueuedMessage(content="Hello")
        assert msg.priority == MessagePriority.NORMAL


# ============================================================================
# 4. MessageQueueHandler Tests
# ============================================================================

class TestMessageQueueHandler:
    """Test MessageQueueHandler main class."""
    
    def test_handler_creation(self):
        """Should create handler with default settings."""
        from praisonai.cli.features.message_queue import MessageQueueHandler
        handler = MessageQueueHandler()
        assert handler.queue.is_empty
        assert handler.state_manager.is_idle
    
    def test_submit_when_idle(self):
        """Should process immediately when idle."""
        from praisonai.cli.features.message_queue import MessageQueueHandler
        processed = []
        
        def processor(msg):
            processed.append(msg)
            return f"Response to: {msg}"
        
        handler = MessageQueueHandler(processor=processor)
        handler.submit("Hello")
        
        # Should process immediately
        assert "Hello" in processed
    
    def test_queue_when_processing(self):
        """Should queue message when already processing."""
        from praisonai.cli.features.message_queue import MessageQueueHandler, ProcessingState
        
        handler = MessageQueueHandler()
        handler.state_manager.set_state(ProcessingState.PROCESSING)
        handler.submit("Hello")
        
        # Should be queued, not processed
        assert handler.queue.count == 1
    
    def test_auto_process_queue_on_idle(self):
        """Should auto-process queue when becoming idle."""
        from praisonai.cli.features.message_queue import MessageQueueHandler, ProcessingState
        processed = []
        
        def processor(msg):
            processed.append(msg)
            return f"Response: {msg}"
        
        handler = MessageQueueHandler(processor=processor)
        
        # Simulate processing state
        handler.state_manager.set_state(ProcessingState.PROCESSING)
        handler.submit("Queued1")
        handler.submit("Queued2")
        
        assert handler.queue.count == 2
        
        # Simulate becoming idle - should trigger queue processing
        handler.on_processing_complete()
        
        # Queue should be processed
        assert "Queued1" in processed or handler.queue.count < 2
    
    def test_get_queue_status(self):
        """Should return queue status."""
        from praisonai.cli.features.message_queue import MessageQueueHandler, ProcessingState
        handler = MessageQueueHandler()
        handler.state_manager.set_state(ProcessingState.PROCESSING)
        handler.submit("Hello")
        handler.submit("World")
        
        status = handler.get_status()
        assert status['queue_count'] == 2
        assert status['state'] == 'processing'
    
    def test_clear_queue(self):
        """Should clear queue via handler."""
        from praisonai.cli.features.message_queue import MessageQueueHandler, ProcessingState
        handler = MessageQueueHandler()
        handler.state_manager.set_state(ProcessingState.PROCESSING)
        handler.submit("Hello")
        handler.clear_queue()
        assert handler.queue.is_empty


# ============================================================================
# 5. QueueDisplay Tests
# ============================================================================

class TestQueueDisplay:
    """Test QueueDisplay for visual indicators."""
    
    def test_format_empty_queue(self):
        """Should return empty string for empty queue."""
        from praisonai.cli.features.message_queue import QueueDisplay, MessageQueue
        queue = MessageQueue()
        display = QueueDisplay(queue)
        assert display.format_queue() == ""
    
    def test_format_single_message(self):
        """Should format single message."""
        from praisonai.cli.features.message_queue import QueueDisplay, MessageQueue
        queue = MessageQueue()
        queue.add("Hello world")
        display = QueueDisplay(queue)
        formatted = display.format_queue()
        assert "↳" in formatted
        assert "Hello world" in formatted
    
    def test_format_multiple_messages(self):
        """Should format multiple messages."""
        from praisonai.cli.features.message_queue import QueueDisplay, MessageQueue
        queue = MessageQueue()
        queue.add("First")
        queue.add("Second")
        display = QueueDisplay(queue)
        formatted = display.format_queue()
        assert "First" in formatted
        assert "Second" in formatted
    
    def test_truncate_long_message(self):
        """Should truncate long messages."""
        from praisonai.cli.features.message_queue import QueueDisplay, MessageQueue
        queue = MessageQueue()
        queue.add("A" * 100)
        display = QueueDisplay(queue, max_message_length=20)
        formatted = display.format_queue()
        assert "..." in formatted
    
    def test_format_status_idle(self):
        """Should show idle status."""
        from praisonai.cli.features.message_queue import QueueDisplay, MessageQueue, StateManager
        queue = MessageQueue()
        state = StateManager()
        display = QueueDisplay(queue, state_manager=state)
        status = display.format_status()
        assert "idle" in status.lower() or status == ""
    
    def test_format_status_processing(self):
        """Should show processing status."""
        from praisonai.cli.features.message_queue import (
            QueueDisplay, MessageQueue, StateManager, ProcessingState
        )
        queue = MessageQueue()
        state = StateManager()
        state.set_state(ProcessingState.PROCESSING)
        display = QueueDisplay(queue, state_manager=state)
        status = display.format_status()
        assert "processing" in status.lower() or "⏳" in status
    
    def test_format_queue_count(self):
        """Should show queue count."""
        from praisonai.cli.features.message_queue import QueueDisplay, MessageQueue, ProcessingState, StateManager
        queue = MessageQueue()
        queue.add("First")
        queue.add("Second")
        state = StateManager()
        state.set_state(ProcessingState.PROCESSING)
        display = QueueDisplay(queue, state_manager=state)
        count_str = display.format_queue_count()
        assert "2" in count_str


# ============================================================================
# 6. Integration Tests
# ============================================================================

class TestMessageQueueIntegration:
    """Integration tests for message queue system."""
    
    def test_full_workflow(self):
        """Test complete queue workflow."""
        from praisonai.cli.features.message_queue import (
            MessageQueueHandler, ProcessingState
        )
        
        results = []
        
        def processor(msg):
            results.append(msg)
            return f"Processed: {msg}"
        
        handler = MessageQueueHandler(processor=processor)
        
        # 1. Submit when idle - processes immediately
        handler.submit("First")
        assert "First" in results
        
        # 2. Simulate processing
        handler.state_manager.set_state(ProcessingState.PROCESSING)
        
        # 3. Queue messages while processing
        handler.submit("Second")
        handler.submit("Third")
        assert handler.queue.count == 2
        
        # 4. Complete processing - should auto-process queue
        handler.on_processing_complete()
        
        # Queue should be processed
        assert handler.queue.count < 2 or "Second" in results
    
    def test_queue_with_display(self):
        """Test queue with display formatting."""
        from praisonai.cli.features.message_queue import (
            MessageQueueHandler, QueueDisplay, ProcessingState
        )
        
        handler = MessageQueueHandler()
        handler.state_manager.set_state(ProcessingState.PROCESSING)
        handler.submit("Task 1")
        handler.submit("Task 2")
        
        display = QueueDisplay(handler.queue, state_manager=handler.state_manager)
        
        # Should show processing status
        status = display.format_status()
        assert "processing" in status.lower() or "⏳" in status
        
        # Should show queued messages
        queue_str = display.format_queue()
        assert "Task 1" in queue_str
        assert "Task 2" in queue_str


# ============================================================================
# 9. AsyncProcessor Tests - Background processing
# ============================================================================

class TestAsyncProcessor:
    """Test AsyncProcessor for background agent execution."""
    
    def test_processor_creation(self):
        """Should create processor with callback."""
        from praisonai.cli.features.message_queue import AsyncProcessor
        
        results = []
        def on_complete(result):
            results.append(result)
        
        processor = AsyncProcessor(on_complete=on_complete)
        assert processor is not None
    
    def test_start_processing(self):
        """Should start processing in background thread."""
        from praisonai.cli.features.message_queue import AsyncProcessor
        import time
        
        results = []
        def work_fn():
            time.sleep(0.05)
            return "done"
        
        def on_complete(result):
            results.append(result)
        
        processor = AsyncProcessor(on_complete=on_complete)
        processor.start(work_fn)
        
        # Should be processing
        assert processor.is_running
        
        # Wait for completion
        time.sleep(0.15)
        assert not processor.is_running
        assert "done" in results
    
    def test_is_running_property(self):
        """Should track running state."""
        from praisonai.cli.features.message_queue import AsyncProcessor
        import time
        
        def slow_work():
            time.sleep(0.1)
            return "result"
        
        processor = AsyncProcessor()
        assert not processor.is_running
        
        processor.start(slow_work)
        assert processor.is_running
        
        time.sleep(0.15)
        assert not processor.is_running
    
    def test_on_status_callback(self):
        """Should call status callback during processing."""
        from praisonai.cli.features.message_queue import AsyncProcessor
        import time
        
        statuses = []
        def on_status(status):
            statuses.append(status)
        
        def work_with_status(status_callback):
            status_callback("Starting...")
            time.sleep(0.02)
            status_callback("Working...")
            return "done"
        
        processor = AsyncProcessor(on_status=on_status)
        processor.start(lambda: work_with_status(on_status))
        
        time.sleep(0.1)
        assert len(statuses) >= 1


# ============================================================================
# 10. LiveStatusDisplay Tests - Real-time status
# ============================================================================

class TestLiveStatusDisplay:
    """Test LiveStatusDisplay for real-time tool/command status."""
    
    def test_display_creation(self):
        """Should create display."""
        from praisonai.cli.features.message_queue import LiveStatusDisplay
        
        display = LiveStatusDisplay()
        assert display is not None
    
    def test_update_status(self):
        """Should update current status."""
        from praisonai.cli.features.message_queue import LiveStatusDisplay
        
        display = LiveStatusDisplay()
        display.update_status("Processing...")
        assert display.current_status == "Processing..."
    
    def test_add_tool_call(self):
        """Should track tool calls."""
        from praisonai.cli.features.message_queue import LiveStatusDisplay
        
        display = LiveStatusDisplay()
        display.add_tool_call("read_file", {"path": "test.py"})
        
        assert len(display.tool_calls) == 1
        assert display.tool_calls[0]['name'] == "read_file"
    
    def test_add_command_execution(self):
        """Should track command executions."""
        from praisonai.cli.features.message_queue import LiveStatusDisplay
        
        display = LiveStatusDisplay()
        display.add_command("ls -la")
        
        assert len(display.commands) == 1
        assert display.commands[0] == "ls -la"
    
    def test_format_live_status(self):
        """Should format live status for display."""
        from praisonai.cli.features.message_queue import LiveStatusDisplay
        
        display = LiveStatusDisplay()
        display.update_status("Thinking...")
        display.add_tool_call("read_file", {"path": "main.py"})
        
        formatted = display.format()
        assert "Thinking" in formatted or "read_file" in formatted
    
    def test_clear_status(self):
        """Should clear all status."""
        from praisonai.cli.features.message_queue import LiveStatusDisplay
        
        display = LiveStatusDisplay()
        display.update_status("Working")
        display.add_tool_call("test", {})
        display.add_command("echo hi")
        
        display.clear()
        
        assert display.current_status == ""
        assert len(display.tool_calls) == 0
        assert len(display.commands) == 0


# ============================================================================
# 11. NonBlockingInput Tests - Async input handling
# ============================================================================

class TestNonBlockingInput:
    """Test NonBlockingInput for async user input."""
    
    def test_input_handler_creation(self):
        """Should create input handler."""
        from praisonai.cli.features.message_queue import NonBlockingInput
        
        handler = NonBlockingInput()
        assert handler is not None
    
    def test_submit_input(self):
        """Should accept input while processing."""
        from praisonai.cli.features.message_queue import NonBlockingInput
        
        handler = NonBlockingInput()
        handler.submit("new message")
        
        assert handler.has_pending
        assert handler.pop() == "new message"
    
    def test_multiple_inputs(self):
        """Should queue multiple inputs."""
        from praisonai.cli.features.message_queue import NonBlockingInput
        
        handler = NonBlockingInput()
        handler.submit("first")
        handler.submit("second")
        
        assert handler.pending_count == 2
        assert handler.pop() == "first"
        assert handler.pop() == "second"

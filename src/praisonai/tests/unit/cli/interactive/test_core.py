"""Tests for InteractiveCore class."""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock


class TestInteractiveCoreInit:
    """Tests for InteractiveCore initialization."""
    
    def test_core_creation_default_config(self):
        """Create core with default config."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        
        core = InteractiveCore()
        
        assert core.config is not None
        assert isinstance(core.config, InteractiveConfig)
    
    def test_core_creation_with_config(self):
        """Create core with custom config."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig(model="gpt-4", verbose=True)
        core = InteractiveCore(config=config)
        
        assert core.config.model == "gpt-4"
        assert core.config.verbose is True
    
    def test_core_has_session_store(self):
        """Core should have access to session store."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        assert core.session_store is not None
    
    def test_core_has_tools(self):
        """Core should have access to tools."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        # Tools are loaded lazily
        assert hasattr(core, 'tools')
    
    def test_core_has_permission_manager(self):
        """Core should have permission manager."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        assert hasattr(core, 'permission_manager')


class TestInteractiveCoreSubscription:
    """Tests for event subscription."""
    
    def test_subscribe_handler(self):
        """Subscribe a handler to events."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import InteractiveEventType
        
        core = InteractiveCore()
        handler = Mock()
        
        unsubscribe = core.subscribe(handler)
        
        assert callable(unsubscribe)
        assert handler in core._event_handlers
    
    def test_unsubscribe_handler(self):
        """Unsubscribe removes handler."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        handler = Mock()
        
        unsubscribe = core.subscribe(handler)
        unsubscribe()
        
        assert handler not in core._event_handlers
    
    def test_subscribe_with_filter(self):
        """Subscribe with event type filter."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import InteractiveEventType
        
        core = InteractiveCore()
        handler = Mock()
        
        unsubscribe = core.subscribe(
            handler, 
            event_types=[InteractiveEventType.MESSAGE_CHUNK]
        )
        
        assert callable(unsubscribe)
    
    def test_emit_calls_handlers(self):
        """Emitting event should call subscribed handlers."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import InteractiveEvent, InteractiveEventType
        
        core = InteractiveCore()
        handler = Mock()
        core.subscribe(handler)
        
        event = InteractiveEvent(type=InteractiveEventType.IDLE)
        core._emit(event)
        
        handler.assert_called_once_with(event)
    
    def test_emit_respects_filter(self):
        """Filtered handlers only receive matching events."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import InteractiveEvent, InteractiveEventType
        
        core = InteractiveCore()
        handler = Mock()
        core.subscribe(handler, event_types=[InteractiveEventType.ERROR])
        
        # Emit non-matching event
        event = InteractiveEvent(type=InteractiveEventType.IDLE)
        core._emit(event)
        
        handler.assert_not_called()
        
        # Emit matching event
        error_event = InteractiveEvent(type=InteractiveEventType.ERROR)
        core._emit(error_event)
        
        handler.assert_called_once_with(error_event)


class TestInteractiveCoreSession:
    """Tests for session management."""
    
    def test_create_session(self):
        """Create a new session."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        session_id = core.create_session()
        
        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0
    
    def test_create_session_with_title(self):
        """Create session with custom title."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        session_id = core.create_session(title="My Test Session")
        
        assert session_id is not None
        # Session should be retrievable
        session = core.get_session(session_id)
        assert session is not None
    
    def test_resume_session(self):
        """Resume an existing session."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        # Create a session first
        session_id = core.create_session()
        
        # Resume it
        resumed = core.resume_session(session_id)
        
        assert resumed is True
        assert core.current_session_id == session_id
    
    def test_resume_nonexistent_session(self):
        """Resuming nonexistent session returns False."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        resumed = core.resume_session("nonexistent-session-id")
        
        assert resumed is False
    
    def test_continue_session_finds_last(self):
        """Continue session finds the most recent session."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        # Create multiple sessions
        session1 = core.create_session()
        session2 = core.create_session()
        
        # Continue should find the last one
        last_session_id = core.continue_session()
        
        assert last_session_id == session2
    
    def test_continue_session_none_available(self):
        """Continue session returns None when no sessions exist."""
        import tempfile
        from pathlib import Path
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        from praisonai.cli.session.unified import UnifiedSessionStore
        
        # Use a fresh temporary directory with no sessions
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fresh session store in the temp directory
            fresh_store = UnifiedSessionStore(session_dir=Path(tmpdir))
            
            config = InteractiveConfig(workspace=tmpdir)
            core = InteractiveCore(config=config)
            core._session_store = fresh_store  # Use fresh store
            
            last_session_id = core.continue_session()
            
            assert last_session_id is None
    
    def test_get_session(self):
        """Get session by ID."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        session_id = core.create_session(title="Test Session")
        
        session = core.get_session(session_id)
        
        assert session is not None
        assert session.session_id == session_id


class TestInteractiveCorePrompt:
    """Tests for prompt execution."""
    
    @pytest.mark.asyncio
    async def test_prompt_emits_message_start(self):
        """Prompt should emit MESSAGE_START event."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import InteractiveEventType
        
        core = InteractiveCore()
        events = []
        core.subscribe(lambda e: events.append(e))
        
        # Mock the agent to avoid real API calls
        with patch.object(core, '_execute_prompt', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "Hello!"
            await core.prompt("Hello")
        
        event_types = [e.type for e in events]
        assert InteractiveEventType.MESSAGE_START in event_types
    
    @pytest.mark.asyncio
    async def test_prompt_emits_message_end(self):
        """Prompt should emit MESSAGE_END event."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import InteractiveEventType
        
        core = InteractiveCore()
        events = []
        core.subscribe(lambda e: events.append(e))
        
        with patch.object(core, '_execute_prompt', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "Response"
            await core.prompt("Test")
        
        event_types = [e.type for e in events]
        assert InteractiveEventType.MESSAGE_END in event_types
    
    @pytest.mark.asyncio
    async def test_prompt_returns_response(self):
        """Prompt should return the response text."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        with patch.object(core, '_execute_prompt', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "This is the response"
            response = await core.prompt("What is 2+2?")
        
        assert response == "This is the response"
    
    @pytest.mark.asyncio
    async def test_prompt_with_session(self):
        """Prompt should use specified session."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        session_id = core.create_session()
        
        with patch.object(core, '_execute_prompt', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "Response"
            await core.prompt("Hello", session_id=session_id)
        
        # Verify session was used
        assert core.current_session_id == session_id
    
    @pytest.mark.asyncio
    async def test_prompt_creates_session_if_none(self):
        """Prompt should create session if none exists."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        assert core.current_session_id is None
        
        with patch.object(core, '_execute_prompt', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = "Response"
            await core.prompt("Hello")
        
        assert core.current_session_id is not None


class TestInteractiveCoreApproval:
    """Tests for approval/permission flow."""
    
    def test_ask_permission_emits_event(self):
        """ask_permission should emit APPROVAL_ASKED event."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import InteractiveEventType, ApprovalRequest
        
        core = InteractiveCore()
        events = []
        core.subscribe(lambda e: events.append(e))
        
        request = ApprovalRequest(
            action_type="file_write",
            description="Write to test.txt",
            tool_name="write_file",
            parameters={"path": "test.txt"}
        )
        
        # Start approval (non-blocking for test)
        core._emit_approval_request(request)
        
        event_types = [e.type for e in events]
        assert InteractiveEventType.APPROVAL_ASKED in event_types
    
    def test_respond_permission_emits_event(self):
        """respond_permission should emit APPROVAL_ANSWERED event."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import (
            InteractiveEventType, ApprovalResponse, ApprovalDecision
        )
        
        core = InteractiveCore()
        events = []
        core.subscribe(lambda e: events.append(e))
        
        response = ApprovalResponse(
            request_id="req-123",
            decision=ApprovalDecision.ONCE
        )
        
        core._emit_approval_response(response)
        
        event_types = [e.type for e in events]
        assert InteractiveEventType.APPROVAL_ANSWERED in event_types
    
    def test_auto_approval_mode(self):
        """Auto approval mode should not ask for permission."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        from praisonai.cli.interactive.events import ApprovalRequest, ApprovalDecision
        
        config = InteractiveConfig(approval_mode="auto")
        core = InteractiveCore(config=config)
        
        request = ApprovalRequest(
            action_type="file_read",
            description="Read test.txt",
            tool_name="read_file",
            parameters={"path": "test.txt"}
        )
        
        # In auto mode, should return approved immediately
        decision = core.check_permission(request)
        
        assert decision == ApprovalDecision.ONCE  # Auto-approved
    
    def test_persistent_approval_pattern(self):
        """Persistent approval patterns should be remembered."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.events import ApprovalRequest, ApprovalDecision
        
        core = InteractiveCore()
        
        # Add a persistent approval pattern
        core.add_approval_pattern("file_read:*")
        
        request = ApprovalRequest(
            action_type="file_read",
            description="Read any file",
            tool_name="read_file",
            parameters={"path": "/any/file.txt"}
        )
        
        decision = core.check_permission(request)
        
        assert decision == ApprovalDecision.ALWAYS


class TestInteractiveCoreTools:
    """Tests for tool dispatch."""
    
    def test_get_tools_returns_list(self):
        """get_tools should return list of tools."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        tools = core.get_tools()
        
        assert isinstance(tools, list)
    
    def test_tools_respect_config(self):
        """Tools should respect ACP/LSP config."""
        from praisonai.cli.interactive.core import InteractiveCore
        from praisonai.cli.interactive.config import InteractiveConfig
        
        config = InteractiveConfig(enable_acp=False, enable_lsp=False)
        core = InteractiveCore(config=config)
        
        tools = core.get_tools()
        
        # Should only have basic tools, no ACP/LSP
        tool_names = [t.__name__ if hasattr(t, '__name__') else str(t) for t in tools]
        assert not any("acp_" in name for name in tool_names)
        assert not any("lsp_" in name for name in tool_names)


class TestInteractiveCoreExportImport:
    """Tests for session export/import."""
    
    def test_export_session(self):
        """Export session to dict."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        session_id = core.create_session(title="Export Test")
        
        exported = core.export_session(session_id)
        
        assert isinstance(exported, dict)
        assert "session_id" in exported
        assert "title" in exported
        assert "messages" in exported
    
    def test_export_session_to_file(self):
        """Export session to JSON file."""
        import tempfile
        import json
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        session_id = core.create_session(title="File Export Test")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name
        
        core.export_session_to_file(session_id, filepath)
        
        with open(filepath) as f:
            data = json.load(f)
        
        assert data["session_id"] == session_id
        
        # Cleanup
        import os
        os.unlink(filepath)
    
    def test_import_session(self):
        """Import session from dict."""
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        session_data = {
            "session_id": "imported-session-123",
            "title": "Imported Session",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ],
            "metadata": {}
        }
        
        session_id = core.import_session(session_data)
        
        assert session_id == "imported-session-123"
        
        # Verify session exists
        session = core.get_session(session_id)
        assert session is not None
    
    def test_import_session_from_file(self):
        """Import session from JSON file."""
        import tempfile
        import json
        from praisonai.cli.interactive.core import InteractiveCore
        
        core = InteractiveCore()
        
        session_data = {
            "session_id": "file-imported-session",
            "title": "File Imported",
            "messages": [],
            "metadata": {}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(session_data, f)
            filepath = f.name
        
        session_id = core.import_session_from_file(filepath)
        
        assert session_id == "file-imported-session"
        
        # Cleanup
        import os
        os.unlink(filepath)

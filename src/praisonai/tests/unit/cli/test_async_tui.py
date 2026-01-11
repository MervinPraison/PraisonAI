"""
Tests for PraisonAI Async TUI Application.
"""


class TestAsyncTUIConfig:
    """Tests for AsyncTUIConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        from praisonai.cli.interactive.async_tui import AsyncTUIConfig
        
        config = AsyncTUIConfig()
        assert config.model == "gpt-4o-mini"
        assert config.show_logo is True
        assert config.show_status_bar is True
        assert config.session_id is None
        assert config.workspace is None
    
    def test_custom_values(self):
        """Test custom configuration values."""
        from praisonai.cli.interactive.async_tui import AsyncTUIConfig
        
        config = AsyncTUIConfig(
            model="gpt-4o",
            show_logo=False,
            session_id="test123",
        )
        assert config.model == "gpt-4o"
        assert config.show_logo is False
        assert config.session_id == "test123"


class TestChatMessage:
    """Tests for ChatMessage dataclass."""
    
    def test_message_creation(self):
        """Test message creation."""
        from praisonai.cli.interactive.async_tui import ChatMessage
        
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is not None
    
    def test_message_roles(self):
        """Test different message roles."""
        from praisonai.cli.interactive.async_tui import ChatMessage
        
        roles = ["user", "assistant", "system", "status"]
        for role in roles:
            msg = ChatMessage(role=role, content="test")
            assert msg.role == role


class TestGetLogo:
    """Tests for get_logo function."""
    
    def test_logo_wide_terminal(self):
        """Test logo for wide terminal."""
        from praisonai.cli.interactive.async_tui import get_logo, LOGO
        
        logo = get_logo(100)
        assert logo == LOGO
    
    def test_logo_medium_terminal(self):
        """Test logo for medium terminal."""
        from praisonai.cli.interactive.async_tui import get_logo, LOGO_SMALL
        
        logo = get_logo(50)
        assert logo == LOGO_SMALL
    
    def test_logo_narrow_terminal(self):
        """Test logo for narrow terminal."""
        from praisonai.cli.interactive.async_tui import get_logo, LOGO_MINIMAL
        
        logo = get_logo(30)
        assert logo == LOGO_MINIMAL
    
    def test_logo_contains_praison_ai(self):
        """Test that logo contains 'Praison AI' branding."""
        from praisonai.cli.interactive.async_tui import LOGO_MINIMAL
        
        assert "Praison AI" in LOGO_MINIMAL


class TestAsyncTUI:
    """Tests for AsyncTUI class."""
    
    def test_init_default(self):
        """Test default initialization."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert tui.config is not None
        assert tui.messages == []
        assert tui._running is False
        assert tui._processing is False
        assert tui.session_id is not None
    
    def test_init_with_config(self):
        """Test initialization with config."""
        from praisonai.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig
        
        config = AsyncTUIConfig(model="gpt-4o", show_logo=False)
        tui = AsyncTUI(config=config)
        assert tui.config.model == "gpt-4o"
        assert tui.config.show_logo is False
    
    def test_format_output_empty(self):
        """Test format_output with no messages."""
        from praisonai.cli.interactive.async_tui import AsyncTUI, AsyncTUIConfig
        
        config = AsyncTUIConfig(show_logo=True)
        tui = AsyncTUI(config=config)
        
        output = tui._format_output()
        assert "Type your message" in output or "gpt-4o-mini" in output
    
    def test_format_output_with_messages(self):
        """Test format_output with messages."""
        from praisonai.cli.interactive.async_tui import AsyncTUI, ChatMessage
        
        tui = AsyncTUI()
        tui.messages = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there"),
        ]
        
        output = tui._format_output()
        assert "Hello" in output
        assert "Hi there" in output
    
    def test_format_output_with_processing(self):
        """Test format_output shows processing indicator."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._processing = True
        tui._status_text = "Thinking..."
        
        output = tui._format_output()
        assert "Thinking..." in output
    
    def test_handle_command_exit(self):
        """Test handling exit command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._running = True
        
        result = tui._handle_command("/exit")
        assert result is True
        assert tui._running is False
    
    def test_handle_command_quit(self):
        """Test handling quit command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._running = True
        
        result = tui._handle_command("/quit")
        assert result is True
        assert tui._running is False
    
    def test_handle_command_help(self):
        """Test handling help command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/help")
        assert result is True
        assert len(tui.messages) == 1
        assert tui.messages[0].role == "system"
        assert "PageUp" in tui.messages[0].content  # Scroll instructions
    
    def test_handle_command_clear(self):
        """Test handling clear command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI, ChatMessage
        
        tui = AsyncTUI()
        tui.messages = [ChatMessage(role="user", content="test")]
        
        result = tui._handle_command("/clear")
        assert result is True
        # Clear now adds a confirmation message
        assert len(tui.messages) == 1
        assert "cleared" in tui.messages[0].content.lower()
    
    def test_handle_command_new(self):
        """Test handling new command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI, ChatMessage
        
        tui = AsyncTUI()
        old_session = tui.session_id
        tui.messages = [ChatMessage(role="user", content="test")]
        
        result = tui._handle_command("/new")
        assert result is True
        assert len(tui.messages) == 1
        assert tui.session_id != old_session
    
    def test_handle_command_model_show(self):
        """Test handling model command (show)."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/model")
        assert result is True
        assert len(tui.messages) == 1
        assert "gpt-4o-mini" in tui.messages[0].content
    
    def test_handle_command_model_change(self):
        """Test handling model command (change)."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/model gpt-4o")
        assert result is True
        assert tui.config.model == "gpt-4o"
        assert tui._agent is None
    
    def test_handle_command_unknown(self):
        """Test handling unknown command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/unknown")
        assert result is True
        assert len(tui.messages) == 1
        assert "Unknown" in tui.messages[0].content


class TestStartAsyncTUI:
    """Tests for start_async_tui function."""
    
    def test_function_exists(self):
        """Test that start_async_tui function exists."""
        from praisonai.cli.interactive.async_tui import start_async_tui
        assert callable(start_async_tui)


class TestASCIILogos:
    """Tests for ASCII logo constants."""
    
    def test_logo_exists(self):
        """Test LOGO constant exists and has content."""
        from praisonai.cli.interactive.async_tui import LOGO
        assert len(LOGO) > 0
        assert "██" in LOGO
    
    def test_logo_small_exists(self):
        """Test LOGO_SMALL constant exists."""
        from praisonai.cli.interactive.async_tui import LOGO_SMALL
        assert len(LOGO_SMALL) > 0
    
    def test_logo_minimal_branding(self):
        """Test LOGO_MINIMAL has correct branding."""
        from praisonai.cli.interactive.async_tui import LOGO_MINIMAL
        assert "Praison AI" in LOGO_MINIMAL


class TestMessageFormatting:
    """Tests for message formatting."""
    
    def test_user_message_prefix(self):
        """Test user messages have correct prefix."""
        from praisonai.cli.interactive.async_tui import AsyncTUI, ChatMessage
        
        tui = AsyncTUI()
        tui.messages = [ChatMessage(role="user", content="test")]
        
        output = tui._format_output()
        assert "› test" in output
    
    def test_assistant_message_prefix(self):
        """Test assistant messages have correct prefix."""
        from praisonai.cli.interactive.async_tui import AsyncTUI, ChatMessage
        
        tui = AsyncTUI()
        tui.messages = [ChatMessage(role="assistant", content="response")]
        
        output = tui._format_output()
        assert "● response" in output
    
    def test_status_message_prefix(self):
        """Test status messages have correct prefix."""
        from praisonai.cli.interactive.async_tui import AsyncTUI, ChatMessage
        
        tui = AsyncTUI()
        tui.messages = [ChatMessage(role="status", content="thinking")]
        
        output = tui._format_output()
        assert "⏳ thinking" in output


class TestNonBlockingExecution:
    """Tests for non-blocking execution features."""
    
    def test_processing_flag(self):
        """Test processing flag is used correctly."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert tui._processing is False
        
        tui._processing = True
        tui._status_text = "Working..."
        
        output = tui._format_output()
        assert "Working..." in output
    
    def test_status_text_updates(self):
        """Test status text can be updated."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._processing = True
        
        tui._status_text = "Step 1"
        output1 = tui._format_output()
        assert "Step 1" in output1
        
        tui._status_text = "Step 2"
        output2 = tui._format_output()
        assert "Step 2" in output2


class TestNewSlashCommands:
    """Tests for newly added slash commands."""
    
    def test_session_command(self):
        """Test /session command shows session info."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/session")
        assert result is True
        assert len(tui.messages) == 1
        assert "Session:" in tui.messages[0].content
        assert tui.session_id in tui.messages[0].content
    
    def test_history_command_empty(self):
        """Test /history command with no history."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/history")
        assert result is True
        assert "No conversation history" in tui.messages[0].content
    
    def test_history_command_with_history(self):
        """Test /history command with conversation history."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._conversation_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = tui._handle_command("/history")
        assert result is True
        assert "[user]" in tui.messages[0].content
    
    def test_cost_command(self):
        """Test /cost command shows token usage."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._total_tokens = 100
        tui._total_cost = 0.001
        result = tui._handle_command("/cost")
        assert result is True
        assert "100" in tui.messages[0].content
    
    def test_compact_command(self):
        """Test /compact command toggles compact mode."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert tui.config.compact_mode is False
        
        result = tui._handle_command("/compact")
        assert result is True
        assert tui.config.compact_mode is True
        
        result = tui._handle_command("/compact")
        assert tui.config.compact_mode is False
    
    def test_multiline_command(self):
        """Test /multiline command toggles multiline mode."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert tui.config.multiline_mode is False
        
        result = tui._handle_command("/multiline")
        assert result is True
        assert tui.config.multiline_mode is True
    
    def test_files_command(self):
        """Test /files command lists workspace files."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._workspace_files = ["test.py", "main.py"]
        result = tui._handle_command("/files")
        assert result is True
        assert "@test.py" in tui.messages[0].content
    
    def test_queue_command_empty(self):
        """Test /queue command with empty queue."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/queue")
        assert result is True
        assert "No prompts in queue" in tui.messages[0].content
    
    def test_queue_command_with_items(self):
        """Test /queue command with queued prompts."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._prompt_queue = ["First prompt", "Second prompt"]
        result = tui._handle_command("/queue")
        assert result is True
        assert "First prompt" in tui.messages[0].content


class TestQueueSystem:
    """Tests for prompt queue system."""
    
    def test_queue_initialization(self):
        """Test queue is initialized empty."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert tui._prompt_queue == []
    
    def test_queue_or_execute_when_not_processing(self):
        """Test _queue_or_execute executes immediately when not processing."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tui._processing = False
        
        # This would normally start background execution
        # Just test that it adds user message
        tui._queue_or_execute("test prompt")
        
        assert len(tui.messages) == 1
        assert tui.messages[0].role == "user"
        assert tui.messages[0].content == "test prompt"


class TestFileProcessing:
    """Tests for @file mention processing."""
    
    def test_process_file_mentions_no_mentions(self):
        """Test processing prompt with no @file mentions."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._process_file_mentions("Hello world")
        assert result == "Hello world"
    
    def test_process_file_mentions_with_mention(self):
        """Test processing prompt with @file mention."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        import tempfile
        import os
        
        tui = AsyncTUI()
        
        # Create a temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test content")
            temp_path = f.name
        
        try:
            tui.config.workspace = os.path.dirname(temp_path)
            filename = os.path.basename(temp_path)
            result = tui._process_file_mentions(f"Check @{filename}")
            assert "test content" in result
        finally:
            os.unlink(temp_path)


class TestWorkspaceScanning:
    """Tests for workspace file scanning."""
    
    def test_workspace_files_initialized(self):
        """Test workspace files list is initialized."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert isinstance(tui._workspace_files, list)
    
    def test_scan_workspace_limits_files(self):
        """Test workspace scanning limits files (may exceed slightly due to batch processing)."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        # Verify the limit is approximately enforced (may exceed slightly due to batch)
        assert len(tui._workspace_files) <= 1100  # Allow some margin


class TestToolLoading:
    """Tests for tool loading functionality."""
    
    def test_load_tools_returns_list(self):
        """Test _load_tools returns a list."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        tools = tui._load_tools()
        assert isinstance(tools, list)
    
    def test_load_tools_method_exists(self):
        """Test _load_tools method exists."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert hasattr(tui, '_load_tools')
        assert callable(tui._load_tools)


class TestNewSessionCommands:
    """Tests for session-related commands."""
    
    def test_sessions_command(self):
        """Test /sessions command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/sessions")
        assert result is True
        # Should have a message about sessions
        assert len(tui.messages) >= 1
    
    def test_continue_command(self):
        """Test /continue command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/continue")
        assert result is True
        assert len(tui.messages) >= 1
    
    def test_import_command_no_args(self):
        """Test /import command without arguments."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/import")
        assert result is True
        assert "Usage" in tui.messages[0].content
    
    def test_import_command_file_not_found(self):
        """Test /import command with non-existent file."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/import nonexistent_file.json")
        assert result is True
        assert "not found" in tui.messages[0].content.lower() or "failed" in tui.messages[0].content.lower()
    
    def test_status_command(self):
        """Test /status command."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        result = tui._handle_command("/status")
        assert result is True
        # Should show runtime status or "not initialized"
        assert len(tui.messages) >= 1


class TestRuntimeIntegration:
    """Tests for runtime integration."""
    
    def test_runtime_fields_initialized(self):
        """Test runtime fields are initialized."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert tui._runtime is None
        assert tui._runtime_started is False
    
    def test_start_runtime_method_exists(self):
        """Test _start_runtime method exists."""
        from praisonai.cli.interactive.async_tui import AsyncTUI
        
        tui = AsyncTUI()
        assert hasattr(tui, '_start_runtime')
        # It's an async method
        import asyncio
        assert asyncio.iscoroutinefunction(tui._start_runtime)

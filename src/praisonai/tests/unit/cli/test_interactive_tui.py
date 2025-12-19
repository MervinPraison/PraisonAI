"""
Tests for Interactive TUI System.

Test-Driven Development approach for interactive terminal interface.
"""

from pathlib import Path
import tempfile

from praisonai.cli.features.interactive_tui import (
    InteractiveConfig,
    CommandCompleter,
    HistoryManager,
    StatusDisplay,
    InteractiveSession,
    InteractiveTUIHandler,
)


# ============================================================================
# InteractiveConfig Tests
# ============================================================================

class TestInteractiveConfig:
    """Tests for InteractiveConfig."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = InteractiveConfig()
        
        assert config.prompt == ">>> "
        assert config.multiline is True
        assert config.enable_completions is True
        assert config.vi_mode is False
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = InteractiveConfig(
            prompt="$ ",
            multiline=False,
            vi_mode=True
        )
        
        assert config.prompt == "$ "
        assert config.multiline is False
        assert config.vi_mode is True


# ============================================================================
# CommandCompleter Tests
# ============================================================================

class TestCommandCompleter:
    """Tests for CommandCompleter."""
    
    def test_create_completer(self):
        """Test creating completer."""
        completer = CommandCompleter()
        assert completer is not None
    
    def test_add_commands(self):
        """Test adding commands."""
        completer = CommandCompleter()
        completer.add_commands(["help", "exit", "cost"])
        
        assert "help" in completer.commands
        assert "exit" in completer.commands
    
    def test_complete_slash_command(self):
        """Test completing slash commands."""
        completer = CommandCompleter(commands=["help", "history", "exit"])
        
        completions = completer.get_completions("/he", 3)
        
        assert "/help" in completions
        # /history should also match but may be filtered
        assert "/exit" not in completions
    
    def test_complete_file_mention(self):
        """Test completing file mentions."""
        completer = CommandCompleter()
        completer._file_cache = ["main.py", "config.py", "utils.py"]
        
        completions = completer.get_completions("@main", 5)
        
        assert "@main.py" in completions
    
    def test_add_symbols(self):
        """Test adding symbols."""
        completer = CommandCompleter()
        completer.add_symbols(["MyClass", "my_function"])
        
        assert "MyClass" in completer._symbol_cache
    
    def test_refresh_files(self):
        """Test refreshing file cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("# test")
            (Path(tmpdir) / "main.py").write_text("# main")
            
            completer = CommandCompleter()
            completer.refresh_files(Path(tmpdir))
            
            assert len(completer._file_cache) >= 2


# ============================================================================
# HistoryManager Tests
# ============================================================================

class TestHistoryManager:
    """Tests for HistoryManager."""
    
    def test_create_manager(self):
        """Test creating history manager."""
        manager = HistoryManager()
        assert manager is not None
    
    def test_add_entry(self):
        """Test adding history entry."""
        manager = HistoryManager()
        manager.add("first command")
        manager.add("second command")
        
        assert len(manager.get_all()) == 2
    
    def test_no_duplicate_consecutive(self):
        """Test no duplicate consecutive entries."""
        manager = HistoryManager()
        manager.add("same command")
        manager.add("same command")
        
        assert len(manager.get_all()) == 1
    
    def test_get_previous(self):
        """Test getting previous entry."""
        manager = HistoryManager()
        manager.add("first")
        manager.add("second")
        manager.add("third")
        
        assert manager.get_previous() == "third"
        assert manager.get_previous() == "second"
        assert manager.get_previous() == "first"
    
    def test_get_next(self):
        """Test getting next entry."""
        manager = HistoryManager()
        manager.add("first")
        manager.add("second")
        
        manager.get_previous()  # second
        manager.get_previous()  # first
        
        assert manager.get_next() == "second"
    
    def test_search(self):
        """Test searching history."""
        manager = HistoryManager()
        manager.add("/help")
        manager.add("/exit")
        manager.add("/help model")
        
        results = manager.search("/help")
        
        assert len(results) == 2
        assert "/help" in results
        assert "/help model" in results
    
    def test_clear(self):
        """Test clearing history."""
        manager = HistoryManager()
        manager.add("command")
        manager.clear()
        
        assert len(manager.get_all()) == 0
    
    def test_persistent_history(self):
        """Test persistent history file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = Path(tmpdir) / "history.txt"
            
            # Create and add entries
            manager1 = HistoryManager(history_file=str(history_file))
            manager1.add("command1")
            manager1.add("command2")
            
            # Create new manager with same file
            manager2 = HistoryManager(history_file=str(history_file))
            
            assert len(manager2.get_all()) == 2


# ============================================================================
# StatusDisplay Tests
# ============================================================================

class TestStatusDisplay:
    """Tests for StatusDisplay."""
    
    def test_create_display(self):
        """Test creating status display."""
        display = StatusDisplay()
        assert display is not None
    
    def test_set_status(self):
        """Test setting status."""
        display = StatusDisplay()
        display.set_status("model", "gpt-4o")
        
        assert display._status_items["model"] == "gpt-4o"
    
    def test_clear_status(self):
        """Test clearing status."""
        display = StatusDisplay()
        display.set_status("key", "value")
        display.clear_status("key")
        
        assert "key" not in display._status_items
    
    def test_print_welcome(self):
        """Test printing welcome message."""
        display = StatusDisplay()
        display._console = None  # Force no console
        
        # Should not raise without console
        display.print_welcome()
    
    def test_print_response(self):
        """Test printing response."""
        display = StatusDisplay()
        display._console = None  # Force no console
        
        display.print_response("Test response")
    
    def test_print_error(self):
        """Test printing error."""
        display = StatusDisplay()
        display._console = None  # Force no console
        
        display.print_error("Test error")


# ============================================================================
# InteractiveSession Tests
# ============================================================================

class TestInteractiveSession:
    """Tests for InteractiveSession."""
    
    def test_create_session(self):
        """Test creating session."""
        session = InteractiveSession()
        assert session is not None
    
    def test_create_session_with_config(self):
        """Test creating session with config."""
        config = InteractiveConfig(prompt="$ ")
        session = InteractiveSession(config=config)
        
        assert session.config.prompt == "$ "
    
    def test_add_commands(self):
        """Test adding commands."""
        session = InteractiveSession()
        session.add_commands(["help", "exit"])
        
        assert "help" in session.completer.commands
    
    def test_add_symbols(self):
        """Test adding symbols."""
        session = InteractiveSession()
        session.add_symbols(["MyClass"])
        
        assert "MyClass" in session.completer._symbol_cache
    
    def test_process_empty_input(self):
        """Test processing empty input."""
        session = InteractiveSession()
        result = session.process_input("")
        
        assert result is None
    
    def test_process_slash_command(self):
        """Test processing slash command."""
        command_called = []
        
        def on_command(cmd):
            command_called.append(cmd)
            return {"type": "help"}
        
        session = InteractiveSession(on_command=on_command)
        session.process_input("/help")
        
        assert len(command_called) == 1
        assert command_called[0] == "/help"
    
    def test_process_regular_input(self):
        """Test processing regular input."""
        input_received = []
        
        def on_input(text):
            input_received.append(text)
            return "Response"
        
        session = InteractiveSession(on_input=on_input)
        result = session.process_input("Hello world")
        
        assert len(input_received) == 1
        assert result == "Response"
    
    def test_exit_command_stops_session(self):
        """Test exit command stops session."""
        def on_command(cmd):
            return {"type": "exit"}
        
        session = InteractiveSession(on_command=on_command)
        session._running = True
        
        session.process_input("/exit")
        
        assert session._running is False
    
    def test_history_tracking(self):
        """Test that input is added to history."""
        session = InteractiveSession()
        session.process_input("test command")
        
        assert "test command" in session.history.get_all()
    
    def test_stop_session(self):
        """Test stopping session."""
        session = InteractiveSession()
        session._running = True
        
        session.stop()
        
        assert session._running is False


# ============================================================================
# InteractiveTUIHandler Tests
# ============================================================================

class TestInteractiveTUIHandler:
    """Tests for InteractiveTUIHandler."""
    
    def test_handler_creation(self):
        """Test handler creation."""
        handler = InteractiveTUIHandler()
        assert handler.feature_name == "interactive_tui"
    
    def test_initialize(self):
        """Test initializing handler."""
        handler = InteractiveTUIHandler()
        session = handler.initialize()
        
        assert session is not None
        assert handler.get_session() is session
    
    def test_initialize_with_config(self):
        """Test initializing with config."""
        handler = InteractiveTUIHandler()
        config = InteractiveConfig(prompt="$ ")
        
        session = handler.initialize(config=config)
        
        assert session.config.prompt == "$ "
    
    def test_initialize_with_callbacks(self):
        """Test initializing with callbacks."""
        handler = InteractiveTUIHandler()
        
        def on_input(text):
            return "response"
        
        def on_command(cmd):
            return {"type": "help"}
        
        session = handler.initialize(on_input=on_input, on_command=on_command)
        
        assert session.on_input is on_input
        assert session.on_command is on_command
    
    def test_stop(self):
        """Test stopping handler."""
        handler = InteractiveTUIHandler()
        handler.initialize()
        handler._session._running = True
        
        handler.stop()
        
        assert handler._session._running is False


# ============================================================================
# Integration Tests
# ============================================================================

class TestInteractiveTUIIntegration:
    """Integration tests for Interactive TUI."""
    
    def test_full_session_workflow(self):
        """Test full session workflow."""
        
        def on_input(text):
            return f"Echo: {text}"
        
        def on_command(cmd):
            if cmd == "/exit":
                return {"type": "exit"}
            return {"type": "command", "message": f"Executed: {cmd}"}
        
        handler = InteractiveTUIHandler()
        session = handler.initialize(on_input=on_input, on_command=on_command)
        
        # Process various inputs
        result1 = session.process_input("Hello")
        assert result1 == "Echo: Hello"
        
        result2 = session.process_input("/help")
        assert result2 == "Executed: /help"
        
        # Exit
        session.process_input("/exit")
        assert session._running is False
    
    def test_completion_integration(self):
        """Test completion integration."""
        handler = InteractiveTUIHandler()
        session = handler.initialize()
        
        # Add commands and symbols
        session.add_commands(["help", "exit", "cost"])
        session.add_symbols(["MyClass", "my_function"])
        
        # Test completions
        completions = session.completer.get_completions("/he", 3)
        assert "/help" in completions
        
        completions = session.completer.get_completions("My", 2)
        assert "MyClass" in completions
    
    def test_history_integration(self):
        """Test history integration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = Path(tmpdir) / "history.txt"
            
            config = InteractiveConfig(history_file=str(history_file))
            handler = InteractiveTUIHandler()
            session = handler.initialize(config=config)
            
            # Add some history
            session.process_input("command 1")
            session.process_input("command 2")
            
            # Check history
            history = session.history.get_all()
            assert "command 1" in history
            assert "command 2" in history

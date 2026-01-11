"""
Tests for PraisonIO - Interactive CLI I/O handler.
"""

from unittest.mock import patch


class TestIOConfig:
    """Tests for IOConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        from praisonai.cli.interactive.praison_io import IOConfig
        
        config = IOConfig()
        assert config.pretty is True
        assert config.user_input_color == "#00cc00"
        assert config.multiline_mode is False
        assert config.vi_mode is False
        assert config.enable_completions is True
    
    def test_custom_values(self):
        """Test custom configuration values."""
        from praisonai.cli.interactive.praison_io import IOConfig
        
        config = IOConfig(
            pretty=False,
            user_input_color="#ff0000",
            multiline_mode=True,
            vi_mode=True,
        )
        assert config.pretty is False
        assert config.user_input_color == "#ff0000"
        assert config.multiline_mode is True
        assert config.vi_mode is True


class TestPraisonCompleter:
    """Tests for PraisonCompleter."""
    
    def test_init_empty(self):
        """Test initialization with no commands."""
        from praisonai.cli.interactive.praison_io import PraisonCompleter
        
        completer = PraisonCompleter()
        assert completer.commands == {}
        assert len(completer.files) == 0
        assert len(completer.symbols) == 0
    
    def test_init_with_commands(self):
        """Test initialization with commands."""
        from praisonai.cli.interactive.praison_io import PraisonCompleter
        
        commands = {"help": "Show help", "exit": "Exit"}
        completer = PraisonCompleter(commands=commands)
        assert completer.commands == commands
    
    def test_add_files(self):
        """Test adding files."""
        from praisonai.cli.interactive.praison_io import PraisonCompleter
        
        completer = PraisonCompleter()
        completer.add_files(["file1.py", "file2.py"])
        assert "file1.py" in completer.files
        assert "file2.py" in completer.files
    
    def test_add_symbols(self):
        """Test adding symbols."""
        from praisonai.cli.interactive.praison_io import PraisonCompleter
        
        completer = PraisonCompleter()
        completer.add_symbols(["MyClass", "my_function"])
        assert "MyClass" in completer.symbols
        assert "my_function" in completer.symbols
    
    def test_get_completions_slash_commands(self):
        """Test completions for slash commands."""
        from praisonai.cli.interactive.praison_io import PraisonCompleter
        
        commands = {"help": "Show help", "history": "Show history", "exit": "Exit"}
        completer = PraisonCompleter(commands=commands)
        
        completions = completer.get_completions("/h", 2)
        completion_texts = [c[0] for c in completions]
        assert "/help" in completion_texts
        assert "/history" in completion_texts
        assert "/exit" not in completion_texts
    
    def test_get_completions_file_mentions(self):
        """Test completions for @ file mentions."""
        from praisonai.cli.interactive.praison_io import PraisonCompleter
        
        completer = PraisonCompleter()
        completer.add_files(["main.py", "test.py", "README.md"])
        
        completions = completer.get_completions("@main", 5)
        completion_texts = [c[0] for c in completions]
        assert "@main.py" in completion_texts
    
    def test_get_completions_symbols(self):
        """Test completions for symbols."""
        from praisonai.cli.interactive.praison_io import PraisonCompleter
        
        completer = PraisonCompleter()
        completer.add_symbols(["MyClass", "MyFunction", "other"])
        
        completions = completer.get_completions("My", 2)
        completion_texts = [c[0] for c in completions]
        assert "MyClass" in completion_texts
        assert "MyFunction" in completion_texts
        assert "other" not in completion_texts


class TestMarkdownStream:
    """Tests for MarkdownStream."""
    
    def test_init(self):
        """Test initialization."""
        from praisonai.cli.interactive.praison_io import MarkdownStream
        
        stream = MarkdownStream(live_window=8)
        assert stream.live_window == 8
        assert stream.printed == []
        assert stream.live is None
    
    def test_render_to_lines_fallback(self):
        """Test rendering without Rich."""
        from praisonai.cli.interactive.praison_io import MarkdownStream
        
        stream = MarkdownStream()
        # This tests the fallback path
        text = "Hello\nWorld"
        lines = stream._render_to_lines(text)
        assert len(lines) >= 1


class TestPraisonIO:
    """Tests for PraisonIO."""
    
    def test_init_default(self):
        """Test default initialization."""
        from praisonai.cli.interactive.praison_io import PraisonIO
        
        io = PraisonIO()
        assert io.config is not None
        assert io.completer is not None
    
    def test_init_with_config(self):
        """Test initialization with config."""
        from praisonai.cli.interactive.praison_io import PraisonIO, IOConfig
        
        config = IOConfig(pretty=False)
        io = PraisonIO(config=config)
        assert io.config.pretty is False
    
    def test_add_commands(self):
        """Test adding commands."""
        from praisonai.cli.interactive.praison_io import PraisonIO
        
        io = PraisonIO()
        io.add_commands({"test": "Test command"})
        assert "test" in io.completer.commands
    
    def test_add_files(self):
        """Test adding files."""
        from praisonai.cli.interactive.praison_io import PraisonIO
        
        io = PraisonIO()
        io.add_files(["file.py"])
        assert "file.py" in io.completer.files
    
    def test_add_symbols(self):
        """Test adding symbols."""
        from praisonai.cli.interactive.praison_io import PraisonIO
        
        io = PraisonIO()
        io.add_symbols(["MyClass"])
        assert "MyClass" in io.completer.symbols
    
    @patch('builtins.print')
    def test_rule_no_rich(self, mock_print):
        """Test rule without Rich."""
        from praisonai.cli.interactive.praison_io import PraisonIO, IOConfig
        
        config = IOConfig(pretty=False)
        io = PraisonIO(config=config)
        io.rule()
        mock_print.assert_called()
    
    @patch('builtins.print')
    def test_tool_output_no_rich(self, mock_print):
        """Test tool output without Rich."""
        from praisonai.cli.interactive.praison_io import PraisonIO, IOConfig
        
        config = IOConfig(pretty=False)
        io = PraisonIO(config=config)
        io.tool_output("Test message")
        mock_print.assert_called_with("⚙ Test message")
    
    @patch('builtins.print')
    def test_info_no_rich(self, mock_print):
        """Test info without Rich."""
        from praisonai.cli.interactive.praison_io import PraisonIO, IOConfig
        
        config = IOConfig(pretty=False)
        io = PraisonIO(config=config)
        io.info("Test info")
        mock_print.assert_called_with("ℹ Test info")
    
    @patch('builtins.print')
    def test_success_no_rich(self, mock_print):
        """Test success without Rich."""
        from praisonai.cli.interactive.praison_io import PraisonIO, IOConfig
        
        config = IOConfig(pretty=False)
        io = PraisonIO(config=config)
        io.success("Test success")
        mock_print.assert_called_with("✓ Test success")


class TestREPLConfig:
    """Tests for REPLConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        from praisonai.cli.interactive.repl import REPLConfig
        
        config = REPLConfig()
        assert config.model == "gpt-4o-mini"
        assert config.verbose is False
        assert config.memory is False
        assert config.tools is None
        assert config.autonomy is True
    
    def test_custom_values(self):
        """Test custom configuration values."""
        from praisonai.cli.interactive.repl import REPLConfig
        
        config = REPLConfig(
            model="gpt-4o",
            verbose=True,
            memory=True,
        )
        assert config.model == "gpt-4o"
        assert config.verbose is True
        assert config.memory is True


class TestInteractiveREPL:
    """Tests for InteractiveREPL."""
    
    def test_init_default(self):
        """Test default initialization."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        assert repl.config is not None
        assert repl.io is not None
        assert repl._running is False
    
    def test_init_with_config(self):
        """Test initialization with config."""
        from praisonai.cli.interactive.repl import InteractiveREPL, REPLConfig
        
        config = REPLConfig(model="gpt-4o")
        repl = InteractiveREPL(config=config)
        assert repl.config.model == "gpt-4o"
    
    def test_handle_command_exit(self):
        """Test handling exit command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        repl._running = True
        
        result = repl._handle_command("/exit")
        assert result is True
        assert repl._running is False
    
    def test_handle_command_quit(self):
        """Test handling quit command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        repl._running = True
        
        result = repl._handle_command("/quit")
        assert result is True
        assert repl._running is False
    
    def test_handle_command_help(self):
        """Test handling help command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        result = repl._handle_command("/help")
        assert result is True
    
    def test_handle_command_clear(self):
        """Test handling clear command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        repl._conversation_history = [{"role": "user", "content": "test"}]
        
        result = repl._handle_command("/clear")
        assert result is True
        assert len(repl._conversation_history) == 0
    
    def test_handle_command_model_show(self):
        """Test handling model command (show)."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        result = repl._handle_command("/model")
        assert result is True
    
    def test_handle_command_model_change(self):
        """Test handling model command (change)."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        result = repl._handle_command("/model gpt-4o")
        assert result is True
        assert repl.config.model == "gpt-4o"
    
    def test_handle_command_unknown(self):
        """Test handling unknown command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        result = repl._handle_command("/unknown")
        assert result is True  # Still handled (shows warning)
    
    def test_handle_command_session(self):
        """Test handling session command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        repl._session_id = "test-session-123"
        
        result = repl._handle_command("/session")
        assert result is True
    
    def test_handle_command_cost(self):
        """Test handling cost command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        repl._total_tokens = 100
        repl._total_cost = 0.01
        
        result = repl._handle_command("/cost")
        assert result is True
    
    def test_handle_command_history_empty(self):
        """Test handling history command with empty history."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        result = repl._handle_command("/history")
        assert result is True
    
    def test_handle_command_history_with_items(self):
        """Test handling history command with items."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        repl._conversation_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        result = repl._handle_command("/history")
        assert result is True
    
    def test_handle_command_compact(self):
        """Test handling compact command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        original = repl.io.config.pretty
        
        result = repl._handle_command("/compact")
        assert result is True
        assert repl.io.config.pretty != original
    
    def test_handle_command_multiline(self):
        """Test handling multiline command."""
        from praisonai.cli.interactive.repl import InteractiveREPL
        
        repl = InteractiveREPL()
        original = repl.io.config.multiline_mode
        
        result = repl._handle_command("/multiline")
        assert result is True
        assert repl.io.config.multiline_mode != original


class TestStartInteractive:
    """Tests for start_interactive function."""
    
    def test_function_exists(self):
        """Test that start_interactive function exists."""
        from praisonai.cli.interactive.repl import start_interactive
        assert callable(start_interactive)

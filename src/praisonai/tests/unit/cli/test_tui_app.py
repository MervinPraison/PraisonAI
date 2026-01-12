"""
Tests for PraisonAI TUI Application.
"""



class TestColorScheme:
    """Tests for ColorScheme dataclass."""
    
    def test_default_values(self):
        """Test default color scheme values."""
        from praisonai.cli.interactive.tui_app import ColorScheme
        
        colors = ColorScheme()
        assert colors.primary == "#00aaff"
        assert colors.secondary == "#888888"
        assert colors.accent == "#00cc00"
        assert colors.text == "#ffffff"
        assert colors.success == "#00cc00"
        assert colors.error == "#ff4444"


class TestTUIConfig:
    """Tests for TUIConfig dataclass."""
    
    def test_default_values(self):
        """Test default TUI configuration values."""
        from praisonai.cli.interactive.tui_app import TUIConfig
        
        config = TUIConfig()
        assert config.model == "gpt-4o-mini"
        assert config.show_logo is True
        assert config.show_tips is True
        assert config.show_status_bar is True
        assert config.compact_mode is False
        assert config.multiline is False
        assert config.vi_mode is False
    
    def test_custom_values(self):
        """Test custom TUI configuration values."""
        from praisonai.cli.interactive.tui_app import TUIConfig
        
        config = TUIConfig(
            model="gpt-4o",
            show_logo=False,
            compact_mode=True,
        )
        assert config.model == "gpt-4o"
        assert config.show_logo is False
        assert config.compact_mode is True


class TestMessage:
    """Tests for Message dataclass."""
    
    def test_message_creation(self):
        """Test message creation."""
        from praisonai.cli.interactive.tui_app import Message
        
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is not None
        assert msg.metadata == {}
    
    def test_message_with_metadata(self):
        """Test message with metadata."""
        from praisonai.cli.interactive.tui_app import Message
        
        msg = Message(role="assistant", content="Hi", metadata={"tokens": 10})
        assert msg.metadata == {"tokens": 10}


class TestGetLogo:
    """Tests for get_logo function."""
    
    def test_logo_wide_terminal(self):
        """Test logo for wide terminal."""
        from praisonai.cli.branding import get_logo, LOGO_LARGE
        
        logo = get_logo(100)
        assert logo == LOGO_LARGE
    
    def test_logo_medium_terminal(self):
        """Test logo for medium terminal."""
        from praisonai.cli.branding import get_logo, LOGO_MEDIUM
        
        logo = get_logo(65)
        assert logo == LOGO_MEDIUM
    
    def test_logo_narrow_terminal(self):
        """Test logo for narrow terminal."""
        from praisonai.cli.branding import get_logo, LOGO_SMALL
        
        logo = get_logo(30)
        assert logo == LOGO_SMALL


class TestPraisonTUI:
    """Tests for PraisonTUI class."""
    
    def test_init_default(self):
        """Test default initialization."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        assert tui.config is not None
        assert tui.messages == []
        assert tui._running is False
        assert tui.session_id is not None
    
    def test_init_with_config(self):
        """Test initialization with config."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, TUIConfig
        
        config = TUIConfig(model="gpt-4o", show_logo=False)
        tui = PraisonTUI(config=config)
        assert tui.config.model == "gpt-4o"
        assert tui.config.show_logo is False
    
    def test_render_logo_disabled(self):
        """Test render_logo when disabled."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, TUIConfig
        
        config = TUIConfig(show_logo=False)
        tui = PraisonTUI(config=config)
        
        logo = tui._render_logo()
        assert logo == ""
    
    def test_render_logo_enabled(self):
        """Test render_logo when enabled."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, TUIConfig
        
        config = TUIConfig(show_logo=True, model="gpt-4o-mini")
        tui = PraisonTUI(config=config)
        
        logo = tui._render_logo()
        assert "PRAISON" in logo or "gpt-4o-mini" in logo
    
    def test_render_welcome(self):
        """Test render_welcome."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, TUIConfig
        
        config = TUIConfig(show_logo=True, show_tips=True)
        tui = PraisonTUI(config=config)
        
        welcome = tui._render_welcome()
        assert "Type your message" in welcome or len(welcome) > 0
    
    def test_render_status_bar(self):
        """Test render_status_bar."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, TUIConfig
        
        config = TUIConfig(show_status_bar=True, model="gpt-4o")
        tui = PraisonTUI(config=config)
        
        status = tui._render_status_bar()
        assert "gpt-4o" in status
    
    def test_render_status_bar_disabled(self):
        """Test render_status_bar when disabled."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, TUIConfig
        
        config = TUIConfig(show_status_bar=False)
        tui = PraisonTUI(config=config)
        
        status = tui._render_status_bar()
        assert status == ""
    
    def test_format_message_user(self):
        """Test format_message for user role."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, Message
        
        tui = PraisonTUI()
        msg = Message(role="user", content="Hello")
        
        formatted = tui._format_message(msg)
        assert "Hello" in formatted
        assert "›" in formatted
    
    def test_format_message_assistant(self):
        """Test format_message for assistant role."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, Message
        
        tui = PraisonTUI()
        msg = Message(role="assistant", content="Hi there")
        
        formatted = tui._format_message(msg)
        assert "Hi there" in formatted
        assert "●" in formatted
    
    def test_format_message_tool(self):
        """Test format_message for tool role."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, Message
        
        tui = PraisonTUI()
        msg = Message(role="tool", content="Running command")
        
        formatted = tui._format_message(msg)
        assert "Running command" in formatted
        assert "⚙" in formatted
    
    def test_handle_command_exit(self):
        """Test handling exit command."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        tui._running = True
        
        result = tui._handle_command("/exit")
        assert result is True
        assert tui._running is False
    
    def test_handle_command_quit(self):
        """Test handling quit command."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        tui._running = True
        
        result = tui._handle_command("/quit")
        assert result is True
        assert tui._running is False
    
    def test_handle_command_help(self):
        """Test handling help command."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        result = tui._handle_command("/help")
        assert result is True
        # Help should add a system message
        assert len(tui.messages) == 1
        assert tui.messages[0].role == "system"
    
    def test_handle_command_clear(self):
        """Test handling clear command."""
        from praisonai.cli.interactive.tui_app import PraisonTUI, Message
        
        tui = PraisonTUI()
        tui.messages = [Message(role="user", content="test")]
        
        result = tui._handle_command("/clear")
        assert result is True
        assert len(tui.messages) == 0
    
    def test_handle_command_model_show(self):
        """Test handling model command (show)."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        result = tui._handle_command("/model")
        assert result is True
        assert len(tui.messages) == 1
        assert "gpt-4o-mini" in tui.messages[0].content
    
    def test_handle_command_model_change(self):
        """Test handling model command (change)."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        result = tui._handle_command("/model gpt-4o")
        assert result is True
        assert tui.config.model == "gpt-4o"
    
    def test_handle_command_cost(self):
        """Test handling cost command."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        tui._total_tokens = 100
        tui._total_cost = 0.01
        
        result = tui._handle_command("/cost")
        assert result is True
        assert len(tui.messages) == 1
        assert "100" in tui.messages[0].content
    
    def test_handle_command_compact(self):
        """Test handling compact command."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        original = tui.config.compact_mode
        
        result = tui._handle_command("/compact")
        assert result is True
        assert tui.config.compact_mode != original
    
    def test_handle_command_multiline(self):
        """Test handling multiline command."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        original = tui.config.multiline
        
        result = tui._handle_command("/multiline")
        assert result is True
        assert tui.config.multiline != original
    
    def test_handle_command_unknown(self):
        """Test handling unknown command."""
        from praisonai.cli.interactive.tui_app import PraisonTUI
        
        tui = PraisonTUI()
        result = tui._handle_command("/unknown")
        assert result is True
        assert len(tui.messages) == 1
        assert "Unknown" in tui.messages[0].content


class TestStartTUI:
    """Tests for start_tui function."""
    
    def test_function_exists(self):
        """Test that start_tui function exists."""
        from praisonai.cli.interactive.tui_app import start_tui
        assert callable(start_tui)


class TestASCIILogos:
    """Tests for ASCII logo constants."""
    
    def test_logo_large_exists(self):
        """Test LOGO_LARGE constant exists."""
        from praisonai.cli.branding import LOGO_LARGE
        assert len(LOGO_LARGE) > 0
        assert "PRAISON" in LOGO_LARGE or "██" in LOGO_LARGE
    
    def test_logo_small_exists(self):
        """Test LOGO_SMALL constant exists."""
        from praisonai.cli.branding import LOGO_SMALL
        assert len(LOGO_SMALL) > 0
    
    def test_logo_tiny_exists(self):
        """Test LOGO_MEDIUM constant exists (was LOGO_TINY)."""
        from praisonai.cli.branding import LOGO_MEDIUM
        assert len(LOGO_MEDIUM) > 0
    
    def test_logo_minimal_exists(self):
        """Test LOGO_MINIMAL constant exists."""
        from praisonai.cli.branding import LOGO_MINIMAL
        assert "Praison AI" in LOGO_MINIMAL

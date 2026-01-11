"""
Tests for PraisonAI Split-Pane TUI Application.
"""


class TestSplitTUIConfig:
    """Tests for SplitTUIConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        from praisonai.cli.interactive.split_tui import SplitTUIConfig
        
        config = SplitTUIConfig()
        assert config.model == "gpt-4o-mini"
        assert config.show_logo is True
        assert config.show_status_bar is True
        assert config.session_id is None
        assert config.workspace is None
    
    def test_custom_values(self):
        """Test custom configuration values."""
        from praisonai.cli.interactive.split_tui import SplitTUIConfig
        
        config = SplitTUIConfig(
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
        from praisonai.cli.interactive.split_tui import ChatMessage
        
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is not None
    
    def test_message_roles(self):
        """Test different message roles."""
        from praisonai.cli.interactive.split_tui import ChatMessage
        
        roles = ["user", "assistant", "system", "status"]
        for role in roles:
            msg = ChatMessage(role=role, content="test")
            assert msg.role == role


class TestGetLogo:
    """Tests for get_logo function."""
    
    def test_logo_wide_terminal(self):
        """Test logo for wide terminal."""
        from praisonai.cli.interactive.split_tui import get_logo, LOGO
        
        logo = get_logo(100)
        assert logo == LOGO
    
    def test_logo_medium_terminal(self):
        """Test logo for medium terminal."""
        from praisonai.cli.interactive.split_tui import get_logo, LOGO_SMALL
        
        logo = get_logo(50)
        assert logo == LOGO_SMALL
    
    def test_logo_narrow_terminal(self):
        """Test logo for narrow terminal."""
        from praisonai.cli.interactive.split_tui import get_logo, LOGO_MINIMAL
        
        logo = get_logo(30)
        assert logo == LOGO_MINIMAL
    
    def test_logo_contains_praison_ai(self):
        """Test that logo contains 'Praison AI' branding."""
        from praisonai.cli.interactive.split_tui import LOGO_MINIMAL
        
        assert "Praison AI" in LOGO_MINIMAL


class TestSplitTUI:
    """Tests for SplitTUI class."""
    
    def test_init_default(self):
        """Test default initialization."""
        from praisonai.cli.interactive.split_tui import SplitTUI
        
        tui = SplitTUI()
        assert tui.config is not None
        assert tui.messages == []
        assert tui._running is False
        assert tui.session_id is not None
    
    def test_init_with_config(self):
        """Test initialization with config."""
        from praisonai.cli.interactive.split_tui import SplitTUI, SplitTUIConfig
        
        config = SplitTUIConfig(model="gpt-4o", show_logo=False)
        tui = SplitTUI(config=config)
        assert tui.config.model == "gpt-4o"
        assert tui.config.show_logo is False
    
    def test_format_output_empty(self):
        """Test format_output with no messages."""
        from praisonai.cli.interactive.split_tui import SplitTUI, SplitTUIConfig
        
        config = SplitTUIConfig(show_logo=True)
        tui = SplitTUI(config=config)
        
        output = tui._format_output()
        # Should contain welcome message
        assert "Type your message" in output or "gpt-4o-mini" in output
    
    def test_format_output_with_messages(self):
        """Test format_output with messages."""
        from praisonai.cli.interactive.split_tui import SplitTUI, ChatMessage
        
        tui = SplitTUI()
        tui.messages = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there"),
        ]
        
        output = tui._format_output()
        assert "Hello" in output
        assert "Hi there" in output
    
    def test_handle_command_exit(self):
        """Test handling exit command."""
        from praisonai.cli.interactive.split_tui import SplitTUI
        
        tui = SplitTUI()
        tui._running = True
        
        result = tui._handle_command("/exit")
        assert result is True
        assert tui._running is False
    
    def test_handle_command_quit(self):
        """Test handling quit command."""
        from praisonai.cli.interactive.split_tui import SplitTUI
        
        tui = SplitTUI()
        tui._running = True
        
        result = tui._handle_command("/quit")
        assert result is True
        assert tui._running is False
    
    def test_handle_command_help(self):
        """Test handling help command."""
        from praisonai.cli.interactive.split_tui import SplitTUI
        
        tui = SplitTUI()
        result = tui._handle_command("/help")
        assert result is True
        assert len(tui.messages) == 1
        assert tui.messages[0].role == "system"
        assert "/help" in tui.messages[0].content
    
    def test_handle_command_clear(self):
        """Test handling clear command."""
        from praisonai.cli.interactive.split_tui import SplitTUI, ChatMessage
        
        tui = SplitTUI()
        tui.messages = [ChatMessage(role="user", content="test")]
        
        result = tui._handle_command("/clear")
        assert result is True
        assert len(tui.messages) == 0
    
    def test_handle_command_new(self):
        """Test handling new command."""
        from praisonai.cli.interactive.split_tui import SplitTUI, ChatMessage
        
        tui = SplitTUI()
        old_session = tui.session_id
        tui.messages = [ChatMessage(role="user", content="test")]
        
        result = tui._handle_command("/new")
        assert result is True
        assert len(tui.messages) == 1  # New session message
        assert tui.session_id != old_session
    
    def test_handle_command_model_show(self):
        """Test handling model command (show)."""
        from praisonai.cli.interactive.split_tui import SplitTUI
        
        tui = SplitTUI()
        result = tui._handle_command("/model")
        assert result is True
        assert len(tui.messages) == 1
        assert "gpt-4o-mini" in tui.messages[0].content
    
    def test_handle_command_model_change(self):
        """Test handling model command (change)."""
        from praisonai.cli.interactive.split_tui import SplitTUI
        
        tui = SplitTUI()
        result = tui._handle_command("/model gpt-4o")
        assert result is True
        assert tui.config.model == "gpt-4o"
        assert tui._agent is None  # Agent should be reset
    
    def test_handle_command_unknown(self):
        """Test handling unknown command."""
        from praisonai.cli.interactive.split_tui import SplitTUI
        
        tui = SplitTUI()
        result = tui._handle_command("/unknown")
        assert result is True
        assert len(tui.messages) == 1
        assert "Unknown" in tui.messages[0].content


class TestStartSplitTUI:
    """Tests for start_split_tui function."""
    
    def test_function_exists(self):
        """Test that start_split_tui function exists."""
        from praisonai.cli.interactive.split_tui import start_split_tui
        assert callable(start_split_tui)


class TestASCIILogos:
    """Tests for ASCII logo constants."""
    
    def test_logo_exists(self):
        """Test LOGO constant exists and has content."""
        from praisonai.cli.interactive.split_tui import LOGO
        assert len(LOGO) > 0
        assert "██" in LOGO  # Contains block characters
    
    def test_logo_small_exists(self):
        """Test LOGO_SMALL constant exists."""
        from praisonai.cli.interactive.split_tui import LOGO_SMALL
        assert len(LOGO_SMALL) > 0
    
    def test_logo_minimal_branding(self):
        """Test LOGO_MINIMAL has correct branding."""
        from praisonai.cli.interactive.split_tui import LOGO_MINIMAL
        assert "Praison AI" in LOGO_MINIMAL


class TestMessageFormatting:
    """Tests for message formatting."""
    
    def test_user_message_prefix(self):
        """Test user messages have correct prefix."""
        from praisonai.cli.interactive.split_tui import SplitTUI, ChatMessage
        
        tui = SplitTUI()
        tui.messages = [ChatMessage(role="user", content="test")]
        
        output = tui._format_output()
        assert "› test" in output
    
    def test_assistant_message_prefix(self):
        """Test assistant messages have correct prefix."""
        from praisonai.cli.interactive.split_tui import SplitTUI, ChatMessage
        
        tui = SplitTUI()
        tui.messages = [ChatMessage(role="assistant", content="response")]
        
        output = tui._format_output()
        assert "● response" in output
    
    def test_status_message_prefix(self):
        """Test status messages have correct prefix."""
        from praisonai.cli.interactive.split_tui import SplitTUI, ChatMessage
        
        tui = SplitTUI()
        tui.messages = [ChatMessage(role="status", content="thinking")]
        
        output = tui._format_output()
        assert "⏳ thinking" in output

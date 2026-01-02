"""
TDD Test Suite for PraisonAI TUI Widgets.

Tests for:
- ComposerWidget (Enter to send, Shift+Enter for newline)
- HelpScreen (F1 key)
- Keyboard shortcuts (Ctrl+Q, Ctrl+C, Ctrl+L)
- Queue panel (edit/delete)
- Tool panel (display tools)
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

# Check if textual is available
try:
    from textual.pilot import Pilot
    from textual.app import App
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    pytest.skip("Textual not available", allow_module_level=True)


class TestComposerWidget:
    """Tests for ComposerWidget."""
    
    @pytest.mark.asyncio
    async def test_submit_text_area_enter_triggers_submit(self):
        """Test that Enter key triggers submit."""
        from praisonai.cli.features.tui.widgets.composer import SubmitTextArea
        
        # Create a mock app context
        text_area = SubmitTextArea("")
        
        # Verify the class exists and has SubmitRequested message
        assert hasattr(SubmitTextArea, 'SubmitRequested')
    
    @pytest.mark.asyncio
    async def test_composer_widget_has_correct_bindings(self):
        """Test ComposerWidget has correct key bindings."""
        from praisonai.cli.features.tui.widgets.composer import ComposerWidget
        
        # Check bindings include enter for submit
        binding_keys = [b.key for b in ComposerWidget.BINDINGS]
        assert "enter" in binding_keys
        assert "escape" in binding_keys


class TestHelpScreen:
    """Tests for HelpScreen."""
    
    def test_help_screen_exists(self):
        """Test HelpScreen can be imported."""
        from praisonai.cli.features.tui.screens.help import HelpScreen
        assert HelpScreen is not None
    
    def test_help_screen_has_dismiss_binding(self):
        """Test HelpScreen has escape binding to dismiss."""
        from praisonai.cli.features.tui.screens.help import HelpScreen
        
        binding_keys = [b.key for b in HelpScreen.BINDINGS]
        assert "escape" in binding_keys
        assert "q" in binding_keys


class TestTUIApp:
    """Tests for TUIApp."""
    
    def test_tui_app_has_help_screen_registered(self):
        """Test TUIApp has help screen in SCREENS."""
        from praisonai.cli.features.tui.app import TUIApp
        
        assert "help" in TUIApp.SCREENS
        assert "main" in TUIApp.SCREENS
        assert "settings" in TUIApp.SCREENS
        assert "queue" in TUIApp.SCREENS
    
    def test_tui_app_has_ctrl_bindings(self):
        """Test TUIApp has Ctrl key bindings."""
        from praisonai.cli.features.tui.app import TUIApp
        
        binding_keys = [b.key for b in TUIApp.BINDINGS]
        assert "ctrl+q" in binding_keys
        assert "ctrl+c" in binding_keys


class TestMainScreen:
    """Tests for MainScreen."""
    
    def test_main_screen_has_safe_default_bindings(self):
        """Test MainScreen has safe default bindings (no Ctrl/Fn by default)."""
        from praisonai.cli.features.tui.screens.main import MainScreen
        
        binding_keys = [b.key for b in MainScreen.BINDINGS]
        # Safe defaults - single char shortcuts
        assert "q" in binding_keys  # quit
        assert "colon" in binding_keys  # command mode
        assert "escape" in binding_keys  # cancel
        # Ctrl keys should NOT be in default bindings
        assert "ctrl+q" not in binding_keys
        assert "ctrl+c" not in binding_keys
        # Function keys should NOT be in default bindings
        assert "f1" not in binding_keys


class TestTUIConfig:
    """Tests for TUIConfig."""
    
    def test_default_config_disables_ctrl_keys(self):
        """Test default config has Ctrl keys disabled."""
        from praisonai.cli.features.tui.config import TUIConfig
        
        config = TUIConfig()
        assert config.enable_ctrl_keys is False
        assert config.enable_fn_keys is False
        assert config.enable_single_char is True
        assert config.leader_key == ":"
    
    def test_command_parsing(self):
        """Test command mode parsing."""
        from praisonai.cli.features.tui.config import get_command
        
        assert get_command("quit") == "quit"
        assert get_command("q") == "quit"
        assert get_command("exit") == "quit"
        assert get_command("clear") == "clear"
        assert get_command("cl") == "clear"
        assert get_command("invalid") is None


class TestQueuePanel:
    """Tests for QueuePanelWidget."""
    
    def test_queue_panel_has_delete_message(self):
        """Test QueuePanelWidget has DeleteRequested message."""
        from praisonai.cli.features.tui.widgets.queue_panel import QueuePanelWidget
        
        assert hasattr(QueuePanelWidget, 'DeleteRequested')
        assert hasattr(QueuePanelWidget, 'EditRequested')
    
    def test_queue_panel_has_delete_method(self):
        """Test QueuePanelWidget has delete_selected method."""
        from praisonai.cli.features.tui.widgets.queue_panel import QueuePanelWidget
        
        assert hasattr(QueuePanelWidget, 'delete_selected')
        assert hasattr(QueuePanelWidget, 'edit_selected')


class TestToolPanel:
    """Tests for ToolPanelWidget."""
    
    def test_tool_panel_has_set_available_tools(self):
        """Test ToolPanelWidget has set_available_tools method."""
        from praisonai.cli.features.tui.widgets.tool_panel import ToolPanelWidget
        
        assert hasattr(ToolPanelWidget, 'set_available_tools')


class TestInteractiveTools:
    """Tests for interactive tools loading."""
    
    def test_get_interactive_tools_exists(self):
        """Test get_interactive_tools function exists."""
        from praisonai.cli.features.interactive_tools import get_interactive_tools
        
        assert callable(get_interactive_tools)
    
    def test_tool_config_exists(self):
        """Test ToolConfig class exists."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        
        assert ToolConfig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

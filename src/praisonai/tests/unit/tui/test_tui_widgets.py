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


class TestCommandPopup:
    """Tests for CommandPopupWidget."""
    
    def test_command_popup_exists(self):
        """Test CommandPopupWidget can be imported."""
        from praisonai.cli.features.tui.widgets.command_popup import CommandPopupWidget
        assert CommandPopupWidget is not None
    
    def test_command_info_dataclass(self):
        """Test CommandInfo dataclass works correctly."""
        from praisonai.cli.features.tui.widgets.command_popup import CommandInfo
        
        cmd = CommandInfo(
            name="test",
            description="Test command",
            aliases=["t", "tst"]
        )
        assert cmd.name == "test"
        assert cmd.description == "Test command"
        assert cmd.aliases == ["t", "tst"]
        assert cmd.display_name == "test (t, tst)"
    
    def test_get_default_commands(self):
        """Test get_default_commands returns command list."""
        from praisonai.cli.features.tui.widgets.command_popup import get_default_commands
        
        commands = get_default_commands()
        assert len(commands) > 0
        
        # Check for essential commands
        command_names = [c.name for c in commands]
        assert "help" in command_names
        assert "exit" in command_names
        assert "clear" in command_names
        assert "model" in command_names
    
    def test_command_popup_has_messages(self):
        """Test CommandPopupWidget has required message classes."""
        from praisonai.cli.features.tui.widgets.command_popup import CommandPopupWidget
        
        assert hasattr(CommandPopupWidget, 'CommandSelected')
        assert hasattr(CommandPopupWidget, 'Dismissed')


class TestMainScreenBackslash:
    """Tests for MainScreen backslash command support."""
    
    def test_main_screen_has_backslash_binding(self):
        """Test MainScreen has backslash binding for commands."""
        from praisonai.cli.features.tui.screens.main import MainScreen
        
        binding_keys = [b.key for b in MainScreen.BINDINGS]
        assert "backslash" in binding_keys
    
    def test_main_screen_has_show_commands_action(self):
        """Test MainScreen has action_show_commands method."""
        from praisonai.cli.features.tui.screens.main import MainScreen
        
        assert hasattr(MainScreen, 'action_show_commands')
    
    def test_main_screen_has_command_popup_handlers(self):
        """Test MainScreen has command popup event handlers."""
        from praisonai.cli.features.tui.screens.main import MainScreen
        
        assert hasattr(MainScreen, 'on_command_popup_widget_command_selected')
        assert hasattr(MainScreen, 'on_command_popup_widget_dismissed')


class TestAutoTriggerEvents:
    """Tests for auto-trigger events (backslash, @, /)."""
    
    def test_composer_has_backslash_typed_message(self):
        """Test ComposerWidget has BackslashTyped message."""
        from praisonai.cli.features.tui.widgets.composer import ComposerWidget
        
        assert hasattr(ComposerWidget, 'BackslashTyped')
    
    def test_composer_has_at_typed_message(self):
        """Test ComposerWidget has AtTyped message for @ file autocomplete."""
        from praisonai.cli.features.tui.widgets.composer import ComposerWidget
        
        assert hasattr(ComposerWidget, 'AtTyped')
    
    def test_composer_has_slash_typed_message(self):
        """Test ComposerWidget has SlashTyped message for / commands."""
        from praisonai.cli.features.tui.widgets.composer import ComposerWidget
        
        assert hasattr(ComposerWidget, 'SlashTyped')
    
    def test_main_screen_has_auto_trigger_handlers(self):
        """Test MainScreen has auto-trigger event handlers."""
        from praisonai.cli.features.tui.screens.main import MainScreen
        
        assert hasattr(MainScreen, 'on_composer_widget_backslash_typed')
        assert hasattr(MainScreen, 'on_composer_widget_at_typed')
        assert hasattr(MainScreen, 'on_composer_widget_slash_typed')


class TestFilePopup:
    """Tests for FilePopupWidget."""
    
    def test_file_popup_exists(self):
        """Test FilePopupWidget can be imported."""
        from praisonai.cli.features.tui.widgets.file_popup import FilePopupWidget
        assert FilePopupWidget is not None
    
    def test_file_popup_has_messages(self):
        """Test FilePopupWidget has required message classes."""
        from praisonai.cli.features.tui.widgets.file_popup import FilePopupWidget
        
        assert hasattr(FilePopupWidget, 'FileSelected')
        assert hasattr(FilePopupWidget, 'Dismissed')
    
    def test_file_info_dataclass(self):
        """Test FileInfo dataclass works correctly."""
        from praisonai.cli.features.tui.widgets.file_popup import FileInfo
        
        file_info = FileInfo(path="test.py", file_type="file")
        assert file_info.path == "test.py"
        assert file_info.file_type == "file"
        assert file_info.icon == "📄 "
        
        dir_info = FileInfo(path="src/", file_type="directory")
        assert dir_info.icon == "📁 "
    
    def test_main_screen_has_file_popup_handlers(self):
        """Test MainScreen has file popup event handlers."""
        from praisonai.cli.features.tui.screens.main import MainScreen
        
        assert hasattr(MainScreen, 'on_file_popup_widget_file_selected')
        assert hasattr(MainScreen, 'on_file_popup_widget_dismissed')
        assert hasattr(MainScreen, '_show_file_popup')
        assert hasattr(MainScreen, '_dismiss_file_popup')


class TestQueueLiveUpdates:
    """Tests for queue panel live updates."""
    
    def test_app_has_update_queue_panel_live(self):
        """Test TUIApp has _update_queue_panel_live method."""
        from praisonai.cli.features.tui.app import TUIApp
        
        assert hasattr(TUIApp, '_update_queue_panel_live')
    
    def test_queue_panel_has_reactive_counts(self):
        """Test QueuePanelWidget has reactive count properties."""
        from praisonai.cli.features.tui.widgets.queue_panel import QueuePanelWidget
        
        # Check reactive properties exist
        assert hasattr(QueuePanelWidget, 'queued_count')
        assert hasattr(QueuePanelWidget, 'running_count')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

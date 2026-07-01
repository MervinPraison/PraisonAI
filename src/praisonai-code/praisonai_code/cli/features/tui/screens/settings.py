"""
Settings Screen for PraisonAI TUI.

Configuration interface.
"""

from typing import Optional

try:
    from textual.screen import Screen
    from textual.containers import Vertical
    from textual.widgets import Static, Footer, Input, Select, Switch, Button
    from textual.binding import Binding
    from textual.message import Message
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Screen = object
    Message = object


if TEXTUAL_AVAILABLE:
    class SettingsScreen(Screen):
        """
        Settings screen.
        
        Allows configuration of:
        - Model selection
        - Queue settings
        - Display preferences
        """
        
        BINDINGS = [
            Binding("escape", "back", "Back", show=True),
            Binding("s", "save", "Save", show=True),
        ]
        
        DEFAULT_CSS = """
        SettingsScreen {
            background: $surface;
        }
        
        SettingsScreen #settings-header {
            height: 3;
            background: $primary;
            padding: 1;
        }
        
        SettingsScreen .setting-row {
            height: 3;
            padding: 0 1;
        }
        
        SettingsScreen .setting-label {
            width: 20;
        }
        
        SettingsScreen Input {
            width: 40;
        }
        """
        
        class SettingsSaved(Message):
            def __init__(self, settings: dict):
                self.settings = settings
                super().__init__()
        
        def __init__(
            self,
            current_settings: Optional[dict] = None,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._settings = current_settings or {}
        
        def compose(self):
            """Compose the screen."""
            yield Static("Settings", id="settings-header")
            
            with Vertical(id="settings-form"):
                # Model setting
                yield Static("Model:", classes="setting-label")
                yield Input(
                    value=self._settings.get("model", "gpt-4o-mini"),
                    id="setting-model",
                    placeholder="Model name"
                )
                
                # Max concurrent runs
                yield Static("Max Concurrent:", classes="setting-label")
                yield Input(
                    value=str(self._settings.get("max_concurrent", 4)),
                    id="setting-max-concurrent",
                    placeholder="4"
                )
                
                # Auto-save interval
                yield Static("Autosave (sec):", classes="setting-label")
                yield Input(
                    value=str(self._settings.get("autosave_interval", 30)),
                    id="setting-autosave",
                    placeholder="30"
                )
                
                # Buttons
                yield Button("Save", id="btn-save", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="default")
            
            yield Footer()
        
        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Handle button press."""
            if event.button.id == "btn-save":
                self.action_save()
            elif event.button.id == "btn-cancel":
                self.action_back()
        
        def action_back(self) -> None:
            """Go back."""
            self.app.pop_screen()
        
        def action_save(self) -> None:
            """Save settings."""
            try:
                model_input = self.query_one("#setting-model", Input)
                max_concurrent_input = self.query_one("#setting-max-concurrent", Input)
                autosave_input = self.query_one("#setting-autosave", Input)
                
                settings = {
                    "model": model_input.value,
                    "max_concurrent": int(max_concurrent_input.value or "4"),
                    "autosave_interval": int(autosave_input.value or "30"),
                }
                
                self.post_message(self.SettingsSaved(settings))
                self.app.pop_screen()
            except ValueError:
                pass

else:
    class SettingsScreen:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )

"""
Textual frontend for InteractiveCore.

This frontend provides a full-screen TUI using Textual framework.
"""

import logging
from typing import Optional

from ..core import InteractiveCore
from ..config import InteractiveConfig
from ..events import (
    InteractiveEvent,
    InteractiveEventType,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalDecision,
)

logger = logging.getLogger(__name__)


class TextualFrontend:
    """
    Textual TUI frontend for interactive mode.
    
    This is used by `praisonai tui launch`.
    
    Note: This is a thin adapter that bridges InteractiveCore events
    to the existing TUIApp. The actual Textual widgets are in tui/app.py.
    """
    
    def __init__(self, core: Optional[InteractiveCore] = None, config: Optional[InteractiveConfig] = None):
        """Initialize the Textual frontend.
        
        Args:
            core: InteractiveCore instance. If None, creates one.
            config: Configuration. Used if core is None.
        """
        self.core = core or InteractiveCore(config=config)
        self._app = None
        
        # Subscribe to events
        self.core.subscribe(self._handle_event)
    
    def _handle_event(self, event: InteractiveEvent) -> None:
        """Handle events from InteractiveCore."""
        # Forward events to the Textual app if running
        if self._app is not None:
            self._forward_to_app(event)
    
    def _forward_to_app(self, event: InteractiveEvent) -> None:
        """Forward event to Textual app."""
        # This will be implemented when integrating with existing TUIApp
        pass
    
    async def run(self) -> None:
        """Run the Textual TUI."""
        try:
            from ..features.tui.app import TUIApp
            
            # Create app with our core
            self._app = TUIApp(
                interactive_core=self.core,
                session_id=self.core.current_session_id,
                model=self.core.config.model,
            )
            
            await self._app.run_async()
            
        except ImportError as e:
            logger.error(f"Textual not available: {e}")
            print("Error: Textual TUI requires 'textual' package.")
            print("Install with: pip install praisonai[tui]")
    
    def stop(self) -> None:
        """Stop the TUI."""
        if self._app:
            self._app.exit()


class ApprovalDialog:
    """
    Approval dialog for Textual TUI.
    
    This provides the same approval options as the Rich frontend:
    - Allow once
    - Always allow this pattern
    - Always allow for this session
    - Reject
    """
    
    def __init__(self, request: ApprovalRequest):
        """Initialize the approval dialog.
        
        Args:
            request: The approval request to display.
        """
        self.request = request
        self.response: Optional[ApprovalResponse] = None
    
    def compose(self):
        """Compose the dialog widgets (for Textual)."""
        try:
            from textual.containers import Vertical, Horizontal
            from textual.widgets import Static, Button
            
            yield Vertical(
                Static(f"[bold]Approval Required[/bold]", id="title"),
                Static(f"\n{self.request.description}\n"),
                Static(f"Tool: {self.request.tool_name}"),
                Static(f"Action: {self.request.action_type}\n"),
                Horizontal(
                    Button("Allow Once", id="once", variant="primary"),
                    Button("Always Allow", id="always", variant="success"),
                    Button("Session Only", id="session", variant="default"),
                    Button("Reject", id="reject", variant="error"),
                    id="buttons"
                ),
                id="approval-dialog"
            )
        except ImportError:
            pass
    
    def on_button_pressed(self, button_id: str) -> ApprovalResponse:
        """Handle button press.
        
        Args:
            button_id: ID of the pressed button.
        
        Returns:
            ApprovalResponse based on the button pressed.
        """
        pattern = f"{self.request.action_type}:*"
        
        if button_id == "once":
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.ONCE
            )
        elif button_id == "always":
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.ALWAYS,
                remember_pattern=pattern
            )
        elif button_id == "session":
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.ALWAYS_SESSION,
                remember_pattern=pattern
            )
        else:  # reject
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.REJECT
            )

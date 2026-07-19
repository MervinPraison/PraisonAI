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
    derive_permission_pattern,
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
            from praisonai_code._wrapper_bridge import import_wrapper_module

            TUIApp = import_wrapper_module("praisonai.cli.features.tui.app").TUIApp
            
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
    - Always allow this command (narrow, command-scoped pattern)
    - Always allow this command for this session
    - Always allow ALL uses of the tool (explicit blanket pattern)
    - Reject
    """
    
    def __init__(self, request: ApprovalRequest):
        """Initialize the approval dialog.
        
        Args:
            request: The approval request to display.
        """
        self.request = request
        self.response: Optional[ApprovalResponse] = None
        # Derive both patterns once so the label shown and the pattern stored
        # for a given decision are guaranteed identical.
        self._narrow_pattern = derive_permission_pattern(request, scope="command")
        self._blanket_pattern = derive_permission_pattern(request, scope="tool")
    
    def compose(self):
        """Compose the dialog widgets (for Textual)."""
        try:
            from textual.containers import Vertical, Horizontal
            from textual.widgets import Static, Button
            
            narrow_pattern = self._narrow_pattern
            blanket_pattern = self._blanket_pattern

            yield Vertical(
                Static("[bold]Approval Required[/bold]", id="title"),
                Static(f"\n{self.request.description}\n"),
                Static(f"Tool: {self.request.tool_name}"),
                Static(f"Action: {self.request.action_type}\n"),
                Horizontal(
                    Button("Allow Once", id="once", variant="primary"),
                    Button(f"Always Allow This Command ({narrow_pattern})", id="always", variant="success"),
                    Button(f"Session Only ({narrow_pattern})", id="session", variant="default"),
                    Button(f"Always Allow All ({blanket_pattern})", id="always_tool", variant="warning"),
                    Button("Reject", id="reject", variant="error"),
                    id="buttons"
                ),
                id="approval-dialog"
            )
        except ImportError:
            pass
    
    def on_button_pressed(self, button_id: str, reason: Optional[str] = None) -> ApprovalResponse:
        """Handle button press.
        
        Args:
            button_id: ID of the pressed button.
            reason: Optional one-line denial reason captured from the user to
                steer the agent when the ``reject`` button is pressed. Empty or
                ``None`` preserves today's plain-denial behaviour.
        
        Returns:
            ApprovalResponse based on the button pressed.
        """
        # "Always allow" defaults to the narrowest reasonable command-scoped
        # pattern; the blanket ``action_type:*`` grant is a separate, explicit
        # choice so a single benign approval never whitelists an entire tool.
        narrow_pattern = self._narrow_pattern

        if button_id == "once":
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.ONCE
            )
        elif button_id == "always":
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.ALWAYS,
                remember_pattern=narrow_pattern
            )
        elif button_id == "session":
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.ALWAYS_SESSION,
                remember_pattern=narrow_pattern
            )
        elif button_id == "always_tool":
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.ALWAYS,
                remember_pattern=self._blanket_pattern
            )
        else:  # reject
            return ApprovalResponse(
                request_id=self.request.request_id,
                decision=ApprovalDecision.REJECT,
                reason=(reason.strip() or None) if reason else None,
            )

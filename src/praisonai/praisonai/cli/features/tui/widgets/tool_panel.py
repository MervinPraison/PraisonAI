"""
Tool Panel Widget for PraisonAI TUI.

Displays tool execution status and approval dialogs.
"""

from typing import List, Optional
from dataclasses import dataclass, field
import time

try:
    from textual.widget import Widget
    from textual.widgets import Static, ListView, ListItem
    from textual.containers import Vertical
    from textual.reactive import reactive
    from textual.message import Message
    from rich.text import Text
    from rich.panel import Panel
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Widget = object
    Message = object


@dataclass
class ToolCall:
    """A tool call for display."""
    call_id: str
    tool_name: str
    args_preview: str
    status: str  # "pending", "running", "completed", "failed", "approved", "rejected"
    result_preview: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    requires_approval: bool = False


if TEXTUAL_AVAILABLE:
    class ToolPanelWidget(Vertical):
        """
        Tool panel widget.
        
        Displays:
        - Recent tool calls
        - Tool execution status
        - Approval requests
        """
        
        DEFAULT_CSS = """
        ToolPanelWidget {
            height: 100%;
            border: solid $accent;
            background: $surface;
            padding: 0 1;
        }
        
        ToolPanelWidget .tool-header {
            height: 1;
            background: $accent;
            padding: 0 1;
        }
        
        ToolPanelWidget .tool-pending {
            color: $warning;
        }
        
        ToolPanelWidget .tool-running {
            color: $primary;
        }
        
        ToolPanelWidget .tool-completed {
            color: $success;
        }
        
        ToolPanelWidget .tool-failed {
            color: $error;
        }
        
        ToolPanelWidget .tool-approval {
            background: $warning-darken-2;
            border: solid $warning;
            padding: 1;
        }
        """
        
        class ApprovalResponse(Message):
            """Event when user responds to approval request."""
            def __init__(self, call_id: str, approved: bool):
                self.call_id = call_id
                self.approved = approved
                super().__init__()
        
        def __init__(
            self,
            max_items: int = 50,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._calls: List[ToolCall] = []
            self._max_items = max_items
            self._pending_approval: Optional[ToolCall] = None
        
        def compose(self):
            """Compose the widget."""
            yield Static("Tools", id="tool-title", classes="tool-header")
            yield Vertical(id="tool-list")
        
        def on_mount(self) -> None:
            """Handle mount."""
            self._update_display()
        
        def add_call(self, call: ToolCall) -> None:
            """Add a tool call."""
            self._calls.append(call)
            
            # Trim old calls
            if len(self._calls) > self._max_items:
                self._calls = self._calls[-self._max_items:]
            
            # Check for approval
            if call.requires_approval and call.status == "pending":
                self._pending_approval = call
            
            self._update_display()
        
        def update_call(self, call_id: str, status: str, result: Optional[str] = None) -> None:
            """Update a tool call status."""
            for call in self._calls:
                if call.call_id == call_id:
                    call.status = status
                    if result:
                        call.result_preview = result[:100]
                    if status in ("completed", "failed"):
                        call.ended_at = time.time()
                    break
            
            # Clear pending approval if this was it
            if self._pending_approval and self._pending_approval.call_id == call_id:
                self._pending_approval = None
            
            self._update_display()
        
        def _update_display(self) -> None:
            """Update the display."""
            try:
                container = self.query_one("#tool-list", Vertical)
            except Exception:
                return
            
            # Clear existing
            container.remove_children()
            
            # Show pending approval first
            if self._pending_approval:
                approval_text = Text()
                approval_text.append("⚠ Approval Required\n", style="bold yellow")
                approval_text.append(f"Tool: {self._pending_approval.tool_name}\n")
                approval_text.append(f"Args: {self._pending_approval.args_preview}\n")
                approval_text.append("[Y] Approve  [N] Reject", style="dim")
                
                container.mount(Static(
                    Panel(approval_text, border_style="yellow"),
                    classes="tool-approval"
                ))
            
            # Show recent calls
            for call in reversed(self._calls[-10:]):
                if call == self._pending_approval:
                    continue
                
                # Status icon
                status_icons = {
                    "pending": "⏳",
                    "running": "⟳",
                    "completed": "✓",
                    "failed": "✗",
                    "approved": "✓",
                    "rejected": "✗",
                }
                icon = status_icons.get(call.status, "?")
                
                # Status style
                status_styles = {
                    "pending": "yellow",
                    "running": "cyan",
                    "completed": "green",
                    "failed": "red",
                    "approved": "green",
                    "rejected": "red",
                }
                style = status_styles.get(call.status, "")
                
                text = Text()
                text.append(f"{icon} ", style=style)
                text.append(call.tool_name, style="bold")
                
                if call.result_preview:
                    text.append(f" → {call.result_preview[:30]}...", style="dim")
                
                container.mount(Static(text, classes=f"tool-{call.status}"))
        
        def handle_approval_key(self, key: str) -> bool:
            """
            Handle approval key press.
            
            Returns True if handled.
            """
            if not self._pending_approval:
                return False
            
            if key.lower() == "y":
                self.post_message(self.ApprovalResponse(
                    self._pending_approval.call_id,
                    approved=True
                ))
                self.update_call(self._pending_approval.call_id, "approved")
                return True
            elif key.lower() == "n":
                self.post_message(self.ApprovalResponse(
                    self._pending_approval.call_id,
                    approved=False
                ))
                self.update_call(self._pending_approval.call_id, "rejected")
                return True
            
            return False
        
        @property
        def has_pending_approval(self) -> bool:
            """Check if there's a pending approval."""
            return self._pending_approval is not None
        
        def clear(self) -> None:
            """Clear all tool calls."""
            self._calls.clear()
            self._pending_approval = None
            self._update_display()

else:
    class ToolPanelWidget:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )

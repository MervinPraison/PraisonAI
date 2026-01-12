"""
PraisonAI Split-Pane TUI Application.

Full-screen terminal UI with:
- Fixed bottom input pane (always visible)
- Scrollable top output pane
- Direct response (no streaming - faster)
- Activity indicators showing agent status

Uses prompt_toolkit Application for true split-pane layout.
"""

import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from datetime import datetime

# ============================================================================
# Branding - Import from unified source
# ============================================================================

from praisonai.cli.branding import get_logo, get_version


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class SplitTUIConfig:
    """Configuration for the Split TUI application."""
    model: str = "gpt-4o-mini"
    show_logo: bool = True
    show_status_bar: bool = True
    session_id: Optional[str] = None
    workspace: Optional[str] = None
    history_file: Optional[str] = None


# ============================================================================
# Message Types
# ============================================================================

@dataclass
class ChatMessage:
    """A chat message."""
    role: str  # "user", "assistant", "system", "status"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


# ============================================================================
# Split TUI Application
# ============================================================================

class SplitTUI:
    """
    Split-pane TUI with fixed bottom input and scrollable top output.
    
    Key features:
    - Input box ALWAYS visible at bottom
    - Output scrolls above independently
    - Direct response (no streaming) for speed
    - Activity indicators during processing
    """
    
    def __init__(self, config: Optional[SplitTUIConfig] = None):
        self.config = config or SplitTUIConfig()
        self.messages: List[ChatMessage] = []
        self._running = False
        self._agent = None
        self._processing = False
        self._status_text = ""
        
        # Terminal size
        self.term_width, self.term_height = shutil.get_terminal_size((80, 24))
        
        # Session ID
        import uuid
        self.session_id = self.config.session_id or str(uuid.uuid4())[:8]
    
    def _get_agent(self):
        """Lazy-load the agent with verbose=False for no streaming."""
        if self._agent is None:
            try:
                from praisonaiagents import Agent
                
                self._agent = Agent(
                    name="Praison",
                    role="AI Assistant",
                    goal="Help the user with their requests",
                    instructions="You are Praison AI, a helpful assistant. Be concise and helpful.",
                    llm=self.config.model,
                )
            except ImportError as e:
                raise RuntimeError(f"Failed to import praisonaiagents: {e}")
        
        return self._agent
    
    def _format_output(self) -> str:
        """Format all messages for the output pane."""
        lines = []
        
        # Logo
        if self.config.show_logo and not self.messages:
            logo = get_logo(self.term_width)
            lines.append(logo.strip())
            lines.append("")
            lines.append(f"  v{get_version()} · Model: {self.config.model}")
            lines.append("")
            lines.append("  Type your message and press Enter. Use /help for commands.")
            lines.append("")
        
        # Messages
        for msg in self.messages:
            if msg.role == "user":
                lines.append(f"› {msg.content}")
                lines.append("")
            elif msg.role == "assistant":
                lines.append(f"● {msg.content}")
                lines.append("")
            elif msg.role == "system":
                lines.append(f"  {msg.content}")
                lines.append("")
            elif msg.role == "status":
                lines.append(f"  ⏳ {msg.content}")
        
        # Processing indicator
        if self._processing:
            lines.append(f"  ⏳ {self._status_text}")
        
        return "\n".join(lines)
    
    def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower().lstrip("/")
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in ("exit", "quit", "q"):
            self._running = False
            return True
        
        elif cmd == "help":
            help_text = """Available Commands:
  /help          Show this help
  /exit, /quit   Exit Praison AI
  /clear         Clear conversation
  /model [name]  Show or change model
  /new           Start new conversation"""
            self.messages.append(ChatMessage(role="system", content=help_text))
            return True
        
        elif cmd == "clear":
            self.messages.clear()
            return True
        
        elif cmd == "new":
            self.messages.clear()
            import uuid
            self.session_id = str(uuid.uuid4())[:8]
            self.messages.append(ChatMessage(role="system", content=f"New session: {self.session_id}"))
            return True
        
        elif cmd == "model":
            if args:
                self.config.model = args
                self._agent = None
                self.messages.append(ChatMessage(role="system", content=f"Model changed to: {args}"))
            else:
                self.messages.append(ChatMessage(role="system", content=f"Current model: {self.config.model}"))
            return True
        
        else:
            self.messages.append(ChatMessage(role="system", content=f"Unknown command: /{cmd}. Use /help for available commands."))
            return True
    
    def _execute_prompt(self, prompt: str) -> Optional[str]:
        """Execute a prompt and return the response (direct, no streaming)."""
        import sys
        import io
        
        try:
            agent = self._get_agent()
            
            # Suppress agent's Rich output by redirecting stdout/stderr
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            
            try:
                response = agent.start(prompt)
            finally:
                # Restore stdout/stderr
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
            return str(response) if response else None
        except Exception as e:
            return f"Error: {e}"
    
    def _run_with_status(self, prompt: str) -> Optional[str]:
        """Run prompt with status updates."""
        self._processing = True
        self._status_text = "Praison AI is thinking..."
        
        # Execute in background
        result = [None]
        error = [None]
        
        def execute():
            try:
                result[0] = self._execute_prompt(prompt)
            except Exception as e:
                error[0] = str(e)
        
        thread = threading.Thread(target=execute)
        thread.start()
        
        # Update status while waiting
        start_time = time.time()
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        
        while thread.is_alive():
            elapsed = time.time() - start_time
            self._status_text = f"{spinner[idx]} Praison AI is thinking... ({elapsed:.1f}s)"
            idx = (idx + 1) % len(spinner)
            time.sleep(0.1)
        
        thread.join()
        self._processing = False
        self._status_text = ""
        
        if error[0]:
            return f"Error: {error[0]}"
        return result[0]
    
    def run(self) -> None:
        """Run the split-pane TUI."""
        self._running = True
        
        # Try to use prompt_toolkit for better experience
        try:
            self._run_with_prompt_toolkit()
        except ImportError:
            # Fallback to simple mode
            self._run_simple()
    
    def _run_simple(self) -> None:
        """Simple fallback mode without prompt_toolkit."""
        # Print welcome
        print(self._format_output())
        
        while self._running:
            try:
                # Status bar
                if self.config.show_status_bar:
                    status = f" ? for help | {self.config.model} | Session: {self.session_id} "
                    print(f"\033[90m{status}\033[0m")
                
                # Get input
                user_input = input("› ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    # Print system messages
                    for msg in self.messages:
                        if msg.role == "system":
                            print(f"  {msg.content}")
                    self.messages = [m for m in self.messages if m.role != "system"]
                    continue
                
                # Add user message
                self.messages.append(ChatMessage(role="user", content=user_input))
                
                # Execute with status
                print("  ⏳ Praison AI is thinking...")
                response = self._execute_prompt(user_input)
                
                if response:
                    self.messages.append(ChatMessage(role="assistant", content=response))
                    print(f"\n● {response}\n")
                
            except KeyboardInterrupt:
                print("\n  Use /exit to quit")
            except EOFError:
                self._running = False
        
        print("\n  Goodbye from Praison AI!")
    
    def _run_with_prompt_toolkit(self) -> None:
        """Run with prompt_toolkit for split-pane layout."""
        from prompt_toolkit import Application
        from prompt_toolkit.buffer import Buffer
        from prompt_toolkit.layout.containers import HSplit, VSplit, Window
        from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
        from prompt_toolkit.layout.layout import Layout
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.styles import Style
        from prompt_toolkit.history import FileHistory
        
        # Setup history
        history_file = self.config.history_file or str(Path.home() / ".praison" / "history")
        Path(history_file).parent.mkdir(parents=True, exist_ok=True)
        
        # Output buffer (read-only, for displaying conversation)
        output_text = [self._format_output()]
        
        def get_output_text():
            return output_text[0]
        
        # Input buffer
        input_buffer = Buffer(
            multiline=False,
            history=FileHistory(history_file),
        )
        
        # Key bindings
        kb = KeyBindings()
        
        @kb.add("enter")
        def handle_enter(event):
            user_input = input_buffer.text.strip()
            if not user_input:
                return
            
            input_buffer.reset()
            
            # Handle commands
            if user_input.startswith("/"):
                self._handle_command(user_input)
                output_text[0] = self._format_output()
                return
            
            # Add user message
            self.messages.append(ChatMessage(role="user", content=user_input))
            
            # Show processing status
            self.messages.append(ChatMessage(role="status", content="Praison AI is thinking..."))
            output_text[0] = self._format_output()
            
            # Execute (this blocks but that's OK for direct response)
            response = self._execute_prompt(user_input)
            
            # Remove status message
            self.messages = [m for m in self.messages if m.role != "status"]
            
            if response:
                self.messages.append(ChatMessage(role="assistant", content=response))
            
            output_text[0] = self._format_output()
        
        @kb.add("c-c")
        def handle_ctrl_c(event):
            input_buffer.reset()
        
        @kb.add("c-d")
        def handle_ctrl_d(event):
            if not input_buffer.text:
                self._running = False
                event.app.exit()
        
        @kb.add("c-q")
        def handle_ctrl_q(event):
            self._running = False
            event.app.exit()
        
        # Style
        style = Style.from_dict({
            "output-area": "bg:#0d0d0d",
            "input-area": "bg:#1a1a1a",
            "status-bar": "bg:#333333 #888888",
            "prompt": "#00aaff bold",
        })
        
        # Status bar text
        def get_status_bar():
            left = "? for help"
            center = self.config.model
            right = f"Session: {self.session_id}"
            return f" {left}  |  {center}  |  {right} "
        
        # Layout: Output (top, scrollable) + Status bar + Input (bottom, fixed)
        layout = Layout(
            HSplit([
                # Output area (takes remaining space)
                Window(
                    content=FormattedTextControl(get_output_text),
                    wrap_lines=True,
                    style="class:output-area",
                ),
                # Status bar (1 line)
                Window(
                    content=FormattedTextControl(get_status_bar),
                    height=1,
                    style="class:status-bar",
                ),
                # Input area (fixed at bottom, 3 lines for visibility)
                HSplit([
                    Window(height=1),  # Spacer
                    VSplit([
                        Window(
                            content=FormattedTextControl([("class:prompt", "› ")]),
                            width=2,
                        ),
                        Window(
                            content=BufferControl(buffer=input_buffer),
                            wrap_lines=True,
                        ),
                    ]),
                    Window(height=1),  # Spacer
                ], height=3, style="class:input-area"),
            ])
        )
        
        # Create application
        app = Application(
            layout=layout,
            key_bindings=kb,
            style=style,
            full_screen=True,
            mouse_support=True,
        )
        
        # Run
        app.run()
        
        print("\n  Goodbye from Praison AI!")
    
    def run_single(self, prompt: str) -> Optional[str]:
        """Run a single prompt (non-interactive)."""
        return self._execute_prompt(prompt)


def start_split_tui(
    model: str = "gpt-4o-mini",
    show_logo: bool = True,
    **kwargs
) -> None:
    """Start the split-pane TUI application."""
    config = SplitTUIConfig(
        model=model,
        show_logo=show_logo,
    )
    
    tui = SplitTUI(config=config)
    tui.run()

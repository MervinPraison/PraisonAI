"""
Interactive Replay Player for PraisonAI.

Provides step-through replay of context traces with keyboard navigation.
"""

from datetime import datetime

from .reader import ContextTraceReader


class ReplayPlayer:
    """
    Interactive replay player for context traces.
    
    Allows stepping through context events with keyboard navigation.
    
    Usage:
        reader = ContextTraceReader("my-session")
        player = ReplayPlayer(reader)
        player.run()
        
    Navigation:
        Enter/Down: Next event
        Up: Previous event
        g <num>: Go to event number
        q/Ctrl+C: Quit
    """
    
    def __init__(
        self,
        reader: ContextTraceReader,
        use_rich: bool = True,
        full_mode: bool = False,
    ):
        """
        Initialize the player.
        
        Args:
            reader: ContextTraceReader with loaded events
            use_rich: Whether to use Rich for formatting (if available)
            full_mode: Whether to show full content without truncation
        """
        self._reader = reader
        self._use_rich = use_rich
        self._full_mode = full_mode
        self._current_index = 0
        self._events = reader.get_all()
        
        # Try to import Rich for better formatting
        self._console = None
        if use_rich:
            try:
                from rich.console import Console
                from rich.panel import Panel
                from rich.table import Table
                self._console = Console()
                self._Panel = Panel
                self._Table = Table
            except ImportError:
                self._use_rich = False
    
    def _format_timestamp(self, timestamp: float) -> str:
        """Format timestamp for display."""
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except Exception:
            return str(timestamp)
    
    def _get_event_type_display(self, event) -> str:
        """Get display string for event type."""
        if hasattr(event, 'event_type'):
            et = event.event_type
            if hasattr(et, 'value'):
                return et.value.upper().replace('_', ' ')
            return str(et).upper().replace('_', ' ')
        elif isinstance(event, dict):
            return event.get('event_type', 'UNKNOWN').upper().replace('_', ' ')
        return 'UNKNOWN'
    
    def _display_event_rich(self, event, index: int) -> None:
        """Display event using Rich formatting."""
        if not self._console:
            return self._display_event_plain(event, index)
        
        # Build header
        event_type = self._get_event_type_display(event)
        agent_name = getattr(event, 'agent_name', None) or (event.get('agent_name') if isinstance(event, dict) else None)
        timestamp = getattr(event, 'timestamp', 0) or (event.get('timestamp', 0) if isinstance(event, dict) else 0)
        
        header = f"[bold cyan]Event {index + 1}/{len(self._events)}[/bold cyan]"
        if agent_name:
            header += f" | [bold green]Agent: {agent_name}[/bold green]"
        
        # Build content
        content_lines = [
            f"[bold]Type:[/bold] {event_type}",
            f"[bold]Time:[/bold] {self._format_timestamp(timestamp)}",
            f"[bold]Session:[/bold] {self._reader.session_id}",
        ]
        
        # Add context state if available
        messages_count = getattr(event, 'messages_count', 0) or (event.get('messages_count', 0) if isinstance(event, dict) else 0)
        tokens_used = getattr(event, 'tokens_used', 0) or (event.get('tokens_used', 0) if isinstance(event, dict) else 0)
        tokens_budget = getattr(event, 'tokens_budget', 0) or (event.get('tokens_budget', 0) if isinstance(event, dict) else 0)
        
        if messages_count or tokens_used:
            content_lines.append("")
            content_lines.append("[bold]Context State:[/bold]")
            if messages_count:
                content_lines.append(f"  Messages: {messages_count}")
            if tokens_used:
                budget_str = f" / {tokens_budget:,}" if tokens_budget else ""
                content_lines.append(f"  Tokens: {tokens_used:,}{budget_str}")
        
        # Add token/cost info if available
        prompt_tokens = getattr(event, 'prompt_tokens', 0) or (event.get('prompt_tokens', 0) if isinstance(event, dict) else 0)
        completion_tokens = getattr(event, 'completion_tokens', 0) or (event.get('completion_tokens', 0) if isinstance(event, dict) else 0)
        cost_usd = getattr(event, 'cost_usd', 0) or (event.get('cost_usd', 0) if isinstance(event, dict) else 0)
        
        if prompt_tokens or completion_tokens or cost_usd:
            content_lines.append("")
            content_lines.append("[bold]Token/Cost Info:[/bold]")
            if prompt_tokens:
                content_lines.append(f"  Prompt Tokens: {prompt_tokens:,}")
            if completion_tokens:
                content_lines.append(f"  Completion Tokens: {completion_tokens:,}")
            if cost_usd:
                content_lines.append(f"  Cost: ${cost_usd:.6f}")
        
        # Add event data if available
        data = getattr(event, 'data', {}) or (event.get('data', {}) if isinstance(event, dict) else {})
        if data:
            content_lines.append("")
            content_lines.append("[bold]Event Data:[/bold]")
            for key, value in data.items():
                if value is not None:
                    value_str = str(value)
                    # Use full_mode to control truncation - None means no limit
                    if not self._full_mode:
                        max_len = 100
                        if len(value_str) > max_len:
                            value_str = value_str[:max_len] + "..."
                    content_lines.append(f"  {key}: {value_str}")
        
        content = "\n".join(content_lines)
        
        # Display panel
        self._console.clear()
        self._console.print(self._Panel(
            content,
            title=header,
            border_style="blue",
        ))
        
        # Navigation help
        self._console.print("\n[dim][Enter/↓] Next  [↑] Previous  [g N] Go to N  [q] Quit[/dim]")
    
    def _display_event_plain(self, event, index: int) -> None:
        """Display event using plain text."""
        print("\n" + "=" * 60)
        print(f"Event {index + 1}/{len(self._events)}")
        print("=" * 60)
        
        event_type = self._get_event_type_display(event)
        agent_name = getattr(event, 'agent_name', None) or (event.get('agent_name') if isinstance(event, dict) else None)
        timestamp = getattr(event, 'timestamp', 0) or (event.get('timestamp', 0) if isinstance(event, dict) else 0)
        
        print(f"Type: {event_type}")
        print(f"Time: {self._format_timestamp(timestamp)}")
        if agent_name:
            print(f"Agent: {agent_name}")
        print(f"Session: {self._reader.session_id}")
        
        # Context state
        messages_count = getattr(event, 'messages_count', 0) or (event.get('messages_count', 0) if isinstance(event, dict) else 0)
        tokens_used = getattr(event, 'tokens_used', 0) or (event.get('tokens_used', 0) if isinstance(event, dict) else 0)
        tokens_budget = getattr(event, 'tokens_budget', 0) or (event.get('tokens_budget', 0) if isinstance(event, dict) else 0)
        
        if messages_count or tokens_used:
            print("\nContext State:")
            if messages_count:
                print(f"  Messages: {messages_count}")
            if tokens_used:
                budget_str = f" / {tokens_budget:,}" if tokens_budget else ""
                print(f"  Tokens: {tokens_used:,}{budget_str}")
        
        # Token/cost info
        prompt_tokens = getattr(event, 'prompt_tokens', 0) or (event.get('prompt_tokens', 0) if isinstance(event, dict) else 0)
        completion_tokens = getattr(event, 'completion_tokens', 0) or (event.get('completion_tokens', 0) if isinstance(event, dict) else 0)
        cost_usd = getattr(event, 'cost_usd', 0) or (event.get('cost_usd', 0) if isinstance(event, dict) else 0)
        
        if prompt_tokens or completion_tokens or cost_usd:
            print("\nToken/Cost Info:")
            if prompt_tokens:
                print(f"  Prompt Tokens: {prompt_tokens:,}")
            if completion_tokens:
                print(f"  Completion Tokens: {completion_tokens:,}")
            if cost_usd:
                print(f"  Cost: ${cost_usd:.6f}")
        
        # Event data
        data = getattr(event, 'data', {}) or (event.get('data', {}) if isinstance(event, dict) else {})
        if data:
            print("\nEvent Data:")
            for key, value in data.items():
                if value is not None:
                    value_str = str(value)
                    # Use full_mode to control truncation - None means no limit
                    if not self._full_mode:
                        max_len = 100
                        if len(value_str) > max_len:
                            value_str = value_str[:max_len] + "..."
                    print(f"  {key}: {value_str}")
        
        print("\n[Enter/Down] Next  [Up] Previous  [g N] Go to N  [q] Quit")
    
    def display_current(self) -> None:
        """Display the current event."""
        if not self._events:
            print("No events to display.")
            return
        
        event = self._events[self._current_index]
        
        if self._use_rich and self._console:
            self._display_event_rich(event, self._current_index)
        else:
            self._display_event_plain(event, self._current_index)
    
    def next(self) -> bool:
        """Move to next event. Returns False if at end."""
        if self._current_index < len(self._events) - 1:
            self._current_index += 1
            return True
        return False
    
    def previous(self) -> bool:
        """Move to previous event. Returns False if at start."""
        if self._current_index > 0:
            self._current_index -= 1
            return True
        return False
    
    def goto(self, index: int) -> bool:
        """Go to specific event index (0-based). Returns False if invalid."""
        if 0 <= index < len(self._events):
            self._current_index = index
            return True
        return False
    
    def run(self) -> None:
        """Run the interactive replay loop."""
        if not self._events:
            print(f"No events found in trace: {self._reader.session_id}")
            return
        
        print(f"Replaying {len(self._events)} events from session: {self._reader.session_id}")
        print("Press Enter to start...")
        
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            return
        
        while True:
            self.display_current()
            
            try:
                user_input = input("\n> ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting replay.")
                break
            
            if user_input in ('q', 'quit', 'exit'):
                print("Exiting replay.")
                break
            elif user_input in ('', 'n', 'next', 'down'):
                if not self.next():
                    print("End of trace reached.")
            elif user_input in ('p', 'prev', 'previous', 'up'):
                if not self.previous():
                    print("Already at start of trace.")
            elif user_input.startswith('g ') or user_input.startswith('goto '):
                try:
                    parts = user_input.split()
                    if len(parts) >= 2:
                        index = int(parts[1]) - 1  # Convert to 0-based
                        if not self.goto(index):
                            print(f"Invalid event number. Valid range: 1-{len(self._events)}")
                except ValueError:
                    print("Invalid number. Usage: g <event_number>")
            elif user_input == 'h' or user_input == 'help':
                print("\nCommands:")
                print("  Enter/n/down - Next event")
                print("  p/up - Previous event")
                print("  g <N> - Go to event N")
                print("  q - Quit")
            else:
                # Default to next on any other input
                if not self.next():
                    print("End of trace reached.")
    
    @property
    def current_index(self) -> int:
        """Get current event index."""
        return self._current_index
    
    @property
    def total_events(self) -> int:
        """Get total number of events."""
        return len(self._events)

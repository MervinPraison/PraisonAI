"""
Editor-Style Output Mode for PraisonAI Agents.

Provides a user-friendly display format with:
- Numbered steps: Step 1: 📄 Creating file: /path
- Human-readable tool names (not technical names)
- Smart result formatting (JSON → summary, exit → ✓ Done)
- Completion summary with duration and block count

Usage:
    # Via preset:
    agent = Agent(output="editor")

    # Programmatic:
    from praisonaiagents.output.editor import enable_editor_output
    enable_editor_output()
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# Module-level state (same pattern as status.py)
# ─────────────────────────────────────────────────────────────────────────────
_editor_output_enabled = False
_editor_output: Optional['EditorOutput'] = None


class BlockType(Enum):
    """Types of display blocks."""
    NARRATIVE = "narrative"
    COMMAND = "command"
    SUMMARY = "summary"
    ACTION = "action"
    CODE = "code"
    LIST = "list"


@dataclass
class DisplayBlock:
    """A single display block."""
    type: BlockType
    content: str
    title: Optional[str] = None
    items: List[str] = field(default_factory=list)
    output: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# Human-readable tool name mappings
TOOL_LABELS: Dict[str, tuple] = {
    # Web / search
    'internet_search': ('🔍', 'Searching the web'),
    'search_web': ('🔍', 'Searching the web'),
    'web_search': ('🔍', 'Searching the web'),
    # File operations
    'read_file': ('📖', 'Reading file'),
    'write_file': ('📝', 'Writing file'),
    'create_file': ('📄', 'Creating file'),
    'acp_create_file': ('📄', 'Creating file'),
    'acp_edit_file': ('✏️', 'Editing file'),
    'acp_delete_file': ('🗑️', 'Deleting file'),
    # Execution
    'execute_command': ('⚡', 'Running command'),
    'acp_execute_command': ('⚡', 'Running command'),
    # Directory
    'list_files': ('📂', 'Listing files'),
    'get_system_info': ('💻', 'Getting system info'),
    # LSP
    'lsp_get_diagnostics': ('🔬', 'Analyzing code'),
    'lsp_list_symbols': ('🔎', 'Finding code symbols'),
    'lsp_find_definition': ('📍', 'Finding definition'),
    'lsp_find_references': ('🔗', 'Finding references'),
}


class EditorOutput:
    """
    User-friendly display for agent output.

    Renders tool calls as numbered steps with emoji icons and
    human-readable labels. Formats results smartly (JSON → summary).

    Thread-safe for multi-agent execution.
    """

    def __init__(self, console=None, use_rich: bool = True, agent_name: Optional[str] = None):
        self._use_rich = use_rich
        self._console = console
        self._blocks: List[DisplayBlock] = []
        self._start_time = time.time()
        self._step_count = 0
        self._llm_call_count = 0
        self._lock = threading.Lock()
        self._agent_name = agent_name  # For multi-agent prefix support
        self._multi_agent_mode = False  # Set True when multiple agents detected

        if use_rich and console is None:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                self._use_rich = False

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def tool_call(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        result: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> None:
        """Display a tool call as a numbered step with emoji."""
        with self._lock:
            self._step_count += 1
            step_num = self._step_count

        # Get human-readable label
        icon, label = TOOL_LABELS.get(tool_name, ('🔧', f'Using {tool_name}'))

        # Format action description with step number and context
        step_prefix = f"Step {step_num}: "
        action = self._format_action(step_prefix, icon, label, args)

        # Format result for display
        display_result = self._format_result(result)

        self._add_block(BlockType.COMMAND, action, output=display_result)
        self._render_command(action, display_result)

    def llm_indicator(self, phase: str = "thinking") -> None:
        """Display a subtle LLM activity indicator between steps."""
        if self._use_rich:
            self._console.print(f"[dim]▸ {phase.capitalize()}...[/dim]")
        else:
            print(f"▸ {phase.capitalize()}...")

    def output(self, content: str, agent_name: Optional[str] = None) -> None:
        """Display final agent output."""
        if self._use_rich:
            self._console.print()
            self._console.print(content)
            self._console.print()
        else:
            print()
            print(content)
            print()

    def summary(self, title: str, items: Optional[List[str]] = None) -> None:
        """Display completion summary."""
        self._add_block(BlockType.SUMMARY, "", title=title, items=items or [])
        self._render_summary(title, items)

    def elapsed_time(self) -> float:
        """Get elapsed time since display started."""
        return time.time() - self._start_time

    def get_blocks(self) -> List[DisplayBlock]:
        """Get all display blocks."""
        with self._lock:
            return self._blocks.copy()

    def set_agent_name(self, name: str) -> None:
        """Set the agent name for multi-agent prefix."""
        with self._lock:
            self._agent_name = name

    def enable_multi_agent_mode(self) -> None:
        """Enable multi-agent mode to show agent prefixes."""
        with self._lock:
            self._multi_agent_mode = True

    def _get_prefix(self, agent_name: Optional[str] = None) -> str:
        """Get the agent prefix for multi-agent mode."""
        if not self._multi_agent_mode:
            return ""
        name = agent_name or self._agent_name
        if name:
            return f"[{name}] "
        return ""

    # ─────────────────────────────────────────────────────────────────────
    # Additional display methods (merged from CLI EditorDisplay)
    # ─────────────────────────────────────────────────────────────────────

    def narrative(self, text: str, agent_name: Optional[str] = None) -> None:
        """
        Display a narrative block (agent thinking/explanation).
        
        Args:
            text: The narrative text
            agent_name: Optional agent name for multi-agent prefix
        """
        if not text or not text.strip():
            return
        self._add_block(BlockType.NARRATIVE, text)
        prefix = self._get_prefix(agent_name)
        if self._use_rich:
            self._console.print(f"{prefix}{text}")
        else:
            print(f"{prefix}{text}")

    def code(self, code: str, language: str = "") -> None:
        """
        Display a code block.
        
        Args:
            code: The code content
            language: Programming language for syntax highlighting
        """
        self._add_block(BlockType.CODE, code, metadata={"language": language})
        if self._use_rich:
            try:
                from rich.syntax import Syntax
                syntax = Syntax(code, language or "text", theme="monokai")
                self._console.print(syntax)
            except ImportError:
                self._console.print(f"```{language}\n{code}\n```")
        else:
            print(f"```{language}")
            print(code)
            print("```")

    def action(self, title: str, details: Optional[List[str]] = None) -> None:
        """
        Display an action summary block.
        
        Args:
            title: Action title (e.g., "Changes applied")
            details: List of detail items
        """
        self._add_block(BlockType.ACTION, "", title=title, items=details or [])
        if self._use_rich:
            self._console.print(f"[bold green]✓ {title}[/bold green]")
            if details:
                for item in details:
                    self._console.print(f"  - {item}")
        else:
            print(f"✓ {title}")
            if details:
                for item in details:
                    print(f"  - {item}")

    def list_items(self, items: List[str], title: Optional[str] = None) -> None:
        """
        Display a bulleted list.
        
        Args:
            items: List items
            title: Optional title
        """
        self._add_block(BlockType.LIST, "", title=title, items=items)
        if self._use_rich:
            if title:
                self._console.print(f"[bold]{title}[/bold]")
            for item in items:
                self._console.print(f"  • {item}")
        else:
            if title:
                print(title)
            for item in items:
                print(f"  • {item}")

    def error(self, message: str, agent_name: Optional[str] = None) -> None:
        """
        Display an error message.
        
        Args:
            message: Error message
            agent_name: Optional agent name for multi-agent prefix
        """
        prefix = self._get_prefix(agent_name)
        if self._use_rich:
            self._console.print(f"[red]{prefix}✗ Error: {message}[/red]")
        else:
            print(f"{prefix}✗ Error: {message}")

    def to_markdown(self) -> str:
        """
        Export all blocks as Markdown.
        
        Returns:
            Markdown string representation of all blocks
        """
        lines = []
        with self._lock:
            blocks = self._blocks.copy()
        
        for block in blocks:
            if block.type == BlockType.NARRATIVE:
                lines.append(block.content)
                lines.append("")
            elif block.type == BlockType.COMMAND:
                lines.append(f"**{block.content}**")
                if block.output:
                    lines.append(f"> {block.output}")
                lines.append("")
            elif block.type == BlockType.CODE:
                lang = block.metadata.get("language", "")
                lines.append(f"```{lang}")
                lines.append(block.content)
                lines.append("```")
                lines.append("")
            elif block.type == BlockType.SUMMARY:
                if block.title:
                    lines.append(f"## {block.title}")
                if block.items:
                    for item in block.items:
                        lines.append(f"- {item}")
                lines.append("")
            elif block.type == BlockType.ACTION:
                if block.title:
                    lines.append(f"✓ **{block.title}**")
                if block.items:
                    for item in block.items:
                        lines.append(f"  - {item}")
                lines.append("")
            elif block.type == BlockType.LIST:
                if block.title:
                    lines.append(f"**{block.title}**")
                for item in block.items:
                    lines.append(f"- {item}")
                lines.append("")
        
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Formatting helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_action(
        step_prefix: str,
        icon: str,
        label: str,
        args: Optional[Dict[str, Any]],
    ) -> str:
        """Build human-readable action string from tool args."""
        if not args:
            return f"{step_prefix}{icon} {label}"

        # Extract the most meaningful argument for context
        for key in ('query', 'filepath', 'file_path', 'directory', 'command'):
            if key in args:
                val = args[key]
                if key == 'query':
                    return f'{step_prefix}{icon} {label} for "{val}"'
                return f"{step_prefix}{icon} {label}: {val}"

        return f"{step_prefix}{icon} {label}"

    @staticmethod
    def _format_result(result: Optional[str]) -> Optional[str]:
        """Convert raw tool result to a user-friendly summary."""
        if not result:
            return None

        result_str = str(result)

        # JSON → summary
        if result_str.startswith(('[', '{')):
            try:
                import json
                data = json.loads(result_str)
                if isinstance(data, list):
                    return f"✓ Found {len(data)} items"
                if isinstance(data, dict):
                    if data.get('success') is True:
                        return f"✓ Created: {data['file_created']}" if data.get('file_created') else "✓ Success"
                    if data.get('success') is False:
                        return f"⚠ Failed: {data.get('error', 'Unknown')[:80]}"
                    if data.get('error'):
                        return f"⚠ {data['error'][:80]}"
                    if data.get('stdout'):
                        first_line = data['stdout'].strip().split('\n')[0][:80]
                        return f"✓ {first_line}"
                    if data.get('exit_code') == 0:
                        return "✓ Command completed"
                    return "✓ Done"
            except (ValueError, TypeError):
                return "✓ Done"

        # Boolean strings
        if result_str.lower() == 'true':
            return "✓ Success"
        if result_str.lower() == 'false':
            return "⚠ Failed"

        # Short plain text → show it; long text → "Done"
        if len(result_str) <= 80 and '\n' not in result_str:
            return result_str
        return "✓ Done"

    # ─────────────────────────────────────────────────────────────────────
    # Internal rendering
    # ─────────────────────────────────────────────────────────────────────

    def _add_block(self, block_type, content, **kwargs):
        block = DisplayBlock(type=block_type, content=content, **kwargs)
        with self._lock:
            self._blocks.append(block)

    def _render_command(self, cmd: str, output: Optional[str] = None):
        if self._use_rich:
            self._console.print(f"[dim]{cmd}[/dim]")
            if output:
                self._console.print(output)
        else:
            print(cmd)
            if output:
                print(output)

    def _render_summary(self, title: str, items: Optional[List[str]] = None):
        if self._use_rich:
            self._console.print()
            self._console.print(f"[bold]{title}[/bold]")
            if items:
                for item in items:
                    self._console.print(f"- {item}")
        else:
            print()
            print(title)
            if items:
                for item in items:
                    print(f"- {item}")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level enable / disable (same pattern as status.py)
# ─────────────────────────────────────────────────────────────────────────────

def is_editor_output_enabled() -> bool:
    """Check whether editor output mode is currently active."""
    return _editor_output_enabled


def enable_editor_output(
    use_color: bool = True,
) -> EditorOutput:
    """
    Enable editor output mode globally.

    Registers display callbacks that render tool calls as numbered steps.

    Returns:
        EditorOutput instance for programmatic access.
    """
    global _editor_output_enabled, _editor_output

    _editor_output = EditorOutput(use_rich=use_color)
    _editor_output_enabled = True

    # Register callbacks with the display system
    from ..main import register_display_callback

    def on_tool_call(
        message: str = None,
        tool_name: str = None,
        tool_input: dict = None,
        tool_output: str = None,
        **kwargs,
    ):
        if not _editor_output_enabled or _editor_output is None:
            return
        if tool_name:
            _editor_output.tool_call(
                tool_name=tool_name,
                args=tool_input,
                result=str(tool_output)[:500] if tool_output else None,
            )

    def on_interaction(
        message: str = None,
        response: str = None,
        agent_name: str = None,
        generation_time: float = None,
        **kwargs,
    ):
        if not _editor_output_enabled or _editor_output is None:
            return
        # Dedup: skip if this exact response was already displayed
        # Covers both llm_content→interaction and interaction→interaction duplicates
        # (LLM layer and Agent layer both fire execute_sync_callback('interaction'))
        if response and hasattr(_editor_output, '_last_displayed_response') and _editor_output._last_displayed_response == response.strip():
            _editor_output._last_displayed_response = None  # Reset for next turn
            return
        if response:
            _editor_output._last_displayed_response = response.strip()
            _editor_output.output(response, agent_name)

    def on_error(message: str = None, **kwargs):
        if not _editor_output_enabled or _editor_output is None:
            return
        if message and _editor_output._use_rich:
            _editor_output._console.print(f"[red]✗ Error: {message}[/red]")
        elif message:
            print(f"✗ Error: {message}")

    def on_llm_start(model: str = None, agent_name: str = None, **kwargs):
        if not _editor_output_enabled or _editor_output is None:
            return
        with _editor_output._lock:
            _editor_output._llm_call_count += 1
            count = _editor_output._llm_call_count
        phase = "Thinking" if count == 1 else "Responding"
        _editor_output.llm_indicator(phase)

    def on_llm_content(content: str = None, agent_name: str = None, **kwargs):
        if not _editor_output_enabled or _editor_output is None:
            return
        if content and content.strip():
            # Dedup: skip if on_interaction already displayed this exact text
            if hasattr(_editor_output, '_last_displayed_response') and _editor_output._last_displayed_response == content.strip():
                return
            _editor_output._last_displayed_response = content.strip()
            _editor_output.narrative(content.strip(), agent_name=agent_name)

    register_display_callback('tool_call', on_tool_call)
    register_display_callback('interaction', on_interaction)
    register_display_callback('error', on_error)
    register_display_callback('llm_start', on_llm_start)
    register_display_callback('llm_content', on_llm_content)

    return _editor_output


def disable_editor_output() -> None:
    """Disable editor output mode."""
    global _editor_output_enabled, _editor_output
    _editor_output_enabled = False
    _editor_output = None


def get_editor_output() -> Optional[EditorOutput]:
    """Get the current editor output instance."""
    return _editor_output

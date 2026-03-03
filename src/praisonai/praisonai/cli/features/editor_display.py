"""
Editor-Style Display for PraisonAI CLI.

Provides a user-friendly display format that is easy to understand:
- Clear action descriptions with icons
- Human-readable tool names
- Progress indicators
- Summarized results (no raw JSON)
- Step-by-step progress

Designed for non-programmers and beginners to understand what the agent is doing.

Usage:
    from praisonai.cli.features.editor_display import EditorDisplay
    
    display = EditorDisplay()
    display.action("Searching the web for information...")
    display.step(1, 10, "Finding Django latest version")
    display.success("Found 5 results")
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum


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
TOOL_LABELS = {
    'internet_search': ('🔍', 'Searching the web'),
    'search_web': ('🔍', 'Searching the web'),
    'web_search': ('🔍', 'Searching the web'),
    'read_file': ('📖', 'Reading file'),
    'write_file': ('📝', 'Writing file'),
    'create_file': ('📄', 'Creating file'),
    'acp_create_file': ('📄', 'Creating file'),
    'acp_edit_file': ('✏️', 'Editing file'),
    'acp_delete_file': ('🗑️', 'Deleting file'),
    'execute_command': ('⚡', 'Running command'),
    'acp_execute_command': ('⚡', 'Running command'),
    'list_files': ('📂', 'Listing files'),
    'get_system_info': ('💻', 'Getting system info'),
    'lsp_get_diagnostics': ('🔬', 'Analyzing code'),
    'lsp_list_symbols': ('🔎', 'Finding code symbols'),
    'lsp_find_definition': ('📍', 'Finding definition'),
    'lsp_find_references': ('🔗', 'Finding references'),
}


class EditorDisplay:
    """
    User-friendly display for CLI output.
    
    Designed for non-programmers and beginners with:
    - Clear action descriptions with icons
    - Human-readable tool names (not technical names)
    - Progress indicators (Step X of Y)
    - Summarized results (no raw JSON)
    - Success/failure indicators
    """
    
    def __init__(self, console=None, use_rich: bool = True):
        """
        Initialize the display.
        
        Args:
            console: Optional Rich console instance
            use_rich: Whether to use Rich formatting (default: True)
        """
        self._use_rich = use_rich
        self._console = console
        self._blocks: List[DisplayBlock] = []
        self._start_time = time.time()
        self._step_count = 0  # Track number of steps for progress
        
        if use_rich and console is None:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                self._use_rich = False
    
    def narrative(self, text: str):
        """
        Display a narrative block (agent thinking/explanation).
        
        Args:
            text: The narrative text
        """
        block = DisplayBlock(type=BlockType.NARRATIVE, content=text)
        self._blocks.append(block)
        self._render_narrative(text)
    
    def command(self, cmd: str, output: str = None, exit_code: int = 0):
        """
        Display a command execution block with output.
        
        Args:
            cmd: The command that was executed
            output: The command output
            exit_code: Exit code (0 = success)
        """
        block = DisplayBlock(
            type=BlockType.COMMAND,
            content=cmd,
            output=output,
            metadata={"exit_code": exit_code}
        )
        self._blocks.append(block)
        self._render_command(cmd, output, exit_code)
    
    def summary(self, title: str, items: List[str] = None, content: str = None):
        """
        Display a summary section with header.
        
        Args:
            title: Section title (e.g., "Problem Identified", "Current Status")
            items: Optional list of bullet points
            content: Optional paragraph content
        """
        block = DisplayBlock(
            type=BlockType.SUMMARY,
            title=title,
            content=content or "",
            items=items or []
        )
        self._blocks.append(block)
        self._render_summary(title, items, content)
    
    def action(self, title: str, details: List[str] = None):
        """
        Display an action summary block.
        
        Args:
            title: Action title (e.g., "Changes applied")
            details: List of detail items
        """
        block = DisplayBlock(
            type=BlockType.ACTION,
            title=title,
            items=details or []
        )
        self._blocks.append(block)
        self._render_action(title, details)
    
    def code(self, code: str, language: str = ""):
        """
        Display a code block.
        
        Args:
            code: The code content
            language: Programming language for syntax highlighting
        """
        block = DisplayBlock(
            type=BlockType.CODE,
            content=code,
            metadata={"language": language}
        )
        self._blocks.append(block)
        self._render_code(code, language)
    
    def list_items(self, items: List[str], title: str = None):
        """
        Display a bulleted list.
        
        Args:
            items: List items
            title: Optional title
        """
        block = DisplayBlock(
            type=BlockType.LIST,
            title=title,
            items=items
        )
        self._blocks.append(block)
        self._render_list(items, title)
    
    def tool_call(self, tool_name: str, args: Dict[str, Any] = None, result: str = None, duration: float = None):
        """
        Display a tool call in user-friendly format.
        
        Args:
            tool_name: Name of the tool
            args: Tool arguments
            result: Tool result
            duration: Execution duration in seconds
        """
        # Increment step counter
        self._step_count += 1
        
        # Get human-readable label
        icon, label = TOOL_LABELS.get(tool_name, ('🔧', f'Using {tool_name}'))
        
        # Format the action description with step number
        step_prefix = f"Step {self._step_count}: "
        if args:
            # Extract key argument for context
            if 'query' in args:
                action = f"{step_prefix}{icon} {label} for \"{args['query']}\""
            elif 'filepath' in args:
                action = f"{step_prefix}{icon} {label}: {args['filepath']}"
            elif 'file_path' in args:
                action = f"{step_prefix}{icon} {label}: {args['file_path']}"
            elif 'directory' in args:
                action = f"{step_prefix}{icon} {label} in {args['directory']}"
            elif 'command' in args:
                action = f"{step_prefix}{icon} {label}: {args['command']}"
            elif 'content' in args:
                action = f"{step_prefix}{icon} {label}"
            else:
                action = f"{step_prefix}{icon} {label}"
        else:
            action = f"{step_prefix}{icon} {label}"
        
        # Format result for display (hide raw JSON, show user-friendly summary)
        display_result = None
        if result:
            result_str = str(result)
            # Check if it's JSON and summarize
            if result_str.startswith('[') or result_str.startswith('{'):
                try:
                    import json
                    data = json.loads(result_str)
                    if isinstance(data, list):
                        # List of items - show count
                        display_result = f"✓ Found {len(data)} items"
                    elif isinstance(data, dict):
                        # Dict - check for common patterns
                        if data.get('success') is True:
                            if data.get('file_created'):
                                display_result = f"✓ Created: {data['file_created']}"
                            else:
                                display_result = "✓ Success"
                        elif data.get('success') is False:
                            display_result = f"⚠ Failed: {data.get('error', 'Unknown error')[:80]}"
                        elif data.get('error'):
                            display_result = f"⚠ {data['error'][:80]}"
                        elif data.get('stdout'):
                            # Command output - show first line
                            stdout = data['stdout'].strip()
                            first_line = stdout.split('\n')[0][:80]
                            display_result = f"✓ {first_line}"
                        elif data.get('exit_code') == 0:
                            display_result = "✓ Command completed"
                        else:
                            display_result = "✓ Done"
                except (json.JSONDecodeError, TypeError, ValueError):
                    # Not valid JSON - don't show raw data
                    display_result = "✓ Done"
            elif result_str.lower() == 'true':
                display_result = "✓ Success"
            elif result_str.lower() == 'false':
                display_result = "⚠ Failed"
            else:
                # Plain text result - show if short
                if len(result_str) <= 80 and '\n' not in result_str:
                    display_result = result_str
                else:
                    # Long text - just confirm done
                    display_result = "✓ Done"
        
        self.command(action, display_result)
    
    def thinking(self, text: str):
        """
        Display agent thinking/reasoning.
        
        Args:
            text: The thinking text
        """
        self.narrative(text)
    
    def result(self, text: str):
        """
        Display final result.
        
        Args:
            text: The result text
        """
        if self._use_rich:
            self._console.print()
            self._console.print(text)
            self._console.print()
        else:
            print()
            print(text)
            print()
    
    def elapsed_time(self) -> float:
        """Get elapsed time since display started."""
        return time.time() - self._start_time
    
    def get_blocks(self) -> List[DisplayBlock]:
        """Get all display blocks."""
        return self._blocks.copy()
    
    def to_markdown(self) -> str:
        """
        Export all blocks as Markdown.
        
        Returns:
            Markdown string
        """
        lines = []
        
        for block in self._blocks:
            if block.type == BlockType.NARRATIVE:
                lines.append(block.content)
                lines.append("")
            
            elif block.type == BlockType.COMMAND:
                lines.append("```")
                lines.append(block.content)
                if block.output:
                    lines.append(block.output)
                lines.append("```")
                lines.append("")
            
            elif block.type == BlockType.SUMMARY:
                if block.title:
                    lines.append(f"## {block.title}")
                if block.content:
                    lines.append(block.content)
                for item in block.items:
                    lines.append(f"- {item}")
                lines.append("")
            
            elif block.type == BlockType.ACTION:
                if block.title:
                    lines.append(f"**{block.title}**")
                for item in block.items:
                    lines.append(f"- {item}")
                lines.append("")
            
            elif block.type == BlockType.CODE:
                lang = block.metadata.get("language", "")
                lines.append(f"```{lang}")
                lines.append(block.content)
                lines.append("```")
                lines.append("")
            
            elif block.type == BlockType.LIST:
                if block.title:
                    lines.append(f"**{block.title}**")
                for item in block.items:
                    lines.append(f"- {item}")
                lines.append("")
        
        return "\n".join(lines)
    
    # =========================================================================
    # Private rendering methods
    # =========================================================================
    
    def _render_narrative(self, text: str):
        """Render narrative block."""
        if self._use_rich:
            self._console.print()
            self._console.print(text)
        else:
            print()
            print(text)
    
    def _render_command(self, cmd: str, output: str = None, exit_code: int = 0):
        """Render command block."""
        if self._use_rich:
            # Command line in dim style
            self._console.print(f"[dim]{cmd}[/dim]")
            
            # Output if present
            if output:
                # Truncate very long output
                lines = output.split("\n")
                if len(lines) > 20:
                    output = "\n".join(lines[:20]) + f"\n... ({len(lines) - 20} more lines)"
                
                self._console.print(output)
        else:
            print(cmd)
            if output:
                print(output)
    
    def _render_summary(self, title: str, items: List[str] = None, content: str = None):
        """Render summary block."""
        if self._use_rich:
            self._console.print()
            self._console.print(f"[bold]{title}[/bold]")
            
            if content:
                self._console.print(content)
            
            if items:
                for item in items:
                    self._console.print(f"- {item}")
        else:
            print()
            print(title)
            print("-" * len(title))
            
            if content:
                print(content)
            
            if items:
                for item in items:
                    print(f"- {item}")
    
    def _render_action(self, title: str, details: List[str] = None):
        """Render action block."""
        if self._use_rich:
            self._console.print()
            self._console.print(f"[bold green]{title}[/bold green]")
            
            if details:
                for detail in details:
                    self._console.print(f"  {detail}")
        else:
            print()
            print(title)
            
            if details:
                for detail in details:
                    print(f"  {detail}")
    
    def _render_code(self, code: str, language: str = ""):
        """Render code block."""
        if self._use_rich:
            try:
                from rich.syntax import Syntax
                syntax = Syntax(code, language or "text", theme="monokai", line_numbers=False)
                self._console.print(syntax)
            except Exception:
                self._console.print(f"```{language}")
                self._console.print(code)
                self._console.print("```")
        else:
            print(f"```{language}")
            print(code)
            print("```")
    
    def _render_list(self, items: List[str], title: str = None):
        """Render list block."""
        if self._use_rich:
            if title:
                self._console.print(f"[bold]{title}[/bold]")
            
            for item in items:
                self._console.print(f"- {item}")
        else:
            if title:
                print(title)
            
            for item in items:
                print(f"- {item}")


def create_editor_callbacks(display: EditorDisplay) -> Dict[str, Callable]:
    """
    Create SDK callbacks that use EditorDisplay.
    
    Args:
        display: EditorDisplay instance
        
    Returns:
        Dict of callback functions to register with SDK
    """
    def tool_call_callback(message=None, tool_name=None, tool_input=None, tool_output=None, **kwargs):
        """Callback for tool calls."""
        if tool_name:
            display.tool_call(
                tool_name=tool_name,
                args=tool_input,
                result=str(tool_output)[:500] if tool_output else None
            )
    
    def thinking_callback(content=None, **kwargs):
        """Callback for agent thinking."""
        if content:
            display.thinking(content)
    
    def response_callback(content=None, **kwargs):
        """Callback for agent response."""
        if content:
            display.result(content)
    
    def autonomy_iteration_callback(iteration=None, max_iterations=None, stage=None, **kwargs):
        """Callback for autonomy iterations."""
        if iteration and max_iterations:
            display.narrative(f"Iteration {iteration}/{max_iterations}: {stage or 'processing'}...")
    
    return {
        "tool_call": tool_call_callback,
        "thinking": thinking_callback,
        "response": response_callback,
        "autonomy_iteration": autonomy_iteration_callback,
    }

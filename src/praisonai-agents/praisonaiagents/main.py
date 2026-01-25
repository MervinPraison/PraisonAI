import os
import time
import json
import logging
from typing import List, Optional, Dict, Any, Union, Literal, Type
from pydantic import BaseModel, ConfigDict
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from rich.live import Live
import asyncio

# Import token metrics if available
try:
    from .telemetry.token_collector import TokenMetrics
except ImportError:
    TokenMetrics = None

# Logging is already configured in _logging.py via __init__.py

# Global list to store error logs
error_logs = []

# Separate registries for sync and async callbacks
sync_display_callbacks = {}
async_display_callbacks = {}

# Global approval callback registry
approval_callback = None

# ─────────────────────────────────────────────────────────────────────────────
# PraisonAI Unique Color Palette: "Elegant Intelligence"
# Creates a visual narrative flow: Agent → Task → Working → Response
# ─────────────────────────────────────────────────────────────────────────────
PRAISON_COLORS = {
    # Agent identity - grounded, stable
    "agent": "#86A789",       # Soft Sage Green
    "agent_text": "#D2E3C8",  # Light sage for text
    
    # Task/Question - input, attention-grabbing
    "task": "#FF9B9B",        # Warm Coral
    "task_text": "#FFE5E5",   # Light coral for text
    
    # Working/Processing - action, energy
    "working": "#FFB347",     # Amber
    "working_text": "#FFF3E0", # Light amber for text
    
    # Response/Output - completion, calm
    "response": "#4A90D9",    # Ocean Blue
    "response_text": "#E3F2FD", # Light blue for text
    
    # Tool calls - special action
    "tool": "#9B7EDE",        # Violet Accent
    "tool_text": "#EDE7F6",   # Light violet for text
    
    # Reasoning - thought process
    "reasoning": "#78909C",   # Blue Gray
    "reasoning_text": "#ECEFF1", # Light gray for text
    
    # Error/Warning - alert
    "error": "#E57373",       # Alert Red
    "error_text": "#FFEBEE",  # Light red for text
    
    # Metrics - meta information
    "metrics": "#B4B4B3",     # Cool Gray
    "metrics_text": "#FAFAFA", # Near white for text
}

# Status animation frames for "Working" indicator
WORKING_FRAMES = ["●○○", "○●○", "○○●", "○●○"]
WORKING_PHASES = [
    "Analyzing query...",
    "Processing context...",
    "Generating response...",
    "Finalizing output...",
]

# At the top of the file, add display_callbacks to __all__
__all__ = [
    'error_logs',
    'register_display_callback',
    'register_approval_callback',
    'add_display_callback',  # Simplified alias
    'add_approval_callback',  # Simplified alias
    'sync_display_callbacks',
    'async_display_callbacks',
    'execute_callback',
    'approval_callback',
    # Color palette and animation constants
    'PRAISON_COLORS',
    'WORKING_FRAMES',
    'WORKING_PHASES',
    # Display functions
    'display_interaction',
    'display_instruction',
    'display_tool_call',
    'display_error',
    'display_generating',
    'display_reasoning_steps',
    'display_working_status',
    'display_self_reflection',
]

def register_display_callback(display_type: str, callback_fn, is_async: bool = False):
    """Register a synchronous or asynchronous callback function for a specific display type.
    
    Args:
        display_type (str): Type of display event ('interaction', 'self_reflection', etc.)
        callback_fn: The callback function to register
        is_async (bool): Whether the callback is asynchronous
    """
    if is_async:
        async_display_callbacks[display_type] = callback_fn
    else:
        sync_display_callbacks[display_type] = callback_fn

def register_approval_callback(callback_fn):
    """Register a global approval callback function for dangerous tool operations.
    
    Args:
        callback_fn: Function that takes (function_name, arguments, risk_level) and returns ApprovalDecision
    """
    global approval_callback
    approval_callback = callback_fn


# Simplified aliases (consistent naming convention)
add_display_callback = register_display_callback
add_approval_callback = register_approval_callback


def execute_sync_callback(display_type: str, **kwargs):
    """Execute synchronous callback for a given display type without displaying anything.
    
    This function is used to trigger callbacks even when verbose=False.
    
    Args:
        display_type (str): Type of display event
        **kwargs: Arguments to pass to the callback function
    """
    if display_type in sync_display_callbacks:
        callback = sync_display_callbacks[display_type]
        import inspect
        sig = inspect.signature(callback)
        
        # Filter kwargs to what the callback accepts to maintain backward compatibility
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            # Callback accepts **kwargs, so pass all arguments
            supported_kwargs = kwargs
        else:
            # Only pass arguments that the callback signature supports
            supported_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        
        callback(**supported_kwargs)

async def execute_callback(display_type: str, **kwargs):
    """Execute both sync and async callbacks for a given display type.
    
    Args:
        display_type (str): Type of display event
        **kwargs: Arguments to pass to the callback functions
    """
    import inspect
    
    # Execute synchronous callback if registered
    if display_type in sync_display_callbacks:
        callback = sync_display_callbacks[display_type]
        sig = inspect.signature(callback)
        
        # Filter kwargs to what the callback accepts to maintain backward compatibility
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            # Callback accepts **kwargs, so pass all arguments
            supported_kwargs = kwargs
        else:
            # Only pass arguments that the callback signature supports
            supported_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: callback(**supported_kwargs))
    
    # Execute asynchronous callback if registered
    if display_type in async_display_callbacks:
        callback = async_display_callbacks[display_type]
        sig = inspect.signature(callback)
        
        # Filter kwargs to what the callback accepts to maintain backward compatibility
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            # Callback accepts **kwargs, so pass all arguments
            supported_kwargs = kwargs
        else:
            # Only pass arguments that the callback signature supports
            supported_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        
        await callback(**supported_kwargs)

def _clean_display_content(content: str, max_length: int = 20000) -> str:
    """Helper function to clean and truncate content for display."""
    if not content or not str(content).strip():
        logging.debug(f"Empty content received in _clean_display_content: {repr(content)}")
        return ""
        
    content = str(content)
    # Handle base64 content
    if "base64" in content:
        content_parts = []
        for line in content.split('\n'):
            if "base64" not in line:
                content_parts.append(line)
        content = '\n'.join(content_parts)
    
    # Truncate if too long
    if len(content) > max_length:
        content = content[:max_length] + "..."
    
    return content.strip()

def display_interaction(message, response, markdown=True, generation_time=None, console=None, agent_name=None, agent_role=None, agent_tools=None, task_name=None, task_description=None, task_id=None, metrics=None):
    """Synchronous version of display_interaction.
    
    Displays the task/message and response in clean panels with semantic colors
    and optional metrics footer. Uses PraisonAI's unique color palette.
    
    Args:
        metrics: Optional dict with token_in, token_out, cost, model for footer display
    """
    if console is None:
        console = Console()
    
    if isinstance(message, list):
        text_content = next((item["text"] for item in message if item["type"] == "text"), "")
        message = text_content

    message = _clean_display_content(str(message))
    response = _clean_display_content(str(response))
    
    # Skip display if response is empty (common with Gemini tool calls)
    if not response or not response.strip():
        return

    # Execute synchronous callbacks
    execute_sync_callback(
        'interaction',
        message=message,
        response=response,
        markdown=markdown,
        generation_time=generation_time,
        agent_name=agent_name,
        agent_role=agent_role,
        agent_tools=agent_tools,
        task_name=task_name,
        task_description=task_description,
        task_id=task_id,
        metrics=metrics
    )
    
    # Build response title with time
    response_title = "Response"
    if generation_time:
        response_title = f"Response ({generation_time:.1f}s)"
    
    # Build response content with optional metrics footer
    response_content = response
    if metrics and isinstance(metrics, dict):
        # Add dashed separator and compact metrics line
        tokens_in = metrics.get('tokens_in', 0)
        tokens_out = metrics.get('tokens_out', 0)
        cost = metrics.get('cost', 0)
        model = metrics.get('model', '')
        
        metrics_line = f"\n\n─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n📊 {tokens_in} tokens in · {tokens_out} out"
        if cost > 0:
            metrics_line += f" · ${cost:.4f}"
        if model:
            metrics_line += f" · {model}"
        response_content = response + metrics_line

    # Task is inline (less visual weight), Response keeps panel (it's the main content)
    # Format: 📝 Task message
    task_prefix = "[bold #FF9B9B]📝[/]"
    if markdown:
        console.print(f"{task_prefix} {message}\n")
        console.print(Panel.fit(Markdown(response_content), title=response_title, border_style=PRAISON_COLORS["response"]))
    else:
        console.print(f"{task_prefix} [bold {PRAISON_COLORS['task_text']}]{message}[/]\n")
        console.print(Panel.fit(Text(response_content, style=f"bold {PRAISON_COLORS['response_text']}"), title=response_title, border_style=PRAISON_COLORS["response"]))

def display_self_reflection(message: str, console=None):
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute synchronous callbacks
    execute_sync_callback('self_reflection', message=message)
    
    console.print(Panel.fit(Text(message, style="bold yellow"), title="Self Reflection", border_style="magenta"))

def display_instruction(message: str, console=None, agent_name: str = None, agent_role: str = None, agent_tools: List[str] = None):
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute synchronous callbacks
    execute_sync_callback('instruction', message=message, agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools)
    
    # Display agent info if available
    if agent_name:
        agent_info = f"[bold #FF9B9B]👤 Agent:[/] [#FFE5E5]{agent_name}[/]"
        if agent_role:
            agent_info += f"\n[bold #B4B4B3]Role:[/] [#FFE5E5]{agent_role}[/]"
        if agent_tools:
            tools_str = ", ".join(f"[italic #B4D4FF]{tool}[/]" for tool in agent_tools)
            agent_info += f"\n[bold #86A789]Tools:[/] {tools_str}"
        console.print(Panel(agent_info, border_style="#D2E3C8", title="[bold]Agent Info[/]", title_align="left", padding=(1, 2)))
    
    # Only print if log level is DEBUG
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        console.print(Panel.fit(Text(message, style="bold blue"), title="Instruction", border_style="cyan"))

def display_tool_call(message: str, console=None, tool_name: str = None, tool_input: dict = None, tool_output: str = None, elapsed_time: float = None, success: bool = True):
    """Display tool call information in PraisonAI's unique timeline format.
    
    Uses ▸ prefix, inline timing [X.Xs], and status icons ✓/✗ for a clean,
    scannable tool activity display.
    
    Args:
        message: The tool call message (legacy format)
        console: Rich console for output
        tool_name: Name of the tool being called
        tool_input: Input arguments to the tool
        tool_output: Output from the tool (if available)
        elapsed_time: Time taken for tool execution in seconds
        success: Whether the tool call succeeded
    """
    logging.debug(f"display_tool_call called with message: {repr(message)}")
    if not message or not message.strip():
        logging.debug("Empty message in display_tool_call, returning early")
        return
    message = _clean_display_content(str(message))
    logging.debug(f"Cleaned message in display_tool_call: {repr(message)}")
    
    # Execute synchronous callbacks (always, even when console is None)
    execute_sync_callback('tool_call', message=message, tool_name=tool_name, tool_input=tool_input, tool_output=tool_output)
    
    # Only print if console is provided (verbose mode)
    if console is not None:
        # Build clean inline format - no panels, just prefixed lines
        if tool_name:
            # Format: ▸ tool_name(args) → result [X.Xs] ✓
            args_str = ""
            if tool_input:
                # Truncate long values for display
                args_parts = []
                for k, v in tool_input.items():
                    v_str = str(v)
                    if len(v_str) > 50:
                        v_str = v_str[:47] + "..."
                    args_parts.append(f"{k}={repr(v_str) if isinstance(v, str) else v_str}")
                args_str = ", ".join(args_parts)
            
            # Build the inline entry
            status_icon = "[green]✓[/]" if success else "[red]✗[/]"
            time_str = f"[dim][{elapsed_time:.1f}s][/]" if elapsed_time else ""
            
            # Base tool call line
            tool_line = f"[bold #86A789]▸[/] [#B4D4FF]{tool_name}[/]({args_str})"
            
            # Add output inline with arrow if available
            if tool_output:
                output_str = str(tool_output)
                if len(output_str) > 80:
                    output_str = output_str[:77] + "..."
                tool_line += f" [dim]→[/] [italic]{output_str}[/]"
            
            tool_line += f" {time_str} {status_icon}"
            console.print(tool_line)
        else:
            # Legacy format - simple inline
            console.print(f"[bold #86A789]▸[/] {message}")

def display_error(message: str, console=None):
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute synchronous callbacks
    execute_sync_callback('error', message=message)
    
    # Use semantic error color
    console.print(Panel.fit(
        Text(message, style=f"bold {PRAISON_COLORS['error_text']}"), 
        title="⚠ Error", 
        border_style=PRAISON_COLORS["error"]
    ))
    error_logs.append(message)

def display_generating(content: str = "", start_time: Optional[float] = None):
    if not content or not str(content).strip():
        logging.debug("Empty content in display_generating, returning early")
        return None
    
    elapsed_str = ""
    if start_time is not None:
        elapsed = time.time() - start_time
        elapsed_str = f" {elapsed:.1f}s"
    
    content = _clean_display_content(str(content))
    
    # Execute synchronous callbacks
    execute_sync_callback('generating', content=content, elapsed_time=elapsed_str.strip() if elapsed_str else None)
    
    # Use semantic response color
    return Panel(Markdown(content), title=f"Generating...{elapsed_str}", border_style=PRAISON_COLORS["response"])

def display_reasoning_steps(steps: List[str], console=None):
    """Display reasoning steps with unique numbered circles.
    
    Uses ①②③ numbered circles for a distinctive, scannable format
    that shows the agent's thought process.
    
    Args:
        steps: List of reasoning step descriptions
        console: Rich console for output
    """
    if not steps:
        return
    if console is None:
        console = Console()
    
    # Circle number mapping (supports up to 20 steps)
    circle_numbers = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
    
    # Build reasoning display with numbered circles
    reasoning_lines = []
    for i, step in enumerate(steps):
        circle = circle_numbers[i] if i < len(circle_numbers) else f"({i+1})"
        step_text = _clean_display_content(str(step))
        if len(step_text) > 80:
            step_text = step_text[:77] + "..."
        reasoning_lines.append(f"{circle} {step_text}")
    
    reasoning_display = "\n".join(reasoning_lines)
    
    console.print(Panel.fit(
        Text(reasoning_display, style=f"italic {PRAISON_COLORS['reasoning_text']}"),
        title="Reasoning",
        border_style=PRAISON_COLORS["reasoning"]
    ))

def display_working_status(phase: int = 0, status_text: str = None, console=None):
    """Display animated working status with pulsing dots.
    
    Shows a unique "Working ●○○" indicator with phase-specific status.
    This is PraisonAI's distinctive approach to showing processing status.
    
    Args:
        phase: Current animation phase (0-3)
        status_text: Optional status description
        console: Rich console for output
    
    Returns:
        Panel object for use with Rich.Live
    """
    if console is None:
        console = Console()
    
    # Get current frame and phase text
    frame = WORKING_FRAMES[phase % len(WORKING_FRAMES)]
    phase_text = status_text or WORKING_PHASES[phase % len(WORKING_PHASES)]
    
    # Build working status display
    working_display = f"Working {frame}  {phase_text}"
    
    return Panel.fit(
        Text(working_display, style=f"bold {PRAISON_COLORS['working_text']}"),
        title="Status",
        border_style=PRAISON_COLORS["working"]
    )

# Async versions with 'a' prefix
async def adisplay_interaction(message, response, markdown=True, generation_time=None, console=None, agent_name=None, agent_role=None, agent_tools=None, task_name=None, task_description=None, task_id=None):
    """Async version of display_interaction."""
    if console is None:
        console = Console()
    
    if isinstance(message, list):
        text_content = next((item["text"] for item in message if item["type"] == "text"), "")
        message = text_content

    message = _clean_display_content(str(message))
    response = _clean_display_content(str(response))

    # Execute callbacks
    await execute_callback(
        'interaction',
        message=message,
        response=response,
        markdown=markdown,
        generation_time=generation_time,
        agent_name=agent_name,
        agent_role=agent_role,
        agent_tools=agent_tools,
        task_name=task_name,
        task_description=task_description,
        task_id=task_id
    )

    # Rest of the display logic...
    if generation_time:
        console.print(Text(f"Response generated in {generation_time:.1f}s", style="dim"))

    if markdown:
        console.print(Panel.fit(Markdown(message), title="Task", border_style="cyan"))
        console.print(Panel.fit(Markdown(response), title="Response", border_style="cyan"))
    else:
        console.print(Panel.fit(Text(message, style="bold green"), title="Task", border_style="cyan"))
        console.print(Panel.fit(Text(response, style="bold blue"), title="Response", border_style="cyan"))

async def adisplay_self_reflection(message: str, console=None):
    """Async version of display_self_reflection."""
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute callbacks
    await execute_callback('self_reflection', message=message)
    
    console.print(Panel.fit(Text(message, style="bold yellow"), title="Self Reflection", border_style="magenta"))

async def adisplay_instruction(message: str, console=None, agent_name: str = None, agent_role: str = None, agent_tools: List[str] = None):
    """Async version of display_instruction."""
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute callbacks
    await execute_callback('instruction', message=message, agent_name=agent_name, agent_role=agent_role, agent_tools=agent_tools)
    
    # Display agent info if available
    if agent_name:
        agent_info = f"[bold #FF9B9B]👤 Agent:[/] [#FFE5E5]{agent_name}[/]"
        if agent_role:
            agent_info += f"\n[bold #B4B4B3]Role:[/] [#FFE5E5]{agent_role}[/]"
        if agent_tools:
            tools_str = ", ".join(f"[italic #B4D4FF]{tool}[/]" for tool in agent_tools)
            agent_info += f"\n[bold #86A789]Tools:[/] {tools_str}"
        console.print(Panel(agent_info, border_style="#D2E3C8", title="[bold]Agent Info[/]", title_align="left", padding=(1, 2)))
    
    # Only print if log level is DEBUG
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        console.print(Panel.fit(Text(message, style="bold blue"), title="Instruction", border_style="cyan"))

async def adisplay_tool_call(message: str, console=None):
    """Async version of display_tool_call."""
    logging.debug(f"adisplay_tool_call called with message: {repr(message)}")
    if not message or not message.strip():
        logging.debug("Empty message in adisplay_tool_call, returning early")
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    logging.debug(f"Cleaned message in adisplay_tool_call: {repr(message)}")
    
    # Execute callbacks
    await execute_callback('tool_call', message=message)
    
    console.print(Panel.fit(Text(message, style="bold cyan"), title="Tool Call", border_style="green"))

async def adisplay_error(message: str, console=None):
    """Async version of display_error."""
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute callbacks
    await execute_callback('error', message=message)
    
    console.print(Panel.fit(Text(message, style="bold red"), title="Error", border_style="red"))
    error_logs.append(message)

async def adisplay_generating(content: str = "", start_time: Optional[float] = None):
    """Async version of display_generating."""
    if not content or not str(content).strip():
        logging.debug("Empty content in adisplay_generating, returning early")
        return None
    
    elapsed_str = ""
    if start_time is not None:
        elapsed = time.time() - start_time
        elapsed_str = f" {elapsed:.1f}s"
    
    content = _clean_display_content(str(content))
    
    # Execute callbacks
    await execute_callback('generating', content=content, elapsed_time=elapsed_str.strip() if elapsed_str else None)
    
    return Panel(Markdown(content), title=f"Generating...{elapsed_str}", border_style="green")

def clean_triple_backticks(text: str) -> str:
    """Remove triple backticks and surrounding json fences from a string."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned

class ReflectionOutput(BaseModel):
    reflection: str
    satisfactory: Literal["yes", "no"]


class TaskOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    description: str
    summary: Optional[str] = None
    raw: str
    pydantic: Optional[BaseModel] = None
    json_dict: Optional[Dict[str, Any]] = None
    agent: str
    output_format: Literal["RAW", "JSON", "Pydantic"] = "RAW"
    token_metrics: Optional['TokenMetrics'] = None  # Add token metrics field

    def json(self) -> Optional[str]:
        if self.output_format == "JSON" and self.json_dict:
            return json.dumps(self.json_dict)
        return None

    def to_dict(self) -> dict:
        output_dict = {}
        if self.json_dict:
            output_dict.update(self.json_dict)
        if self.pydantic:
            output_dict.update(self.pydantic.model_dump())
        return output_dict

    def __str__(self):
        if self.pydantic:
            return str(self.pydantic)
        elif self.json_dict:
            return json.dumps(self.json_dict)
        else:
            return self.raw 
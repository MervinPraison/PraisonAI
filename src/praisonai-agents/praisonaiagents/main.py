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

# Logging is already configured in __init__.py, just clean up handlers for litellm
logging.getLogger("litellm").handlers = []
logging.getLogger("litellm.utils").handlers = []
logging.getLogger("litellm").propagate = False
logging.getLogger("litellm.utils").propagate = False

# Global list to store error logs
error_logs = []

# Separate registries for sync and async callbacks
sync_display_callbacks = {}
async_display_callbacks = {}

# Global approval callback registry
approval_callback = None

# At the top of the file, add display_callbacks to __all__
__all__ = [
    'error_logs',
    'register_display_callback',
    'register_approval_callback',
    'sync_display_callbacks',
    'async_display_callbacks',
    'execute_callback',
    'approval_callback',
    # ... other exports
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

def display_interaction(message, response, markdown=True, generation_time=None, console=None, agent_name=None, agent_role=None, agent_tools=None, task_name=None, task_description=None, task_id=None):
    """Synchronous version of display_interaction."""
    if console is None:
        console = Console()
    
    if isinstance(message, list):
        text_content = next((item["text"] for item in message if item["type"] == "text"), "")
        message = text_content

    message = _clean_display_content(str(message))
    response = _clean_display_content(str(response))

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

def display_tool_call(message: str, console=None):
    logging.debug(f"display_tool_call called with message: {repr(message)}")
    if not message or not message.strip():
        logging.debug("Empty message in display_tool_call, returning early")
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    logging.debug(f"Cleaned message in display_tool_call: {repr(message)}")
    
    # Execute synchronous callbacks
    execute_sync_callback('tool_call', message=message)
    
    console.print(Panel.fit(Text(message, style="bold cyan"), title="Tool Call", border_style="green"))

def display_error(message: str, console=None):
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute synchronous callbacks
    execute_sync_callback('error', message=message)
    
    console.print(Panel.fit(Text(message, style="bold red"), title="Error", border_style="red"))
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
    
    return Panel(Markdown(content), title=f"Generating...{elapsed_str}", border_style="green")

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
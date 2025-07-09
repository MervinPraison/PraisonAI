"""Display utilities for console output and UI interactions.

This module provides all display functionality for the PraisonAI agents system,
including synchronous and asynchronous display functions for various types of
output (interactions, errors, tool calls, etc.).
"""

import time
import logging
import asyncio
from typing import List, Optional, Dict, Any

from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from rich.live import Live

# Import callback registries from callbacks module
try:
    from .callbacks import sync_display_callbacks, async_display_callbacks, execute_callback
except ImportError:
    # Fallback for when callbacks module doesn't exist yet
    sync_display_callbacks = {}
    async_display_callbacks = {}
    async def execute_callback(display_type: str, **kwargs):
        pass

# Global list to store error logs
error_logs = []


def _clean_display_content(content: str, max_length: int = 20000) -> str:
    """Helper function to clean and truncate content for display.
    
    Args:
        content: Content to clean
        max_length: Maximum length before truncation
        
    Returns:
        Cleaned and possibly truncated content
    """
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


def display_interaction(message, response, markdown=True, generation_time=None, console=None):
    """Display an interaction between user/task and agent response.
    
    Args:
        message: The task or user message
        response: The agent's response
        markdown: Whether to render as markdown
        generation_time: Time taken to generate response
        console: Rich console instance (created if None)
    """
    if console is None:
        console = Console()
    
    if isinstance(message, list):
        text_content = next((item["text"] for item in message if item["type"] == "text"), "")
        message = text_content

    message = _clean_display_content(str(message))
    response = _clean_display_content(str(response))

    # Execute synchronous callback if registered
    if 'interaction' in sync_display_callbacks:
        sync_display_callbacks['interaction'](
            message=message,
            response=response,
            markdown=markdown,
            generation_time=generation_time
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
    """Display a self-reflection message from the agent.
    
    Args:
        message: The reflection message
        console: Rich console instance (created if None)
    """
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute callback if registered
    if 'self_reflection' in sync_display_callbacks:
        sync_display_callbacks['self_reflection'](message=message)
    
    console.print(Panel.fit(Text(message, style="bold yellow"), title="Self Reflection", border_style="magenta"))


def display_instruction(message: str, console=None, agent_name: str = None, agent_role: str = None, agent_tools: List[str] = None):
    """Display instruction message with optional agent information.
    
    Args:
        message: The instruction message
        console: Rich console instance (created if None)
        agent_name: Name of the agent
        agent_role: Role of the agent
        agent_tools: List of tools available to the agent
    """
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute callback if registered
    if 'instruction' in sync_display_callbacks:
        sync_display_callbacks['instruction'](message=message)
    
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
    """Display a tool call message.
    
    Args:
        message: The tool call information
        console: Rich console instance (created if None)
    """
    logging.debug(f"display_tool_call called with message: {repr(message)}")
    if not message or not message.strip():
        logging.debug("Empty message in display_tool_call, returning early")
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    logging.debug(f"Cleaned message in display_tool_call: {repr(message)}")
    
    # Execute callback if registered
    if 'tool_call' in sync_display_callbacks:
        sync_display_callbacks['tool_call'](message=message)
    
    console.print(Panel.fit(Text(message, style="bold cyan"), title="Tool Call", border_style="green"))


def display_error(message: str, console=None):
    """Display an error message and log it.
    
    Args:
        message: The error message
        console: Rich console instance (created if None)
    """
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    # Execute callback if registered
    if 'error' in sync_display_callbacks:
        sync_display_callbacks['error'](message=message)
    
    console.print(Panel.fit(Text(message, style="bold red"), title="Error", border_style="red"))
    error_logs.append(message)


def display_generating(content: str = "", start_time: Optional[float] = None):
    """Display content being generated with elapsed time.
    
    Args:
        content: The content being generated
        start_time: When generation started (for elapsed time)
        
    Returns:
        Panel object for use with Live display or None
    """
    if not content or not str(content).strip():
        logging.debug("Empty content in display_generating, returning early")
        return None
    
    elapsed_str = ""
    if start_time is not None:
        elapsed = time.time() - start_time
        elapsed_str = f" {elapsed:.1f}s"
    
    content = _clean_display_content(str(content))
    
    # Execute callback if registered
    if 'generating' in sync_display_callbacks:
        sync_display_callbacks['generating'](
            content=content,
            elapsed_time=elapsed_str.strip() if elapsed_str else None
        )
    
    return Panel(Markdown(content), title=f"Generating...{elapsed_str}", border_style="green")


# Async versions with 'a' prefix
async def adisplay_interaction(message, response, markdown=True, generation_time=None, console=None):
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
        generation_time=generation_time
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
    
    await execute_callback('self_reflection', message=message)
    
    console.print(Panel.fit(Text(message, style="bold yellow"), title="Self Reflection", border_style="magenta"))


async def adisplay_instruction(message: str, console=None, agent_name: str = None, agent_role: str = None, agent_tools: List[str] = None):
    """Async version of display_instruction."""
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
    await execute_callback('instruction', message=message)
    
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
    
    await execute_callback('tool_call', message=message)
    
    console.print(Panel.fit(Text(message, style="bold cyan"), title="Tool Call", border_style="green"))


async def adisplay_error(message: str, console=None):
    """Async version of display_error."""
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    
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
    
    await execute_callback(
        'generating',
        content=content,
        elapsed_time=elapsed_str.strip() if elapsed_str else None
    )
    
    return Panel(Markdown(content), title=f"Generating...{elapsed_str}", border_style="green")


# Export all display functions
__all__ = [
    'display_interaction',
    'display_self_reflection',
    'display_instruction',
    'display_tool_call',
    'display_error',
    'display_generating',
    'adisplay_interaction',
    'adisplay_self_reflection',
    'adisplay_instruction',
    'adisplay_tool_call',
    'adisplay_error',
    'adisplay_generating',
    'error_logs',
    '_clean_display_content',
]
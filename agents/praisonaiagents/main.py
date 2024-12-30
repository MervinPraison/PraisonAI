import os
import time
import json
import logging
from typing import List, Optional, Dict, Any, Union, Literal, Type
from openai import OpenAI
from pydantic import BaseModel
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from rich.logging import RichHandler
from rich.live import Live

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()

logging.basicConfig(
    level=getattr(logging, LOGLEVEL, logging.INFO),
    format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)

# Global list to store error logs
error_logs = []

def _clean_display_content(content: str, max_length: int = 20000) -> str:
    """Helper function to clean and truncate content for display."""
    if not content or not str(content).strip():
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
    """Display the interaction between user and assistant."""
    if console is None:
        console = Console()
    if generation_time:
        console.print(Text(f"Response generated in {generation_time:.1f}s", style="dim"))

    # Handle multimodal content (list)
    if isinstance(message, list):
        # Extract just the text content from the multimodal message
        text_content = next((item["text"] for item in message if item["type"] == "text"), "")
        message = text_content

    message = _clean_display_content(str(message))
    response = _clean_display_content(str(response))

    if markdown:
        console.print(Panel.fit(Markdown(message), title="Message", border_style="cyan"))
        console.print(Panel.fit(Markdown(response), title="Response", border_style="cyan"))
    else:
        console.print(Panel.fit(Text(message, style="bold green"), title="Message", border_style="cyan"))
        console.print(Panel.fit(Text(response, style="bold blue"), title="Response", border_style="cyan"))

def display_self_reflection(message: str, console=None):
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    console.print(Panel.fit(Text(message, style="bold yellow"), title="Self Reflection", border_style="magenta"))

def display_instruction(message: str, console=None):
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    console.print(Panel.fit(Text(message, style="bold blue"), title="Instruction", border_style="cyan"))

def display_tool_call(message: str, console=None):
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    console.print(Panel.fit(Text(message, style="bold cyan"), title="Tool Call", border_style="green"))

def display_error(message: str, console=None):
    if not message or not message.strip():
        return
    if console is None:
        console = Console()
    message = _clean_display_content(str(message))
    console.print(Panel.fit(Text(message, style="bold red"), title="Error", border_style="red"))
    # Store errors
    error_logs.append(message)

def display_generating(content: str = "", start_time: Optional[float] = None):
    if not content or not str(content).strip():
        return Panel("", title="", border_style="green")  # Return empty panel when no content
    elapsed_str = ""
    if start_time is not None:
        elapsed = time.time() - start_time
        elapsed_str = f" {elapsed:.1f}s"
    
    content = _clean_display_content(str(content))
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

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

class TaskOutput(BaseModel):
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
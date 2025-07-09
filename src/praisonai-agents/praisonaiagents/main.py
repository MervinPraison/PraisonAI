import os
import logging
from rich.logging import RichHandler

# # Configure root logger
# logging.basicConfig(level=logging.WARNING)

# Suppress litellm logs
logging.getLogger("litellm").handlers = []
logging.getLogger("litellm.utils").handlers = []
logging.getLogger("litellm").propagate = False
logging.getLogger("litellm.utils").propagate = False

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()

logging.basicConfig(
    level=getattr(logging, LOGLEVEL, logging.INFO),
    format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)

# Add these lines to suppress markdown parser debug logs
logging.getLogger('markdown_it').setLevel(logging.WARNING)
logging.getLogger('rich.markdown').setLevel(logging.WARNING)

# Import from new modules
from .display import (
    display_interaction, display_self_reflection, display_instruction,
    display_tool_call, display_error, display_generating,
    adisplay_interaction, adisplay_self_reflection, adisplay_instruction,
    adisplay_tool_call, adisplay_error, adisplay_generating,
    error_logs, _clean_display_content
)
from .callbacks import (
    register_display_callback, register_approval_callback, execute_callback,
    sync_display_callbacks, async_display_callbacks, approval_callback
)
from .models import ReflectionOutput, TaskOutput
from .client import client
from .utils.utils import clean_triple_backticks

# Re-export everything for backward compatibility
__all__ = [
    # From display module
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
    # From callbacks module
    'register_display_callback',
    'register_approval_callback',
    'execute_callback',
    'sync_display_callbacks',
    'async_display_callbacks',
    'approval_callback',
    # From models module
    'ReflectionOutput',
    'TaskOutput',
    # From client module
    'client',
    # From utils module
    'clean_triple_backticks',
]
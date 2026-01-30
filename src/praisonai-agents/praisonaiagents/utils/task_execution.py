"""
Shared Task Execution Utilities.

DRY utilities for task execution logic shared between:
- AgentManager.execute_task() / aexecute_task()
- Workflow step execution

These utilities eliminate code duplication between sync and async execution paths.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


def build_task_prompt(
    description: str,
    expected_output: str,
    context_results: Optional[List[str]] = None,
    memory_context: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a standardized task prompt for agent execution.
    
    DRY helper - consolidates prompt building logic.
    
    Args:
        description: Task description
        expected_output: Expected output format/content
        context_results: List of context strings from previous tasks
        memory_context: Memory context string if available
        variables: Variables for substitution in description
        
    Returns:
        Formatted task prompt string
    """
    # Apply variable substitution if provided
    task_description = description
    if variables:
        for key, value in variables.items():
            task_description = task_description.replace(f"{{{{{key}}}}}", str(value))
    
    prompt = f"""
You need to do the following task: {task_description}.
Expected Output: {expected_output}.
"""
    
    # Add context if available
    if context_results:
        unique_contexts = list(dict.fromkeys(context_results))  # Remove duplicates
        context_separator = '\n\n'
        prompt += f"""
Context:

{context_separator.join(unique_contexts)}
"""
    
    # Add memory context if available
    if memory_context:
        prompt += f"\n\n{memory_context}"
    
    prompt += "Please provide only the final result of your work. Do not add any conversation or extra explanation."
    
    return prompt


def parse_task_output(
    agent_output: str,
    output_json: Optional[Any] = None,
    output_pydantic: Optional[Any] = None,
    task_id: Optional[int] = None,
    clean_json_fn: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """
    Parse task output into structured format.
    
    DRY helper - consolidates output parsing logic.
    
    Args:
        agent_output: Raw output from agent
        output_json: JSON schema if JSON output expected
        output_pydantic: Pydantic model if Pydantic output expected
        task_id: Task ID for logging
        clean_json_fn: Function to clean JSON output
        
    Returns:
        Dict with parsed output info:
        - output_format: "RAW", "JSON", or "Pydantic"
        - json_dict: Parsed JSON dict if applicable
        - pydantic: Pydantic model instance if applicable
    """
    result = {
        "output_format": "RAW",
        "json_dict": None,
        "pydantic": None,
    }
    
    if output_json:
        cleaned = clean_json_fn(agent_output) if clean_json_fn else agent_output
        try:
            parsed = json.loads(cleaned)
            result["json_dict"] = parsed
            result["output_format"] = "JSON"
        except Exception:
            logger.warning(f"Warning: Could not parse output of task {task_id} as JSON")
            logger.debug(f"Output that failed JSON parsing: {agent_output}")
    
    if output_pydantic:
        cleaned = clean_json_fn(agent_output) if clean_json_fn else agent_output
        try:
            parsed = json.loads(cleaned)
            pyd_obj = output_pydantic(**parsed)
            result["pydantic"] = pyd_obj
            result["output_format"] = "Pydantic"
        except Exception:
            logger.warning(f"Warning: Could not parse output of task {task_id} as Pydantic Model")
            logger.debug(f"Output that failed Pydantic parsing: {agent_output}")
    
    return result


def check_multimodal_dependencies() -> bool:
    """
    Check if multimodal dependencies are available.
    
    Returns:
        True if dependencies are available, False otherwise
    """
    try:
        import cv2  # noqa: F401
        import base64  # noqa: F401
        from moviepy import VideoFileClip  # noqa: F401
        return True
    except ImportError:
        return False


def get_multimodal_error_message() -> str:
    """Get error message for missing multimodal dependencies."""
    return "Please install with: pip install opencv-python moviepy"

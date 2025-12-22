"""
Utility functions for PraisonAI Agents evaluation framework.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


def save_result_to_file(
    result: Any,
    file_path: str,
    eval_id: Optional[str] = None,
    name: Optional[str] = None
) -> bool:
    """
    Save evaluation result to a file.
    
    Args:
        result: The evaluation result to save
        file_path: Path to save the result (supports {name}, {eval_id} placeholders)
        eval_id: Optional eval ID for placeholder substitution
        name: Optional name for placeholder substitution
        
    Returns:
        True if save was successful, False otherwise
    """
    try:
        formatted_path = file_path.format(name=name or "", eval_id=eval_id or "")
        path = Path(formatted_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if hasattr(result, 'to_dict'):
            data = result.to_dict()
        elif hasattr(result, '__dict__'):
            data = result.__dict__
        else:
            data = {"result": str(result)}
        
        path.write_text(json.dumps(data, indent=2, default=str))
        logger.debug(f"Saved result to: {formatted_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to save result: {e}")
        return False


def load_result_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Load evaluation result from a file.
    
    Args:
        file_path: Path to the result file
        
    Returns:
        Dictionary containing the result data, or None if load failed
    """
    try:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Result file not found: {file_path}")
            return None
        
        data = json.loads(path.read_text())
        return data
    except Exception as e:
        logger.warning(f"Failed to load result: {e}")
        return None


def format_score(score: float, max_score: float = 10.0) -> str:
    """
    Format a score for display.
    
    Args:
        score: The score value
        max_score: Maximum possible score
        
    Returns:
        Formatted score string
    """
    return f"{score:.1f}/{max_score:.0f}"


def format_percentage(value: float) -> str:
    """
    Format a value as a percentage.
    
    Args:
        value: Value between 0 and 1
        
    Returns:
        Formatted percentage string
    """
    return f"{value * 100:.1f}%"


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds for display.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 0.001:
        return f"{seconds * 1000000:.0f}μs"
    elif seconds < 1:
        return f"{seconds * 1000:.2f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"


def format_memory(mb: float) -> str:
    """
    Format memory usage for display.
    
    Args:
        mb: Memory in megabytes
        
    Returns:
        Formatted memory string
    """
    if mb < 1:
        return f"{mb * 1024:.1f} KB"
    elif mb < 1024:
        return f"{mb:.2f} MB"
    else:
        return f"{mb / 1024:.2f} GB"


def calculate_pass_rate(passed: int, total: int) -> float:
    """
    Calculate pass rate.
    
    Args:
        passed: Number of passed evaluations
        total: Total number of evaluations
        
    Returns:
        Pass rate as a float between 0 and 1
    """
    if total == 0:
        return 0.0
    return passed / total

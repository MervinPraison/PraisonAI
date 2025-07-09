"""Data models for PraisonAI agents system.

This module contains Pydantic models used throughout the system for
data validation and structured outputs.
"""

import json
from typing import Optional, Dict, Any, Literal

from pydantic import BaseModel, ConfigDict


class ReflectionOutput(BaseModel):
    """Model for agent self-reflection outputs.
    
    Attributes:
        reflection: The reflection text content
        satisfactory: Whether the reflection is satisfactory ("yes" or "no")
    """
    reflection: str
    satisfactory: Literal["yes", "no"]


class TaskOutput(BaseModel):
    """Model for task execution outputs.
    
    This model represents the output from a task execution, supporting
    multiple output formats including raw text, JSON, and Pydantic models.
    
    Attributes:
        description: Description of the task output
        summary: Optional summary of the output
        raw: Raw string output from the task
        pydantic: Optional Pydantic model if output is structured
        json_dict: Optional dictionary if output is JSON
        agent: Name of the agent that produced the output
        output_format: Format of the output (RAW, JSON, or Pydantic)
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    description: str
    summary: Optional[str] = None
    raw: str
    pydantic: Optional[BaseModel] = None
    json_dict: Optional[Dict[str, Any]] = None
    agent: str
    output_format: Literal["RAW", "JSON", "Pydantic"] = "RAW"

    def json(self) -> Optional[str]:
        """Get JSON string representation if output format is JSON.
        
        Returns:
            JSON string if format is JSON and json_dict exists, None otherwise
        """
        if self.output_format == "JSON" and self.json_dict:
            return json.dumps(self.json_dict)
        return None

    def to_dict(self) -> dict:
        """Convert output to dictionary format.
        
        Combines json_dict and pydantic model data if available.
        
        Returns:
            Dictionary representation of the output
        """
        output_dict = {}
        if self.json_dict:
            output_dict.update(self.json_dict)
        if self.pydantic:
            output_dict.update(self.pydantic.model_dump())
        return output_dict

    def __str__(self) -> str:
        """String representation of the task output.
        
        Returns:
            String representation based on output format
        """
        if self.pydantic:
            return str(self.pydantic)
        elif self.json_dict:
            return json.dumps(self.json_dict)
        else:
            return self.raw


__all__ = [
    'ReflectionOutput',
    'TaskOutput',
]
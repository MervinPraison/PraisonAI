"""
Lightweight output models for PraisonAI Agents.

This module contains Pydantic models that are used across the codebase.
It is kept separate from main.py to avoid importing rich at module level.
"""

import json
from typing import Optional, Dict, Any, Literal, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from ..telemetry.token_collector import TokenMetrics


class TaskOutput(BaseModel):
    """Output model for task results."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    description: str
    summary: Optional[str] = None
    raw: str
    pydantic: Optional[BaseModel] = None
    json_dict: Optional[Dict[str, Any]] = None
    agent: str
    output_format: Literal["RAW", "JSON", "Pydantic"] = "RAW"
    token_metrics: Optional['TokenMetrics'] = None

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

    def __str__(self) -> str:
        if self.pydantic:
            return str(self.pydantic)
        if self.json_dict:
            return json.dumps(self.json_dict, indent=2)
        return self.raw


class ReflectionOutput(BaseModel):
    """Output model for self-reflection results."""
    reflection: str
    satisfactory: Literal["yes", "no"]

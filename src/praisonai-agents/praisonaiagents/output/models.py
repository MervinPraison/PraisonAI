"""
Lightweight output models for PraisonAI Agents.

This module contains Pydantic models that are used across the codebase.
It is kept separate from main.py to avoid importing rich at module level.
"""

import json
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, ConfigDict

# Import token metrics at runtime so the forward reference in TaskOutput can be
# resolved by model_rebuild() below. Importing only under TYPE_CHECKING left the
# model perpetually "not fully defined", making any instantiation raise.
try:
    from ..telemetry.token_collector import TokenMetrics
except ImportError:
    TokenMetrics = None


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
    callback_error: Optional[str] = None
    non_fatal_errors: Optional[list[str]] = None

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


# Resolve the 'TokenMetrics' forward reference now that it is available at
# runtime, so TaskOutput can actually be instantiated.
TaskOutput.model_rebuild()

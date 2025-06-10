"""
Guardrail result classes for PraisonAI Agents.

This module provides the result types for guardrail validation,
following the same pattern as CrewAI for consistency.
"""

from typing import Any, Tuple, Union
from pydantic import BaseModel, Field
from ..main import TaskOutput


class GuardrailResult(BaseModel):
    """Result of a guardrail validation."""
    
    success: bool = Field(description="Whether the guardrail check passed")
    result: Union[str, TaskOutput, None] = Field(description="The result if modified, or None if unchanged")
    error: str = Field(default="", description="Error message if validation failed")
    
    @classmethod
    def from_tuple(cls, result: Tuple[bool, Any]) -> "GuardrailResult":
        """Create a GuardrailResult from a tuple returned by a guardrail function.
        
        Args:
            result: Tuple of (success, result_or_error)
            
        Returns:
            GuardrailResult: The structured result
        """
        success, data = result
        
        if success:
            return cls(
                success=True,
                result=data,
                error=""
            )
        else:
            return cls(
                success=False,
                result=None,
                error=str(data) if data else "Guardrail validation failed"
            )
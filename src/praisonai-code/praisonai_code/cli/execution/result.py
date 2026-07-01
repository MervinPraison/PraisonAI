"""
ExecutionResult - Result from execution.

Contains the output and metadata from an execution.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionResult:
    """
    Result from executing a request.
    
    Attributes:
        output: The text output from the agent
        run_id: Unique identifier for this execution
        success: Whether execution completed successfully
        error: Error message if execution failed
        metadata: Additional metadata about the execution
        tool_calls: List of tools that were called
        start_time: When execution started (perf_counter)
        end_time: When execution ended (perf_counter)
    """
    
    # Primary output
    output: str
    
    # Identity
    run_id: str = ""
    
    # Status
    success: bool = True
    error: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Tool tracking
    tool_calls: List[str] = field(default_factory=list)
    
    # Timing (raw perf_counter values)
    start_time: float = 0.0
    end_time: float = 0.0
    
    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "output": self.output,
            "run_id": self.run_id,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
            "tool_calls": self.tool_calls,
            "duration_ms": self.duration_ms,
        }
    
    @classmethod
    def from_error(cls, error: str, run_id: str = "") -> 'ExecutionResult':
        """Create a result from an error."""
        return cls(
            output="",
            run_id=run_id,
            success=False,
            error=error,
        )

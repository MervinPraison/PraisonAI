"""
Structured result types for workflow operations.

Provides type-safe error handling for workflow steps that distinguishes
between recoverable errors (retry/skip) and fatal errors (halt workflow).
Prevents error strings from flowing as valid data to subsequent steps.
"""

from typing import Optional, Any, Dict, List, Union, Literal
from dataclasses import dataclass
from enum import Enum
from ..errors import PraisonAIError


class StepStatus(Enum):
    """Status of a workflow step execution."""
    SUCCESS = "success"
    FAILED = "failed" 
    SKIPPED = "skipped"
    RETRYING = "retrying"


class ErrorStrategy(Enum):
    """Strategy for handling step errors."""
    STOP = "stop"      # Halt the entire workflow
    SKIP = "skip"      # Skip to next step  
    RETRY = "retry"    # Retry the step N times
    FALLBACK = "fallback"  # Use fallback output


@dataclass
class StepError:
    """
    Structured error information for workflow steps.
    
    Replaces opaque error strings with typed error context
    that enables proper retry logic and observability.
    """
    
    exception: Exception
    step_name: str
    retry_count: int = 0
    max_retries: int = 0
    is_retryable: bool = True
    error_strategy: ErrorStrategy = ErrorStrategy.STOP
    fallback_output: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}
    
    @property
    def can_retry(self) -> bool:
        """Returns True if this error can be retried."""
        return self.is_retryable and self.retry_count < self.max_retries
    
    @property
    def should_stop_workflow(self) -> bool:
        """Returns True if this error should stop the workflow."""
        return self.error_strategy == ErrorStrategy.STOP and not self.can_retry
    
    @property
    def should_use_fallback(self) -> bool:
        """Returns True if fallback output should be used."""
        return self.error_strategy == ErrorStrategy.FALLBACK
    
    def get_output_for_next_step(self) -> str:
        """
        Get the output that should be passed to the next step.
        
        Returns fallback output if available, otherwise a structured
        error indicator that won't be confused with real data.
        """
        if self.fallback_output:
            return self.fallback_output
        
        # Return a structured error marker that downstream steps can detect
        return f"[STEP_ERROR:{self.step_name}] {str(self.exception)}"


@dataclass
class StepResult:
    """
    Structured result for workflow step execution.
    
    Replaces string-only outputs with typed results that distinguish
    between successful output, error conditions, and control flow.
    """
    
    status: StepStatus
    output: Optional[str] = None
    error: Optional[StepError] = None
    stop_workflow: bool = False
    variables: Optional[Dict[str, Any]] = None
    step_name: str = ""
    execution_time_ms: Optional[float] = None
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.variables is None:
            self.variables = {}
        if self.context is None:
            self.context = {}
    
    @property
    def success(self) -> bool:
        """Returns True if the step succeeded."""
        return self.status == StepStatus.SUCCESS
    
    @property
    def failed(self) -> bool:
        """Returns True if the step failed."""
        return self.status == StepStatus.FAILED
    
    @property
    def can_retry(self) -> bool:
        """Returns True if a failed step can be retried."""
        return self.failed and self.error and self.error.can_retry
    
    @classmethod
    def success_result(cls, output: str, step_name: str = "",
                      variables: Optional[Dict[str, Any]] = None,
                      execution_time_ms: Optional[float] = None,
                      context: Optional[Dict[str, Any]] = None) -> "StepResult":
        """Create a successful step result."""
        return cls(
            status=StepStatus.SUCCESS,
            output=output,
            step_name=step_name,
            variables=variables,
            execution_time_ms=execution_time_ms,
            context=context
        )
    
    @classmethod
    def failed_result(cls, error: StepError, step_name: str = "",
                     context: Optional[Dict[str, Any]] = None) -> "StepResult":
        """Create a failed step result."""
        return cls(
            status=StepStatus.FAILED,
            error=error,
            stop_workflow=error.should_stop_workflow,
            step_name=step_name,
            context=context
        )
    
    @classmethod
    def skipped_result(cls, reason: str, step_name: str = "",
                      context: Optional[Dict[str, Any]] = None) -> "StepResult":
        """Create a skipped step result."""
        return cls(
            status=StepStatus.SKIPPED,
            output=f"[SKIPPED] {reason}",
            step_name=step_name,
            context=context
        )
    
    def to_legacy_string(self) -> str:
        """
        Convert to legacy string output for backward compatibility.
        
        For successful results, returns the output.
        For failed results, returns a structured error string.
        """
        if self.success:
            return self.output or ""
        elif self.failed and self.error:
            return self.error.get_output_for_next_step()
        elif self.status == StepStatus.SKIPPED:
            return self.output or ""
        else:
            return f"[UNKNOWN_STATUS:{self.status}] Step result unavailable"


@dataclass
class WorkflowResult:
    """
    Complete result of a workflow execution.
    
    Provides visibility into the success/failure of individual steps
    and enables proper error handling at the workflow level.
    """
    
    success: bool
    steps: List[StepResult]
    final_output: Optional[str] = None
    error_summary: Optional[str] = None
    total_execution_time_ms: Optional[float] = None
    variables: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.variables is None:
            self.variables = {}
        if self.context is None:
            self.context = {}
    
    @property
    def failed_steps(self) -> List[StepResult]:
        """Returns list of failed steps."""
        return [step for step in self.steps if step.failed]
    
    @property
    def successful_steps(self) -> List[StepResult]:
        """Returns list of successful steps."""
        return [step for step in self.steps if step.success]
    
    @property
    def has_failures(self) -> bool:
        """Returns True if any steps failed."""
        return len(self.failed_steps) > 0
    
    @property
    def retryable_failures(self) -> List[StepResult]:
        """Returns list of failed steps that can be retried."""
        return [step for step in self.failed_steps if step.can_retry]
    
    def get_step_by_name(self, step_name: str) -> Optional[StepResult]:
        """Get a step result by name."""
        for step in self.steps:
            if step.step_name == step_name:
                return step
        return None


# Exception types for workflow errors
class WorkflowError(PraisonAIError):
    """Base class for workflow execution errors."""
    
    def __init__(self, message: str, workflow_name: str = "unknown", 
                 step_name: Optional[str] = None, **kwargs):
        super().__init__(message, error_category="validation", **kwargs)
        self.workflow_name = workflow_name
        self.step_name = step_name
        if step_name:
            self.context["step_name"] = step_name
        self.context["workflow_name"] = workflow_name


class StepExecutionError(WorkflowError):
    """Error during step execution."""
    
    def __init__(self, message: str, step_name: str, original_exception: Exception,
                 **kwargs):
        super().__init__(message, step_name=step_name, is_retryable=True, **kwargs)
        self.original_exception = original_exception
        self.context["original_error"] = str(original_exception)
        self.context["original_error_type"] = type(original_exception).__name__


class WorkflowConfigError(WorkflowError):
    """Error in workflow configuration."""
    
    def __init__(self, message: str, config_field: Optional[str] = None, **kwargs):
        super().__init__(message, is_retryable=False, **kwargs)
        if config_field:
            self.context["config_field"] = config_field


# Export main types
__all__ = [
    "StepStatus",
    "ErrorStrategy", 
    "StepError",
    "StepResult",
    "WorkflowResult",
    "WorkflowError",
    "StepExecutionError", 
    "WorkflowConfigError"
]
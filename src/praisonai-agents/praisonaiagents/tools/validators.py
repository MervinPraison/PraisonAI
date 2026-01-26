"""Tool validation protocols and types."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ValidationResult:
    """Result of a validation check.
    
    Example:
        result = ValidationResult(valid=False, errors=["Invalid input"])
        if not result:
            print(f"Validation failed: {result.errors}")
    """
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    remediation: Optional[str] = None
    
    def __bool__(self) -> bool:
        return self.valid
    
    @classmethod
    def success(cls) -> "ValidationResult":
        """Create a successful validation result."""
        return cls(valid=True)
    
    @classmethod
    def failure(cls, errors: List[str], remediation: Optional[str] = None) -> "ValidationResult":
        """Create a failed validation result."""
        return cls(valid=False, errors=errors, remediation=remediation)
    
    def add_error(self, error: str) -> "ValidationResult":
        """Add an error and mark as invalid."""
        self.errors.append(error)
        self.valid = False
        return self
    
    def add_warning(self, warning: str) -> "ValidationResult":
        """Add a warning (doesn't affect validity)."""
        self.warnings.append(warning)
        return self


@runtime_checkable
class ToolValidatorProtocol(Protocol):
    """Protocol for tool argument and result validators."""
    
    def validate_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Validate tool arguments before execution.
        
        Args:
            tool_name: Name of the tool being called
            args: Arguments to validate
            context: Optional execution context
            
        Returns:
            ValidationResult with valid=True if args are valid
        """
        ...
    
    def validate_result(
        self,
        tool_name: str,
        result: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Validate tool result after execution.
        
        Args:
            tool_name: Name of the tool that was called
            result: Result to validate
            context: Optional execution context
            
        Returns:
            ValidationResult with valid=True if result is valid
        """
        ...


@runtime_checkable
class AsyncToolValidatorProtocol(Protocol):
    """Async version of tool validator."""
    
    async def validate_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        ...
    
    async def validate_result(
        self,
        tool_name: str,
        result: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        ...


class PassthroughValidator:
    """Validator that always passes. Default when no validator configured."""
    
    def validate_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        return ValidationResult(valid=True)
    
    def validate_result(
        self,
        tool_name: str,
        result: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        return ValidationResult(valid=True)

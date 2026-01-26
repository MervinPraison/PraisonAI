"""Unit tests for tools/validators.py"""
import pytest
from praisonaiagents.tools.validators import (
    ValidationResult,
    ToolValidatorProtocol,
    AsyncToolValidatorProtocol,
    PassthroughValidator,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""
    
    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert bool(result) is True
        assert result.errors == []
        assert result.warnings == []
        assert result.remediation is None
    
    def test_invalid_result_with_errors(self):
        """Test creating an invalid result with errors."""
        result = ValidationResult(
            valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
            remediation="Fix by doing X"
        )
        assert result.valid is False
        assert bool(result) is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
        assert result.remediation == "Fix by doing X"
    
    def test_success_factory(self):
        """Test ValidationResult.success() factory method."""
        result = ValidationResult.success()
        assert result.valid is True
        assert result.errors == []
    
    def test_failure_factory(self):
        """Test ValidationResult.failure() factory method."""
        result = ValidationResult.failure(
            errors=["Something went wrong"],
            remediation="Try again"
        )
        assert result.valid is False
        assert result.errors == ["Something went wrong"]
        assert result.remediation == "Try again"
    
    def test_failure_factory_without_remediation(self):
        """Test failure factory without remediation."""
        result = ValidationResult.failure(errors=["Error"])
        assert result.valid is False
        assert result.remediation is None
    
    def test_add_error(self):
        """Test add_error method."""
        result = ValidationResult(valid=True)
        returned = result.add_error("New error")
        
        assert result.valid is False
        assert "New error" in result.errors
        assert returned is result  # Returns self for chaining
    
    def test_add_error_chaining(self):
        """Test chaining add_error calls."""
        result = ValidationResult(valid=True)
        result.add_error("Error 1").add_error("Error 2")
        
        assert result.valid is False
        assert len(result.errors) == 2
    
    def test_add_warning(self):
        """Test add_warning method."""
        result = ValidationResult(valid=True)
        returned = result.add_warning("Warning message")
        
        assert result.valid is True  # Warnings don't affect validity
        assert "Warning message" in result.warnings
        assert returned is result
    
    def test_add_warning_preserves_validity(self):
        """Test that warnings don't change validity."""
        result = ValidationResult(valid=True)
        result.add_warning("W1").add_warning("W2")
        
        assert result.valid is True
        assert len(result.warnings) == 2


class TestToolValidatorProtocol:
    """Tests for ToolValidatorProtocol."""
    
    def test_protocol_is_runtime_checkable(self):
        """Test that protocol is runtime checkable."""
        validator = PassthroughValidator()
        assert isinstance(validator, ToolValidatorProtocol)
    
    def test_custom_validator_implements_protocol(self):
        """Test custom validator implements protocol."""
        class CustomValidator:
            def validate_args(self, tool_name, args, context=None):
                return ValidationResult(valid=True)
            
            def validate_result(self, tool_name, result, context=None):
                return ValidationResult(valid=True)
        
        validator = CustomValidator()
        assert isinstance(validator, ToolValidatorProtocol)
    
    def test_incomplete_validator_not_protocol(self):
        """Test incomplete validator doesn't match protocol."""
        class IncompleteValidator:
            def validate_args(self, tool_name, args, context=None):
                return ValidationResult(valid=True)
            # Missing validate_result
        
        validator = IncompleteValidator()
        assert not isinstance(validator, ToolValidatorProtocol)


class TestAsyncToolValidatorProtocol:
    """Tests for AsyncToolValidatorProtocol."""
    
    def test_protocol_is_runtime_checkable(self):
        """Test that async protocol is runtime checkable."""
        class AsyncValidator:
            async def validate_args(self, tool_name, args, context=None):
                return ValidationResult(valid=True)
            
            async def validate_result(self, tool_name, result, context=None):
                return ValidationResult(valid=True)
        
        validator = AsyncValidator()
        assert isinstance(validator, AsyncToolValidatorProtocol)


class TestPassthroughValidator:
    """Tests for PassthroughValidator."""
    
    def test_validate_args_always_passes(self):
        """Test validate_args always returns valid."""
        validator = PassthroughValidator()
        result = validator.validate_args("any_tool", {"arg": "value"})
        
        assert result.valid is True
    
    def test_validate_result_always_passes(self):
        """Test validate_result always returns valid."""
        validator = PassthroughValidator()
        result = validator.validate_result("any_tool", {"output": "data"})
        
        assert result.valid is True
    
    def test_validate_args_with_context(self):
        """Test validate_args with context."""
        validator = PassthroughValidator()
        result = validator.validate_args(
            "tool",
            {"arg": "value"},
            context={"user": "test"}
        )
        assert result.valid is True
    
    def test_validate_result_with_context(self):
        """Test validate_result with context."""
        validator = PassthroughValidator()
        result = validator.validate_result(
            "tool",
            "result",
            context={"session": "123"}
        )
        assert result.valid is True
    
    def test_implements_protocol(self):
        """Test PassthroughValidator implements ToolValidatorProtocol."""
        validator = PassthroughValidator()
        assert isinstance(validator, ToolValidatorProtocol)

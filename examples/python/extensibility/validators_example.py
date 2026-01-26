"""Example: Tool Validation with Custom Validators

This example demonstrates how to use ValidationResult and implement
custom validators using the ToolValidatorProtocol.
"""
from praisonaiagents.tools import (
    ValidationResult,
    ToolValidatorProtocol,
    PassthroughValidator,
)


def example_validation_result():
    """Demonstrate ValidationResult usage."""
    print("=" * 50)
    print("ValidationResult Examples")
    print("=" * 50)
    
    # 1. Success factory
    success = ValidationResult.success()
    print(f"\n1. Success: valid={success.valid}, bool={bool(success)}")
    
    # 2. Failure factory
    failure = ValidationResult.failure(
        errors=["Query cannot be empty", "Missing required field"],
        remediation="Provide a non-empty query string"
    )
    print(f"\n2. Failure: valid={failure.valid}")
    print(f"   Errors: {failure.errors}")
    print(f"   Remediation: {failure.remediation}")
    
    # 3. Fluent API - building incrementally
    result = ValidationResult(valid=True)
    result.add_warning("Query is very long, may be slow")
    result.add_warning("Consider using pagination")
    print(f"\n3. With warnings: valid={result.valid}, warnings={result.warnings}")
    
    # 4. Adding errors changes validity
    result.add_error("Rate limit exceeded")
    print(f"\n4. After error: valid={result.valid}, errors={result.errors}")


class InputLengthValidator:
    """Custom validator that checks string input lengths."""
    
    def __init__(self, max_length: int = 100):
        self.max_length = max_length
    
    def validate_args(self, tool_name, args, context=None):
        """Validate that string arguments don't exceed max length."""
        for key, value in args.items():
            if isinstance(value, str) and len(value) > self.max_length:
                return ValidationResult.failure(
                    errors=[f"Argument '{key}' ({len(value)} chars) exceeds limit ({self.max_length})"],
                    remediation=f"Truncate '{key}' to {self.max_length} characters or less"
                )
        return ValidationResult.success()
    
    def validate_result(self, tool_name, result, context=None):
        """Validate tool results."""
        return ValidationResult.success()


class TypeValidator:
    """Custom validator that checks argument types."""
    
    def __init__(self, type_specs: dict):
        """
        Args:
            type_specs: Dict mapping arg names to expected types
                       e.g., {"query": str, "limit": int}
        """
        self.type_specs = type_specs
    
    def validate_args(self, tool_name, args, context=None):
        result = ValidationResult(valid=True)
        
        for arg_name, expected_type in self.type_specs.items():
            if arg_name in args:
                actual_value = args[arg_name]
                if not isinstance(actual_value, expected_type):
                    result.add_error(
                        f"Argument '{arg_name}' must be {expected_type.__name__}, "
                        f"got {type(actual_value).__name__}"
                    )
        
        if not result.valid:
            result.remediation = "Check argument types and try again"
        
        return result
    
    def validate_result(self, tool_name, result, context=None):
        return ValidationResult.success()


def example_custom_validators():
    """Demonstrate custom validator implementations."""
    print("\n" + "=" * 50)
    print("Custom Validator Examples")
    print("=" * 50)
    
    # 1. InputLengthValidator
    print("\n1. InputLengthValidator:")
    validator = InputLengthValidator(max_length=50)
    
    # Valid input
    result = validator.validate_args("search", {"query": "short query"})
    print(f"   Short query: valid={result.valid}")
    
    # Invalid input
    long_query = "x" * 100
    result = validator.validate_args("search", {"query": long_query})
    print(f"   Long query: valid={result.valid}")
    print(f"   Error: {result.errors[0]}")
    print(f"   Fix: {result.remediation}")
    
    # 2. TypeValidator
    print("\n2. TypeValidator:")
    validator = TypeValidator({"query": str, "limit": int, "offset": int})
    
    # Valid types
    result = validator.validate_args("search", {"query": "test", "limit": 10})
    print(f"   Correct types: valid={result.valid}")
    
    # Invalid types
    result = validator.validate_args("search", {"query": 123, "limit": "ten"})
    print(f"   Wrong types: valid={result.valid}")
    for error in result.errors:
        print(f"   - {error}")
    
    # 3. Protocol compliance check
    print("\n3. Protocol Compliance:")
    print(f"   InputLengthValidator: {isinstance(InputLengthValidator(), ToolValidatorProtocol)}")
    print(f"   TypeValidator: {isinstance(TypeValidator({}), ToolValidatorProtocol)}")
    print(f"   PassthroughValidator: {isinstance(PassthroughValidator(), ToolValidatorProtocol)}")


def example_passthrough_validator():
    """Demonstrate the default PassthroughValidator."""
    print("\n" + "=" * 50)
    print("PassthroughValidator Example")
    print("=" * 50)
    
    validator = PassthroughValidator()
    
    # Always returns valid
    result = validator.validate_args("any_tool", {"any": "args"})
    print(f"\nvalidate_args: valid={result.valid}")
    
    result = validator.validate_result("any_tool", {"any": "result"})
    print(f"validate_result: valid={result.valid}")
    
    print("\nPassthroughValidator is useful as a default when no validation is needed.")


if __name__ == "__main__":
    example_validation_result()
    example_custom_validators()
    example_passthrough_validator()
    
    print("\n" + "=" * 50)
    print("All examples completed!")
    print("=" * 50)

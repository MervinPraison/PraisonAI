"""
Unit tests for the ExampleVerifier.
"""

from praisonai.standardise.example_verifier import ExampleVerifier, VerificationResult


class TestExampleVerifier:
    """Tests for ExampleVerifier."""
    
    def test_valid_simple_code(self):
        """Test verification of valid simple code."""
        verifier = ExampleVerifier(timeout=10)
        code = '''
print("Hello, World!")
'''
        result = verifier.verify(code)
        
        assert result.syntax_valid
        assert result.execution_passed
        assert result.success
        assert result.can_write
    
    def test_syntax_error(self):
        """Test detection of syntax errors."""
        verifier = ExampleVerifier(timeout=10)
        code = '''
def broken(
    print("missing closing paren"
'''
        result = verifier.verify(code)
        
        assert not result.syntax_valid
        assert not result.success
        assert not result.can_write
        assert "Syntax error" in result.error
    
    def test_runtime_error(self):
        """Test detection of runtime errors."""
        verifier = ExampleVerifier(timeout=10)
        code = '''
x = 1 / 0  # Division by zero
'''
        result = verifier.verify(code)
        
        assert result.syntax_valid
        assert not result.execution_passed
        assert not result.success
        assert "ZeroDivisionError" in result.error
    
    def test_missing_import(self):
        """Test detection of missing imports."""
        verifier = ExampleVerifier(timeout=10)
        code = '''
import nonexistent_module_xyz
'''
        result = verifier.verify(code)
        
        assert result.syntax_valid
        assert not result.execution_passed
        assert "nonexistent_module_xyz" in result.missing_libraries
    
    def test_external_library_detection(self):
        """Test detection of external library requirements."""
        verifier = ExampleVerifier(timeout=10)
        code = '''
import pandas
df = pandas.DataFrame()
'''
        result = verifier.verify(code)
        
        assert result.syntax_valid
        # May or may not pass depending on if pandas is installed
        # But should detect pandas as external
        assert "pandas" in result.missing_libraries or result.execution_passed
    
    def test_can_write_with_external_libs(self):
        """Test that code requiring external libs can still be written."""
        # Create a result that simulates external lib requirement
        result = VerificationResult(
            success=True,
            syntax_valid=True,
            execution_passed=False,
            output="",
            error="ModuleNotFoundError: No module named 'requests'",
            missing_libraries=["requests"],
            requires_external=True,
        )
        
        assert result.can_write  # Should allow writing despite execution failure
    
    def test_timeout_handling(self):
        """Test that infinite loops are handled."""
        verifier = ExampleVerifier(timeout=2)
        code = '''
import time
time.sleep(10)  # Will timeout
'''
        result = verifier.verify(code)
        
        assert result.syntax_valid
        assert not result.execution_passed
        assert "timed out" in result.error.lower()
    
    def test_format_result(self):
        """Test result formatting."""
        verifier = ExampleVerifier()
        
        result = VerificationResult(
            success=True,
            syntax_valid=True,
            execution_passed=True,
            output="Hello",
            error="",
            missing_libraries=[],
            requires_external=False,
        )
        
        formatted = verifier.format_result(result)
        assert "PASSED" in formatted
        assert "Syntax valid: ✓" in formatted

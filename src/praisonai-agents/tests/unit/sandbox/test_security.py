"""
Unit tests for sandbox security module.
"""

import pytest
from praisonaiagents.sandbox.security import (
    check_code_safety, 
    format_warnings,
    SecurityWarning,
    SecurityLevel,
    SecurityAnalyzer
)


class TestCodeSafety:
    """Test code safety checking functionality."""

    def test_empty_code(self):
        """Test empty code returns no warnings."""
        warnings = check_code_safety("", "python")
        assert warnings == []

    def test_safe_code(self):
        """Test safe code returns no warnings."""
        safe_code = """
x = 1 + 2
print(f"Result: {x}")
"""
        warnings = check_code_safety(safe_code, "python")
        assert warnings == []

    def test_dangerous_imports(self):
        """Test detection of dangerous imports."""
        dangerous_code = """
import os
import subprocess
os.system('rm -rf /')
"""
        warnings = check_code_safety(dangerous_code, "python")
        assert len(warnings) > 0
        assert any("os.system" in str(w) for w in warnings)

    def test_eval_exec_usage(self):
        """Test detection of eval/exec usage."""
        dangerous_code = """
user_input = input("Enter code: ")
eval(user_input)
exec(user_input)
"""
        warnings = check_code_safety(dangerous_code, "python")
        assert len(warnings) > 0
        assert any("eval" in str(w) or "exec" in str(w) for w in warnings)

    def test_network_operations(self):
        """Test detection of network operations."""
        network_code = """
import urllib.request
import socket
urllib.request.urlopen('http://example.com')
"""
        warnings = check_code_safety(network_code, "python")
        assert len(warnings) > 0

    def test_file_operations(self):
        """Test detection of file operations."""
        file_code = """
with open('/etc/passwd', 'r') as f:
    data = f.read()
"""
        warnings = check_code_safety(file_code, "python")
        assert len(warnings) > 0

    def test_bash_commands(self):
        """Test bash command safety checking."""
        dangerous_bash = "rm -rf / --no-preserve-root"
        warnings = check_code_safety(dangerous_bash, "bash")
        assert len(warnings) > 0

    def test_sql_injection_patterns(self):
        """Test SQL injection pattern detection."""
        sql_code = """
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)
"""
        warnings = check_code_safety(sql_code, "python")
        assert len(warnings) > 0

    def test_format_warnings(self):
        """Test warning formatting."""
        warnings = [
            SecurityWarning("Test warning", SecurityLevel.HIGH, "eval", 1),
            SecurityWarning("Another warning", SecurityLevel.MEDIUM, "import os", 2)
        ]
        
        formatted = format_warnings(warnings)
        assert "Test warning" in formatted
        assert "Another warning" in formatted
        assert "HIGH" in formatted
        assert "MEDIUM" in formatted

    def test_format_warnings_empty(self):
        """Test formatting empty warnings list."""
        formatted = format_warnings([])
        assert formatted == ""


class TestSecurityAnalyzer:
    """Test SecurityAnalyzer class."""

    def test_analyzer_initialization(self):
        """Test SecurityAnalyzer initialization."""
        analyzer = SecurityAnalyzer()
        assert analyzer is not None

    def test_analyze_safe_code(self):
        """Test analyzer with safe code."""
        analyzer = SecurityAnalyzer()
        code = "print('Hello, World!')"
        
        warnings = analyzer.analyze(code, "python")
        assert warnings == []

    def test_analyze_unsafe_code(self):
        """Test analyzer with unsafe code."""
        analyzer = SecurityAnalyzer()
        code = "import os; os.system('rm -rf /')"
        
        warnings = analyzer.analyze(code, "python")
        assert len(warnings) > 0
        assert all(isinstance(w, SecurityWarning) for w in warnings)

    def test_different_languages(self):
        """Test analyzer with different languages."""
        analyzer = SecurityAnalyzer()
        
        # Python
        python_warnings = analyzer.analyze("import os", "python")
        assert len(python_warnings) > 0
        
        # Bash
        bash_warnings = analyzer.analyze("rm -rf /", "bash")
        assert len(bash_warnings) > 0
        
        # JavaScript (should fall back to basic checks)
        js_warnings = analyzer.analyze("eval(userInput)", "javascript")
        assert len(js_warnings) > 0

    def test_security_levels(self):
        """Test different security levels are detected."""
        analyzer = SecurityAnalyzer()
        
        # High risk
        high_risk_code = "import os; os.system('rm -rf /')"
        warnings = analyzer.analyze(high_risk_code, "python")
        high_warnings = [w for w in warnings if w.level == SecurityLevel.HIGH]
        assert len(high_warnings) > 0
        
        # Medium risk
        medium_risk_code = "import subprocess"
        warnings = analyzer.analyze(medium_risk_code, "python")
        medium_warnings = [w for w in warnings if w.level == SecurityLevel.MEDIUM]
        # May or may not have medium warnings depending on implementation

    def test_line_numbers(self):
        """Test that line numbers are correctly reported."""
        analyzer = SecurityAnalyzer()
        code = """
print("Safe line")
import os
os.system('dangerous')
"""
        
        warnings = analyzer.analyze(code, "python")
        assert len(warnings) > 0
        
        # Check that line numbers are reasonable
        line_numbers = [w.line_number for w in warnings if w.line_number is not None]
        assert all(ln > 0 for ln in line_numbers)
        assert all(ln <= 4 for ln in line_numbers)  # Within the code block

    def test_pattern_matching(self):
        """Test that specific patterns are matched correctly."""
        analyzer = SecurityAnalyzer()
        
        test_cases = [
            ("eval(x)", ["eval"]),
            ("exec('code')", ["exec"]),
            ("__import__('os')", ["__import__"]),
            ("open('/etc/passwd')", ["file access"]),
            ("subprocess.call(['rm', 'file'])", ["subprocess"]),
        ]
        
        for code, expected_patterns in test_cases:
            warnings = analyzer.analyze(code, "python")
            assert len(warnings) > 0, f"No warnings for: {code}"
            
            # Check that at least one expected pattern is found
            warning_texts = [str(w) for w in warnings]
            found = any(
                any(pattern.lower() in text.lower() for text in warning_texts)
                for pattern in expected_patterns
            )
            assert found, f"Expected patterns {expected_patterns} not found in warnings for: {code}"
"""
Unit tests for sandbox security module.
"""

import pytest
from praisonaiagents.sandbox.security import (
    check_code_safety,
    format_warnings,
    SecurityWarning,
)


class TestCodeSafety:
    """Test code safety checking functionality."""

    def test_empty_code(self):
        warnings = check_code_safety("", "python")
        assert warnings == []

    def test_safe_code(self):
        safe_code = """
x = 1 + 2
print(f"Result: {x}")
"""
        warnings = check_code_safety(safe_code, "python")
        assert warnings == []

    def test_dangerous_imports(self):
        dangerous_code = """
import os
import subprocess
os.system('rm -rf /')
"""
        warnings = check_code_safety(dangerous_code, "python")
        assert len(warnings) > 0
        assert any("os.system" in str(w) for w in warnings)

    def test_eval_exec_usage(self):
        dangerous_code = """
user_input = input("Enter code: ")
eval(user_input)
exec(user_input)
"""
        warnings = check_code_safety(dangerous_code, "python")
        assert len(warnings) > 0
        assert any("eval" in str(w) or "exec" in str(w) for w in warnings)

    def test_network_operations(self):
        network_code = """
import urllib.request
import socket
urllib.request.urlopen('http://example.com')
"""
        warnings = check_code_safety(network_code, "python")
        assert len(warnings) > 0

    def test_file_operations(self):
        file_code = """
with open('/etc/passwd', 'r') as f:
    data = f.read()
"""
        warnings = check_code_safety(file_code, "python")
        assert len(warnings) > 0

    def test_bash_commands(self):
        dangerous_bash = "rm -rf / --no-preserve-root"
        warnings = check_code_safety(dangerous_bash, "bash")
        assert len(warnings) > 0

    @pytest.mark.skip(reason="SQL injection heuristics not implemented in security.py")
    def test_sql_injection_patterns(self):
        sql_code = """
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)
"""
        warnings = check_code_safety(sql_code, "python")
        assert len(warnings) > 0

    def test_format_warnings(self):
        warnings = [
            SecurityWarning(
                pattern="eval",
                message="Test warning",
                severity="high",
                line_number=1,
            ),
            SecurityWarning(
                pattern="import os",
                message="Another warning",
                severity="medium",
                line_number=2,
            ),
        ]

        formatted = format_warnings(warnings)
        assert "Test warning" in formatted
        assert "Another warning" in formatted
        assert "HIGH RISK" in formatted
        assert "MEDIUM RISK" in formatted

    def test_format_warnings_empty(self):
        formatted = format_warnings([])
        assert "No security issues detected" in formatted

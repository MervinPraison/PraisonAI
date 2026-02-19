"""
Security regression tests for python_tools.py sandbox.

Tests that known exploit vectors are blocked and that
legitimate code still executes correctly.
"""

from __future__ import annotations

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────


class _SandboxHarness:
    """Directly exercises PythonTools sandbox without installing black/pylint."""

    def __init__(self):
        # Import the class but bypass _check_dependencies
        from praisonaiagents.tools.python_tools import PythonTools
        self._pt = PythonTools.__new__(PythonTools)

    def run(self, code: str) -> dict:
        return self._pt.execute_code.__wrapped__(self._pt, code)


@pytest.fixture
def sandbox():
    return _SandboxHarness()


# ── Exploit Vectors (all must be BLOCKED) ───────────────────────────────────


class TestSandboxEscapePrevention:
    """Verify that known sandbox escape vectors are blocked."""

    def test_getattr_concat_blocked(self, sandbox):
        """getattr + string concat to access __class__ must fail."""
        result = sandbox.run("c = getattr((), '__cl' + 'ass__')")
        assert result["success"] is False
        assert "restricted" in result["stderr"].lower()

    def test_getattr_dunder_base_blocked(self, sandbox):
        """getattr to access __bases__ must fail."""
        result = sandbox.run("getattr(object, '__ba' + 'ses__')")
        assert result["success"] is False

    def test_getattr_dunder_subclasses_blocked(self, sandbox):
        """getattr to access __subclasses__ must fail."""
        result = sandbox.run("getattr(type, '__sub' + 'classes__')")
        assert result["success"] is False

    def test_dot_dunder_class_blocked(self, sandbox):
        """Direct .__class__ access blocked by AST check."""
        result = sandbox.run("x = ().__class__")
        assert result["success"] is False
        assert "restricted" in result["stderr"].lower()

    def test_dot_dunder_subclasses_blocked(self, sandbox):
        """Direct .__subclasses__ access blocked by AST or text check."""
        result = sandbox.run("x = object.__subclasses__()")
        assert result["success"] is False

    def test_dot_dunder_globals_blocked(self, sandbox):
        """.__globals__ access blocked."""
        result = sandbox.run("x = print.__globals__")
        assert result["success"] is False

    def test_import_statement_blocked(self, sandbox):
        """import os must be blocked."""
        result = sandbox.run("import os")
        assert result["success"] is False

    def test_from_import_blocked(self, sandbox):
        """from os import system must be blocked."""
        result = sandbox.run("from os import system")
        assert result["success"] is False

    def test_setattr_call_blocked(self, sandbox):
        """setattr() call blocked by AST check."""
        result = sandbox.run("setattr(type, 'x', 1)")
        assert result["success"] is False

    def test_dir_call_blocked(self, sandbox):
        """dir() call blocked by AST check."""
        result = sandbox.run("print(dir(type))")
        assert result["success"] is False

    def test_eval_blocked(self, sandbox):
        """eval() blocked by both builtins and AST."""
        result = sandbox.run("eval('1+1')")
        assert result["success"] is False

    def test_exec_blocked(self, sandbox):
        """exec() blocked."""
        result = sandbox.run("exec('print(1)')")
        assert result["success"] is False

    def test_open_blocked(self, sandbox):
        """open() blocked."""
        result = sandbox.run("open('/etc/passwd')")
        assert result["success"] is False

    def test_dunder_import_blocked(self, sandbox):
        """__import__() blocked."""
        result = sandbox.run("__import__('os')")
        assert result["success"] is False


# ── Legitimate Code (all must PASS) ─────────────────────────────────────────


class TestSandboxLegitimateCode:
    """Verify that safe code still executes correctly."""

    def test_arithmetic(self, sandbox):
        result = sandbox.run("print(1 + 2 * 3)")
        assert result["success"] is True
        assert "7" in result["stdout"]

    def test_list_operations(self, sandbox):
        result = sandbox.run("print(sorted([3, 1, 2]))")
        assert result["success"] is True
        assert "[1, 2, 3]" in result["stdout"]

    def test_type_constructors(self, sandbox):
        result = sandbox.run("print(int('42'), float('3.14'), str(100))")
        assert result["success"] is True
        assert "42" in result["stdout"]

    def test_dict_operations(self, sandbox):
        result = sandbox.run("d = {'a': 1, 'b': 2}; print(len(d), sum(d.values()))")
        assert result["success"] is True
        assert "2 3" in result["stdout"]

    def test_string_operations(self, sandbox):
        result = sandbox.run("print('hello'.upper())")
        assert result["success"] is True
        assert "HELLO" in result["stdout"]

    def test_exceptions_catchable(self, sandbox):
        code = """
try:
    raise ValueError('test error')
except ValueError as e:
    print(f'caught: {e}')
"""
        result = sandbox.run(code)
        assert result["success"] is True
        assert "caught: test error" in result["stdout"]

    def test_functions_definable(self, sandbox):
        code = """
def add(a, b):
    return a + b
print(add(3, 4))
"""
        result = sandbox.run(code)
        assert result["success"] is True
        assert "7" in result["stdout"]

    def test_safe_getattr_on_data(self, sandbox):
        """getattr on normal (non-dunder) attributes should work."""
        result = sandbox.run("print(hasattr({'a': 1}, 'keys'))")
        assert result["success"] is True
        assert "True" in result["stdout"]

    def test_list_comprehension(self, sandbox):
        result = sandbox.run("print([x**2 for x in range(5)])")
        assert result["success"] is True
        assert "[0, 1, 4, 9, 16]" in result["stdout"]

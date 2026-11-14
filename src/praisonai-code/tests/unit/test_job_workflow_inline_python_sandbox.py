"""Inline python steps must not allow dunder/private attribute traversal (#6367)."""

import pytest

from praisonai_code.cli.features.job_workflow import JobWorkflowExecutor


@pytest.fixture
def executor():
    return JobWorkflowExecutor({"steps": []}, "test.yaml")


@pytest.mark.parametrize("code", [
    "().__class__",
    "().__class__.__base__.__subclasses__()",
    "getattr((), '__class__')",
    "getattr(getattr((), '__class__'), '__base__')",
    "getattr((), '_' + '_class__')",
    "hasattr((), '__class__')",
    "x = ().__class__",
    # str subclass overriding startswith must not evade the runtime check
    "getattr((), type('S', (str,), {'startswith': {}.get})('__class__'))",
    "getattr(getattr, type('S', (str,), {'startswith': {}.get})('__globals__'))",
    # format-string field traversal bypasses attribute checks
    "'{0.__globals__}'.format(getattr)",
    "'{0.__globals__}'.format_map([getattr])",
    "str.format('{0.__globals__}', getattr)",
    "getattr('{0.__globals__}', 'format')(getattr)",
])
def test_private_attribute_access_blocked(executor, code):
    result = executor._exec_inline_python(code, {}, {})
    assert result["ok"] is False
    assert "class" not in result.get("output", "")
    assert "environ" not in result.get("output", "")


@pytest.mark.parametrize("code,expected", [
    ("len([1, 2, 3])", "3"),
    ("'abc'.upper()", "ABC"),
    ("getattr('abc', 'upper')()", "ABC"),
    ("hasattr('abc', 'upper')", "True"),
    ("result = 1 + 2", "3"),
])
def test_safe_expressions_still_work(executor, code, expected):
    result = executor._exec_inline_python(code, {}, {})
    assert result == {"ok": True, "output": expected}

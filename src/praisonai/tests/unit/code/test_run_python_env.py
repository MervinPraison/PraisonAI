"""run_python must not hand the operator's secrets to the code it runs.

execute_command() already built its child env with the shared scrub helper;
run_python(), its sibling, inherited os.environ whole.
"""
from praisonai.code.tools.execute_command import run_python


def test_run_python_does_not_inherit_operator_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    result = run_python("import os; print(sorted(os.environ.items()))")
    assert result["success"], result
    assert "sk-should-not-leak" not in result["stdout"]


def test_run_python_still_runs():
    assert run_python("print(6 * 7)")["stdout"].strip() == "42"

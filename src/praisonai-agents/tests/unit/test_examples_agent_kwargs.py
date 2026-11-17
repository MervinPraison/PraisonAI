"""Every Agent(...) call in the repo's examples/ uses keywords Agent accepts (D-06).

Keywords outside the signature are tried on a real Agent: removed parameters
raise ``TypeError: unexpected keyword``, deprecated ones still construct.
"""

import ast
import inspect
import warnings
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[4] / "examples"


def _agent_keywords():
    found = {}
    for path in sorted(EXAMPLES.rglob("*.py")):
        src = path.read_text(errors="ignore")
        if "praisonaiagents" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "Agent":
                for kw in node.keywords:
                    if kw.arg:
                        found.setdefault(kw.arg, []).append(f"{path.relative_to(EXAMPLES)}:{node.lineno}")
    return found


@pytest.mark.skipif(not EXAMPLES.is_dir(), reason="examples/ not present (installed package)")
def test_examples_pass_no_removed_agent_parameters(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    from praisonaiagents import Agent

    params = set(inspect.signature(Agent.__init__).parameters)
    rejected = {}
    for name, sites in _agent_keywords().items():
        if name in params:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                Agent(name="probe", **{name: None})
            except TypeError as exc:
                if "unexpected keyword" in str(exc):
                    rejected[name] = sites
            except Exception:
                pass  # accepted, but None is not a valid value: not a removed name
    assert rejected == {}, f"examples pass removed Agent parameters: {rejected}"

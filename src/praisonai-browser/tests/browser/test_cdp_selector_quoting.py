"""A model-chosen CSS selector stays one JavaScript string in Runtime.evaluate.

Every expression built from a caller or model value goes through
``cdp_utils.js_string``. The guard scans the CDP modules so a new
interpolation must use it too.
"""
import ast
import asyncio
import json
from pathlib import Path

import pytest

from praisonai_browser import cdp_agent, cdp_utils
from praisonai_browser.cdp_agent import CDPBrowserAgent

HOSTILE = [
    "x');globalThis.PWNED='INJECTED';('",
    'x");globalThis.PWNED="INJECTED";("',
    "x\\');globalThis.PWNED=1;//",
    "x globalThis.PWNED=1",
]


def _agent(sent):
    agent = CDPBrowserAgent.__new__(CDPBrowserAgent)
    agent.debug = False

    async def record(method, params=None):
        sent.append((method, params or {}))
        return {"result": {"value": None}}

    agent._send = record
    return agent


def _selector_arg(expression):
    """The JSON string literal right after ``querySelector(``, and the rest."""
    start = expression.index("querySelector(") + len("querySelector(")
    value, end = json.JSONDecoder().raw_decode(expression, start)
    assert expression[end] == ")"
    return value, expression[:start] + expression[end:]


@pytest.mark.parametrize("action", ["click", "type", "clear_input"])
@pytest.mark.parametrize("selector", HOSTILE)
def test_selector_is_one_string_literal(action, selector):
    sent = []
    asyncio.run(_agent(sent)._execute_action({"action": action, "selector": selector, "value": "v"}))
    exprs = [p["expression"] for m, p in sent if m == "Runtime.evaluate"]
    assert exprs, "no expression sent"
    for expr in exprs:
        value, rest = _selector_arg(expr)
        assert value == selector  # one string literal holding the whole selector
        assert "PWNED" not in rest


def test_wait_for_element_quotes_selector(monkeypatch):
    seen = []

    async def fake_execute_js(page_id, code, port=9222, **kw):
        seen.append(code)
        return True

    monkeypatch.setattr(cdp_utils, "execute_js", fake_execute_js)
    assert asyncio.run(cdp_utils.wait_for_element("p", HOSTILE[0], timeout=1))
    assert seen == ["!!document.querySelector(" + json.dumps(HOSTILE[0]) + ")"]


def test_ordinary_selector_unchanged_in_meaning():
    assert cdp_utils.js_string("input[name='q']") == "\"input[name='q']\""


MODULES = [Path(cdp_agent.__file__), Path(cdp_utils.__file__)]


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_guard_js_expressions_only_interpolate_quoted_values(path):
    """Every f-string that builds JavaScript calling the DOM interpolates only js_string(...)."""
    tree = ast.parse(path.read_text())
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        text = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
        if "document." not in text:
            continue
        for part in node.values:
            if isinstance(part, ast.FormattedValue):
                checked += 1
                ok = isinstance(part.value, ast.Call) and getattr(part.value.func, "id", None) == "js_string"
                assert ok, f"{path.name}:{node.lineno} interpolates {ast.unparse(part.value)}"
    assert checked, "no JS expression found; update MODULES"

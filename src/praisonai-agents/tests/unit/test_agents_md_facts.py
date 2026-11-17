"""X-10 / X-15 / D-17: the core AGENTS.md states facts the code agrees with.

Coding agents read this file first and copy from it. It listed
``openai>=2.0.0`` (pyproject requires ``>=1.68.2``; requirements.txt said
``>=1.30.0``) and an example ``MemoryConfig(provider=..., use_long_term=...)``
that raises ``TypeError``.
"""

import ast
import os
import re

from praisonaiagents import HooksConfig, MemoryConfig

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(name):
    with open(os.path.join(PKG_ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_openai_floor_matches_pyproject_everywhere():
    floor = re.search(r'"openai>=([\d.]+)"', _read("pyproject.toml")).group(1)
    assert re.search(r'"openai>=([\d.]+)"', _read("AGENTS.md")).group(1) == floor
    assert re.search(r"^openai>=([\d.]+)", _read("requirements.txt"), re.M).group(1) == floor


def _value(node, names):
    # Only literals and known placeholder names: never evaluate file text.
    if isinstance(node, ast.Name):
        return names[node.id]
    if isinstance(node, ast.List):
        return [_value(e, names) for e in node.elts]
    return ast.literal_eval(node)


def test_config_examples_construct():
    classes = {"MemoryConfig": MemoryConfig, "HooksConfig": HooksConfig}
    placeholders = {"my_tool_logger": print, "my_validator": print, "my_hook": print}
    calls = re.findall(r"\b((?:MemoryConfig|HooksConfig)\([^()]*\))", _read("AGENTS.md"))
    assert calls
    for call in calls:
        node = ast.parse(call, mode="eval").body
        cls = classes[node.func.id]
        args = [_value(a, placeholders) for a in node.args]
        kwargs = {k.arg: _value(k.value, placeholders) for k in node.keywords}
        cls(*args, **kwargs)

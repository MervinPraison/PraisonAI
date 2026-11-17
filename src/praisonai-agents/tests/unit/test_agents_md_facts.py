"""X-10 / X-15 / D-17: the core AGENTS.md states facts the code agrees with.

Coding agents read this file first and copy from it. It listed
``openai>=2.0.0`` (pyproject requires ``>=1.68.2``; requirements.txt said
``>=1.30.0``) and an example ``MemoryConfig(provider=..., use_long_term=...)``
that raises ``TypeError``.
"""

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


def test_config_examples_construct():
    placeholders = {"my_tool_logger": print, "my_validator": print, "my_hook": print}
    calls = re.findall(r"\b((?:MemoryConfig|HooksConfig)\([^()]*\))", _read("AGENTS.md"))
    assert calls
    for call in calls:
        eval(call, {"MemoryConfig": MemoryConfig, "HooksConfig": HooksConfig, **placeholders})

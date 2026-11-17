"""G-30 (usage): one copy of a helper llm.py, openai_client.py and tool_execution.py shared (G-30)."""

from pathlib import Path
from types import SimpleNamespace

import praisonaiagents
from praisonaiagents.llm import _helpers

PKG = Path(praisonaiagents.__file__).parent


def test_usage_lookups_read_dicts_and_objects():
    as_dict = {"prompt_tokens": 7, "prompt_tokens_details": {"cached_tokens": 3}}
    as_obj = SimpleNamespace(input_tokens=None, prompt_tokens=7,
                             prompt_tokens_details=SimpleNamespace(cached_tokens=3))
    for usage in (as_dict, as_obj):
        assert _helpers.usage_value(usage, "input_tokens", "prompt_tokens") == 7
        assert _helpers.usage_detail(usage, ("input_tokens_details", "prompt_tokens_details"), "cached_tokens") == 3
        assert _helpers.usage_detail(usage, ("completion_tokens_details",), "reasoning_tokens") == 0
    for rel in ("llm/llm.py", "llm/openai_client.py"):
        src = (PKG / rel).read_text()
        # Local wrappers may stay; the duplicated loop body must not.
        assert "for detail_name in detail_names" not in src, rel

"""G-30 (steering): one copy of a helper llm.py, openai_client.py and tool_execution.py shared (G-30)."""

from pathlib import Path
from types import SimpleNamespace

import praisonaiagents
from praisonaiagents.llm import _helpers

PKG = Path(praisonaiagents.__file__).parent


def test_steering_notes_are_injected_by_the_shared_helper():
    msgs = []
    _helpers.inject_steering(msgs, lambda: ["go left", "", None, "stop"])
    assert msgs == [{"role": "user", "content": "[steering] go left"},
                    {"role": "user", "content": "[steering] stop"}]
    _helpers.inject_steering(msgs, None)  # no drain: no-op
    def broken():
        raise RuntimeError("drain down")
    _helpers.inject_steering(msgs, broken)  # a failing drain is ignored
    assert len(msgs) == 2
    for rel in ("llm/llm.py", "llm/openai_client.py"):
        assert "[steering]" not in (PKG / rel).read_text(), rel

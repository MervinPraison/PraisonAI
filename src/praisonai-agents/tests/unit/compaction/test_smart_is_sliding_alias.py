"""N-5: CompactionStrategy.SMART is an alias of SLIDING, and says so.

``_smart_compact`` has always returned ``_sliding_window``; the docstrings
described "importance-based" compaction that does not exist. The alias is
kept (no removal) and documented; this pins it, so a real SMART strategy must
update the docs and this test together.
"""

from praisonaiagents.compaction.compactor import ContextCompactor
from praisonaiagents.compaction.strategy import CompactionStrategy


def _messages():
    msgs = [{"role": "system", "content": "You are helpful."}]
    for i in range(40):
        msgs.append({"role": "user", "content": f"question {i} " + "word " * 60})
        msgs.append({"role": "assistant", "content": f"answer {i} " + "word " * 60})
    return msgs


def _compact(strategy):
    compactor = ContextCompactor(max_tokens=1500, strategy=strategy, preserve_recent=4)
    compacted, _result = compactor.compact(_messages())
    return compacted


def test_smart_compacts_exactly_like_sliding():
    assert _compact(CompactionStrategy.SMART) == _compact(CompactionStrategy.SLIDING)


def test_smart_is_documented_as_an_alias_of_sliding():
    from praisonaiagents.compaction import compactor, strategy

    assert "alias" in compactor.ContextCompactor._smart_compact.__doc__.lower()
    assert "alias of sliding" in open(strategy.__file__, encoding="utf-8").read().lower()

"""Regression tests for issue #5920.

* A rejected *input* returns the same fixed blocked string as a rejected
  output (never ``None``, never the validator's free-text reason).
* Concurrent ``PolicyConfig.save_learned_rule`` calls keep every rule.
"""
import asyncio
import threading

from praisonaiagents import Agent
from praisonaiagents.policy.config import PolicyConfig

SECRET_REASON = "contains secret: hunter2"


class RejectInput:
    def validate_input(self, content, **kwargs):
        return False, SECRET_REASON

    def validate_output(self, content, **kwargs):
        return True, content


def _agent():
    return Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=RejectInput())


def _assert_blocked(agent, result):
    assert isinstance(result, str)
    assert result == agent._guardrail_blocked_message()
    assert "hunter2" not in result


def test_chat_input_block_returns_fixed_string():
    a = _agent()
    _assert_blocked(a, a.chat("hi"))


def test_start_input_block_returns_fixed_string():
    a = _agent()
    _assert_blocked(a, a.start("hi"))


def test_achat_input_block_returns_fixed_string():
    a = _agent()
    _assert_blocked(a, asyncio.run(a.achat("hi")))


def test_stream_input_block_does_not_leak_reason():
    a = _agent()
    chunks = list(a.start("hi", stream=True))
    _assert_blocked(a, "".join(chunks))


def test_input_block_reason_exposed_via_last_guardrail_error():
    a = _agent()
    _assert_blocked(a, a.chat("hi"))
    assert a.last_guardrail_error == SECRET_REASON


def test_concurrent_learned_rules_are_not_lost(tmp_path):
    rules_file = str(tmp_path / "rules" / "default.rules")
    threads, per_thread = 8, 25

    def worker(i):
        cfg = PolicyConfig(rules_file=rules_file)
        for j in range(per_thread):
            assert cfg.save_learned_rule(f"tool_{i}_{j}")

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    rules = PolicyConfig(rules_file=rules_file).load_learned_rules()
    assert len(rules) == threads * per_thread


def test_learned_rule_is_deduplicated(tmp_path):
    cfg = PolicyConfig(rules_file=str(tmp_path / "r.rules"))
    assert cfg.save_learned_rule("tool:ls", "allow")
    assert cfg.save_learned_rule("tool:ls", "deny")
    assert cfg.load_learned_rules() == [{"resource": "tool:ls", "action": "allow"}]

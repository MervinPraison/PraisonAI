"""Learned rules reuse the shared locked JSON read-modify-write boundary."""
from concurrent.futures import ThreadPoolExecutor

from praisonaiagents.policy.config import PolicyConfig
from praisonaiagents.utils import atomic_io


def test_save_learned_rule_uses_locked_current_data(tmp_path, monkeypatch):
    """The mutation must merge the lock-protected snapshot, not a stale read."""
    path = tmp_path / "rules.json"
    cfg = PolicyConfig(rules_file=str(path))
    current = {"rules": [{"resource": "tool:existing", "action": "deny"}]}
    calls = []

    def locked_update(target, mutate, default=dict, **kwargs):
        calls.append(target)
        assert default() == {"rules": []}
        result = mutate(current)
        atomic_io.atomic_write_json(target, current, **kwargs)
        return result

    monkeypatch.setattr(atomic_io, "update_json", locked_update)
    assert cfg.save_learned_rule("tool:new") is True
    assert calls == [str(path)]
    assert cfg.load_learned_rules() == [
        {"resource": "tool:existing", "action": "deny"},
        {"resource": "tool:new", "action": "allow"},
    ]


def test_independent_configs_preserve_concurrent_rules(tmp_path):
    """All distinct public saves survive concurrent independent config writers."""
    path = str(tmp_path / "nested" / "rules.json")

    def save(i):
        return PolicyConfig(rules_file=path).save_learned_rule(f"tool:{i}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(save, range(80)))
    rules = PolicyConfig(rules_file=path).load_learned_rules()
    assert len(rules) == 80
    assert {rule["resource"] for rule in rules} == {f"tool:{i}" for i in range(80)}


def test_save_learned_rule_preserves_duplicate_action(tmp_path):
    """A repeated resource keeps its established action and appears once."""
    cfg = PolicyConfig(rules_file=str(tmp_path / "rules.json"))
    assert cfg.save_learned_rule("tool:one", "deny")
    assert cfg.save_learned_rule("tool:one", "allow")
    assert cfg.load_learned_rules() == [{"resource": "tool:one", "action": "deny"}]

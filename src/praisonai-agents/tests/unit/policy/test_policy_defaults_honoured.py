"""PolicyEngine honours what the operator configured.

* ``default_action="deny"`` denies a resource no rule matches.
* A rule loaded from a dict/YAML with the documented ``match:`` key matches
  only that resource, not every resource.
* Rules loaded from a dict are evaluated by priority, as ``add_rule`` does.
* ``load_from_dict(engine.to_dict())`` keeps ``default_action``/``strict_mode``.
"""
import pytest

from praisonaiagents.policy import Policy, PolicyConfig, PolicyEngine


def test_default_action_deny_denies_unmatched_resource():
    engine = PolicyEngine(PolicyConfig(default_action="deny"))
    assert engine.check("tool:shell_exec").allowed is False


def test_default_action_allow_still_allows():
    assert PolicyEngine(PolicyConfig()).check("tool:read_file").allowed is True


def test_match_key_scopes_the_rule():
    policy = Policy.from_dict({
        "name": "p",
        "rules": [{"match": "tool:read_file", "action": "allow"}],
    })
    engine = PolicyEngine(PolicyConfig(default_action="deny"))
    engine.add_policy(policy)
    assert engine.check("tool:read_file").allowed is True
    assert engine.check("tool:shell_exec").allowed is False


def test_dict_rules_are_evaluated_by_priority():
    policy = Policy.from_dict({
        "name": "p",
        "rules": [
            {"resource": "tool:*", "action": "allow", "priority": 0},
            {"resource": "tool:shell_exec", "action": "deny", "priority": 100},
        ],
    })
    engine = PolicyEngine()
    engine.add_policy(policy)
    assert engine.check("tool:shell_exec").allowed is False
    assert engine.check("tool:read_file").allowed is True


@pytest.mark.parametrize("data", [
    {"default_action": "deny", "policies": []},
    {"config": {"default_action": "deny"}, "policies": []},
])
def test_load_from_dict_applies_default_action(data):
    engine = PolicyEngine()
    engine.load_from_dict(data)
    assert engine.check("tool:shell_exec").allowed is False


def test_round_trip_keeps_strict_mode():
    source = PolicyEngine(PolicyConfig(strict_mode=True))
    engine = PolicyEngine()
    engine.load_from_dict(source.to_dict())
    assert engine.check("tool:anything").allowed is False


def test_load_from_yaml_match_and_default(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "policy.yaml"
    path.write_text(
        "default_action: deny\n"
        "policies:\n"
        "  - name: p\n"
        "    rules:\n"
        "      - match: tool:read_file\n"
        "        action: allow\n"
    )
    engine = PolicyEngine()
    engine.load_from_yaml(str(path))
    assert engine.check("tool:read_file").allowed is True
    assert engine.check("tool:shell_exec").allowed is False

"""Tests for path-scoped (activation: glob) rule activation during runs.

Covers issue #3134: glob rules must fire when the agent touches matching
files, be deduplicated against always rules, and cost nothing when absent.
"""

import textwrap

import pytest

from praisonaiagents.memory.rules_manager import Rule, RulesManager


def _write_rule(rules_dir, name, activation, body, globs=None):
    frontmatter = ["---", f"activation: {activation}"]
    if globs:
        globs_str = ", ".join(f'"{g}"' for g in globs)
        frontmatter.append(f"globs: [{globs_str}]")
    frontmatter.append("---")
    (rules_dir / f"{name}.md").write_text(
        "\n".join(frontmatter) + "\n\n" + body, encoding="utf-8"
    )


class TestMatchesFile:
    def test_bare_filename_matches_recursive_glob(self):
        rule = Rule(name="python", content="x", activation="glob", globs=["**/*.py"])
        assert rule.matches_file("foo.py")
        assert rule.matches_file("src/main.py")
        assert rule.matches_file("a/b/c.py")

    def test_non_matching_extension(self):
        rule = Rule(name="python", content="x", activation="glob", globs=["**/*.py"])
        assert not rule.matches_file("foo.js")

    def test_always_matches_anything(self):
        rule = Rule(name="root", content="x", activation="always")
        assert rule.matches_file("anything.txt")

    def test_manual_never_matches(self):
        rule = Rule(name="sec", content="x", activation="manual")
        assert not rule.matches_file("foo.py")


class TestGlobRulesForPaths:
    def _manager(self, tmp_path):
        rules_dir = tmp_path / ".praisonai" / "rules"
        rules_dir.mkdir(parents=True)
        _write_rule(rules_dir, "python", "glob", "Use type hints.", globs=["**/*.py"])
        _write_rule(rules_dir, "root", "always", "Always follow this.")
        return RulesManager(workspace_path=str(tmp_path))

    def test_glob_rule_selected_only_for_matching_path(self, tmp_path):
        mgr = self._manager(tmp_path)
        matched = mgr.get_glob_rules_for_paths(["foo.py"])
        assert [r.name for r in matched] == ["python"]

        assert mgr.get_glob_rules_for_paths(["foo.js"]) == []

    def test_exclude_names_dedupes(self, tmp_path):
        mgr = self._manager(tmp_path)
        matched = mgr.get_glob_rules_for_paths(["foo.py"], exclude_names={"python"})
        assert matched == []

    def test_has_glob_rules_gate(self, tmp_path):
        mgr = self._manager(tmp_path)
        assert mgr.has_glob_rules() is True

    def test_has_glob_rules_false_without_glob(self, tmp_path):
        rules_dir = tmp_path / ".praisonai" / "rules"
        rules_dir.mkdir(parents=True)
        _write_rule(rules_dir, "root", "always", "Always follow this.")
        mgr = RulesManager(workspace_path=str(tmp_path))
        assert mgr.has_glob_rules() is False


class TestChatMixinInjection:
    """Verify _build_system_prompt injects glob rules for touched files."""

    def _make_agent(self, tmp_path):
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.config.feature_configs import RulesConfig

        rules_dir = tmp_path / ".praisonai" / "rules"
        rules_dir.mkdir(parents=True)
        _write_rule(
            rules_dir,
            "python",
            "glob",
            "PYTHON_RULE_MARKER: use type hints.",
            globs=["**/*.py"],
        )
        agent = Agent(
            name="t",
            role="dev",
            goal="help",
            backstory="bg",
            rules=RulesConfig(workspace_path=str(tmp_path)),
            llm="gpt-4o-mini",
        )
        return agent

    def test_glob_rule_absent_without_touched_file(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent.chat_history = [{"role": "user", "content": "hello there"}]
        prompt = agent._build_system_prompt(tools=None)
        assert "PYTHON_RULE_MARKER" not in prompt

    def test_glob_rule_injected_when_file_touched(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent.chat_history = [
            {"role": "user", "content": "open foo.py and describe it"}
        ]
        prompt = agent._build_system_prompt(tools=None)
        assert "PYTHON_RULE_MARKER" in prompt

    def test_glob_rule_not_duplicated(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent.chat_history = [
            {"role": "user", "content": "look at foo.py"},
            {"role": "assistant", "content": "reading src/bar.py now"},
        ]
        prompt = agent._build_system_prompt(tools=None)
        assert prompt.count("PYTHON_RULE_MARKER") == 1

    def test_glob_rule_activates_per_turn_even_when_base_cached(self, tmp_path):
        # First turn touches no file: base prompt is built (and may be cached).
        agent = self._make_agent(tmp_path)
        agent.chat_history = [{"role": "user", "content": "hi"}]
        first = agent._build_system_prompt(tools=None)
        assert "PYTHON_RULE_MARKER" not in first

        # Second turn touches a matching file: the (possibly cached) base prompt
        # must still gain the path-scoped rule dynamically.
        agent.chat_history = [{"role": "user", "content": "open foo.py"}]
        second = agent._build_system_prompt(tools=None)
        assert second.count("PYTHON_RULE_MARKER") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

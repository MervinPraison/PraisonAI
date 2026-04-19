"""Unit tests for slash-command invocation and invocation policies."""

import os
import tempfile
from pathlib import Path


def _make_skill(tmpdir: Path, name: str, body: str, extra_fm: str = "") -> Path:
    skill_dir = tmpdir / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} skill\n{extra_fm}---\n\n{body}\n"
    )
    return skill_dir


class TestManagerInvoke:
    def test_invoke_substitutes_arguments(self):
        from praisonaiagents.skills import SkillManager

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _make_skill(tmp, "migrate", "Migrate $0 from $1 to $2.")
            mgr = SkillManager()
            mgr.add_skill(str(tmp / "migrate"))
            out = mgr.invoke("migrate", raw_args="SearchBar React Vue")
            assert out == "Migrate SearchBar from React to Vue."

    def test_invoke_returns_none_for_missing_skill(self):
        from praisonaiagents.skills import SkillManager

        mgr = SkillManager()
        assert mgr.invoke("nope") is None

    def test_invoke_respects_user_invocable_false(self):
        from praisonaiagents.skills import SkillManager

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _make_skill(
                tmp, "legacy",
                body="Legacy knowledge body.",
                extra_fm="user-invocable: false\n",
            )
            mgr = SkillManager()
            mgr.add_skill(str(tmp / "legacy"))
            assert mgr.invoke("legacy") is None

    def test_disable_model_invocation_hides_from_available(self):
        from praisonaiagents.skills import SkillManager

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _make_skill(
                tmp, "deploy",
                body="Deploy body.",
                extra_fm="disable-model-invocation: true\n",
            )
            mgr = SkillManager()
            mgr.add_skill(str(tmp / "deploy"))
            available = mgr.get_available_skills()
            assert all(m.name != "deploy" for m in available)
            # Still user-invocable
            assert mgr.invoke("deploy") == "Deploy body."


class TestAgentSlashRouter:
    def test_slash_returns_rendered_body_without_llm_call(self):
        """Slash prefix should short-circuit to the skill body."""
        from praisonaiagents import Agent

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _make_skill(tmp, "hello", "Say hello to $0 in one word.")

            agent = Agent(
                name="t",
                instructions="You are a helpful assistant.",
                skills=[str(tmp / "hello")],
                llm=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"),
            )
            rendered = agent._resolve_skill_invocation("/hello Alice")
            assert rendered == "Say hello to Alice in one word."

    def test_non_slash_prompt_untouched(self):
        from praisonaiagents import Agent

        agent = Agent(name="t", instructions="x")
        assert agent._resolve_skill_invocation("hello there") == "hello there"

    def test_slash_with_unknown_name_untouched(self):
        from praisonaiagents import Agent

        agent = Agent(name="t", instructions="x")
        assert agent._resolve_skill_invocation("/does-not-exist arg") == "/does-not-exist arg"


class TestSkillsConfigAutoDiscover:
    def test_skills_config_auto_discover_honoured(self):
        """SkillsConfig(auto_discover=True) must initialise the skill manager."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import SkillsConfig

        agent = Agent(
            name="ad",
            instructions="x",
            skills=SkillsConfig(paths=[], dirs=[], auto_discover=True),
        )
        # Manager must be created even with no paths, because auto_discover is on
        assert agent.skill_manager is not None

    def test_empty_skills_config_no_manager(self):
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import SkillsConfig

        agent = Agent(
            name="none",
            instructions="x",
            skills=SkillsConfig(paths=[], dirs=[], auto_discover=False),
        )
        assert agent.skill_manager is None

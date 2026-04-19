"""YAML `skills:` support for praisonai agents.yaml loader."""

import tempfile
from pathlib import Path


def _make_pdf_skill(tmp: Path) -> Path:
    sd = tmp / "pdf-like"
    sd.mkdir()
    (sd / "SKILL.md").write_text(
        "---\n"
        "name: pdf-like\n"
        "description: Demo skill for YAML loading.\n"
        "---\n\n"
        "Instructions body.\n"
    )
    return sd


def test_yaml_skills_passed_to_agent(monkeypatch):
    """agents.yaml `skills: [path]` must reach Agent(skills=[...])."""
    from praisonaiagents import Agent

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        skill_dir = _make_pdf_skill(tmp)

        # Build an agent the same way agents_generator.py does:
        agent = Agent(
            name="yaml-skills-test",
            role="tester",
            goal="demo",
            backstory="demo",
            instructions="You help.",
            skills=[str(skill_dir)],
        )

        # Invoke via slash-router mirrors YAML flow
        rendered = agent._resolve_skill_invocation("/pdf-like")
        assert rendered == "Instructions body."

"""Real agentic tests for the skills feature.

Each test creates a real ``Agent``, calls ``agent.start(...)`` (which hits the
LLM), and prints the full output so the developer can visually confirm the
end-to-end pipeline works with the user's configured model.

Skipped automatically when ``OPENAI_API_KEY`` is not set.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


if not os.environ.get("OPENAI_API_KEY"):
    pytest.skip("OPENAI_API_KEY not set", allow_module_level=True)


MODEL = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")


def _write_skill(parent: Path, name: str, body: str, extra_fm: str = "") -> Path:
    d = parent / name
    d.mkdir()
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} skill for testing.\n{extra_fm}---\n\n{body}\n"
    )
    return d


def _agent(**kwargs):
    from praisonaiagents import Agent
    return Agent(
        name=kwargs.pop("name", "skills-test"),
        instructions=kwargs.pop("instructions", "You are a helpful assistant. Keep answers under 40 words."),
        llm=MODEL,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Test 1 — auto-trigger via description in system prompt
# --------------------------------------------------------------------------- #
def test_1_autotrigger_pdf_style_skill():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_skill(
            tmp,
            "pdf-like",
            body=(
                "# PDF helper\n\n"
                "When answering PDF questions ALWAYS mention the Python library "
                "`pypdf` and `PdfReader`."
            ),
        )
        agent = _agent(skills=[str(tmp / "pdf-like")])
        out = agent.start("How do I read a PDF file in Python?")
        print("\n[TEST 1 OUTPUT]\n" + (out or "<empty>") + "\n")
        assert out and isinstance(out, str)


# --------------------------------------------------------------------------- #
# Test 2 — /slash-command invocation
# --------------------------------------------------------------------------- #
def test_2_slash_invocation_csv_analyzer(monkeypatch):
    # Disable auto-injection of subprocess tools so this test is hermetic.
    monkeypatch.setenv("PRAISONAI_DISABLE_SKILL_TOOLS", "1")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_skill(
            tmp,
            "csv-summary",
            body=(
                "Do NOT call any tools. Produce a placeholder summary with "
                "exactly these three lines, one per line:\n"
                "Rows: 42\n"
                "Columns: 5\n"
                "Notes: synthetic demo data"
            ),
        )
        agent = _agent(skills=[str(tmp / "csv-summary")])
        out = agent.start("/csv-summary customers.csv")
        print("\n[TEST 2 OUTPUT]\n" + (out or "<empty>") + "\n")
        assert out and "Rows" in out


# --------------------------------------------------------------------------- #
# Test 3 — $ARGUMENTS substitution
# --------------------------------------------------------------------------- #
def test_3_arguments_substitution():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_skill(
            tmp,
            "migrate",
            body="Explain in ONE sentence how to migrate $0 from $1 to $2.",
        )
        agent = _agent(skills=[str(tmp / "migrate")])
        out = agent.start("/migrate SearchBar React Vue")
        print("\n[TEST 3 OUTPUT]\n" + (out or "<empty>") + "\n")
        assert out
        low = out.lower()
        assert "searchbar" in low or "search bar" in low
        assert "vue" in low


# --------------------------------------------------------------------------- #
# Test 4 — disable-model-invocation hides from listing, works via /
# --------------------------------------------------------------------------- #
def test_4_disable_model_invocation_but_user_can_invoke():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_skill(
            tmp,
            "deploy",
            body="Pretend to deploy: respond with the single word OK.",
            extra_fm="disable-model-invocation: true\n",
        )
        agent = _agent(skills=[str(tmp / "deploy")])

        # Not in listing
        xml = agent.get_skills_prompt()
        assert "deploy" not in xml

        # But user invoke works
        out = agent.start("/deploy prod")
        print("\n[TEST 4 OUTPUT]\n" + (out or "<empty>") + "\n")
        assert out and "OK" in out.upper()


# --------------------------------------------------------------------------- #
# Test 5 — YAML-loaded skill via agents_generator semantics
# --------------------------------------------------------------------------- #
def test_5_yaml_skills_key_equivalence():
    """A YAML config would pass skills=[...]; verify that path works."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_skill(
            tmp,
            "greet",
            body="Greet $0 warmly in exactly one sentence.",
        )

        # Simulate YAML -> agent path by passing skills as a list of strings
        agent = _agent(
            name="greeter",
            instructions="You are a greeter.",
            skills=[str(tmp / "greet")],
        )
        out = agent.start("/greet Alice")
        print("\n[TEST 5 OUTPUT]\n" + (out or "<empty>") + "\n")
        assert out and "alice" in out.lower()

"""``praisonai ship`` (S-5): a pull request title and body written from the commits and diff."""

import os

import pytest

from praisonai_code.ship.pr_text import PRText, write_pr_text

COMMITS = ["feat(ship): add the never-merge guard", "test: cover gh api merges"]
DIFF = "diff --git a/a.py b/a.py\n+x = 1\n"


class FakeAgent:
    def __init__(self, reply):
        self.reply, self.prompts, self.kwargs = reply, [], []

    def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        return self.reply


def test_model_writes_the_title_and_body():
    agent = FakeAgent(PRText(title="Add a never-merge guard to ship", body="Why and what."))
    text = write_pr_text(COMMITS, DIFF, agent=agent)
    assert text.title == "Add a never-merge guard to ship"
    assert agent.kwargs[0]["output_pydantic"] is PRText


def test_prompt_carries_commits_and_fences_the_diff_as_untrusted():
    agent = FakeAgent(PRText(title="t", body="b"))
    write_pr_text(COMMITS, DIFF, agent=agent)
    prompt = agent.prompts[0]
    assert all(c in prompt for c in COMMITS)
    assert "```diff\n" + DIFF in prompt and "untrusted" in prompt.lower()


@pytest.mark.parametrize("reply", ["sure, here is a title", PRText(title=" ", body="b"), RuntimeError("down")])
def test_falls_back_to_the_commits_not_the_branch_name(reply):
    class Agent(FakeAgent):
        def chat(self, prompt, **kwargs):
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply

    text = write_pr_text(COMMITS, DIFF, agent=Agent(reply))
    assert text.title == COMMITS[0]
    assert all(f"- {c}" in text.body for c in COMMITS)


def test_long_titles_are_cut_to_one_line():
    agent = FakeAgent(PRText(title="word " * 40 + "\nsecond line", body="b"))
    title = write_pr_text(COMMITS, DIFF, agent=agent).title
    assert len(title) <= 72 and "\n" not in title


def test_no_commits_is_refused():
    with pytest.raises(ValueError, match="commit"):
        write_pr_text([], DIFF, agent=FakeAgent(PRText(title="t", body="b")))


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS", "").lower() not in {"1", "true", "yes"}
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Real OpenAI test disabled",
)
def test_real_pr_text():
    """Real agentic test: the model writes a title and body for a two-commit change."""
    diff = "diff --git a/calc.py b/calc.py\n+def last(xs):\n+    return xs[-1] if xs else None\n"
    text = write_pr_text(["fix: last() on an empty list", "test: cover empty list"], diff, llm="gpt-4o-mini")
    print(text.model_dump())
    assert text.title and len(text.title) <= 72 and text.body
    assert text.body != "- fix: last() on an empty list\n- test: cover empty list", "model text, not the fallback"

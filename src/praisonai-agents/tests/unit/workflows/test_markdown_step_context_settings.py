"""Markdown workflow steps honour context_from / retain_full_context (F-20).

The parser passed these to Task as context=TaskContextConfig(...), which Task
stored as-is in .context (a list of tasks elsewhere): the settings were
ignored by the engine and Task.to_dict() raised TypeError.
"""

from praisonaiagents import Task
from praisonaiagents.workflows.workflow_configs import TaskContextConfig
from praisonaiagents.workflows.workflows import WorkflowManager

BODY = """
## Step 1: research
Find facts about the topic.

## Step 2: outline
Outline the article.

## Step 3: write
Write the article.
context_from: [research]

## Step 4: review
Review everything so far.
retain_full_context: true
"""


def _steps(tmp_path):
    return {s.name: s for s in WorkflowManager(workspace_path=str(tmp_path))._parse_steps(BODY)}


def test_context_from_reaches_the_engine(tmp_path):
    steps = _steps(tmp_path)
    write = steps["write"]
    assert write.context_from == ["research"]
    results = [{"step": "research", "output": "RESEARCH-OUT", "status": "success"},
               {"step": "outline", "output": "OUTLINE-OUT", "status": "success"}]
    ctx = WorkflowManager(workspace_path=str(tmp_path))._build_step_context(write, 2, results, {})
    assert "RESEARCH-OUT" in ctx and "OUTLINE-OUT" not in ctx


def test_retain_full_context_reaches_the_engine(tmp_path):
    review = _steps(tmp_path)["review"]
    assert review.retain_full_context is True


def test_task_accepts_a_context_config():
    t = Task(description="d", context=TaskContextConfig(from_steps=["a"], retain_full=True))
    assert t.context == [] and t.context_from == ["a"] and t.retain_full_context is True
    t.to_dict()  # raised TypeError: 'TaskContextConfig' object is not iterable


def test_plain_task_context_list_is_unchanged():
    dep = Task(description="first")
    t = Task(description="second", context=[dep])
    assert t.context == [dep] and getattr(t, "context_from", None) is None

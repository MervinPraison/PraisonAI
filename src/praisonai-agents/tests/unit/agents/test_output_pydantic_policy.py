"""Unit tests for structured-output fail-closed policy in agents.py.

Covers the fix for the silent `output_pydantic` parse failure: when a Task
requests structured output but the agent returns freeform prose, the task must
NOT be treated as a success (regression: TaskResult.success stayed True with
pydantic=None). No live LLM is required.
"""
from types import SimpleNamespace

from pydantic import BaseModel

from praisonaiagents.agents.agents import _process_task_result, PraisonAIAgents
from praisonaiagents.agents.protocols import ExecutionContext


class Fact(BaseModel):
    title: str
    detail: str


class _StubAgentsInstance:
    def clean_json_output(self, output: str) -> str:
        return output.strip()


def _make_context(task):
    return ExecutionContext(
        task_id=0,
        task=task,
        executor_agent=SimpleNamespace(display_name="stub"),
        tools=[],
        task_description="desc",
        context_text="",
        task_prompt="prompt",
        llm=None,
    )


def _make_task(**kwargs):
    defaults = {
        "description": "desc",
        "memory": None,
        "output_json": None,
        "output_pydantic": None,
        "result": None,
        "status": "in progress",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_freeform_prose_not_success_when_output_pydantic_set():
    task = _make_task(output_pydantic=Fact)
    ctx = _make_context(task)
    result = _process_task_result(_StubAgentsInstance(), ctx, "The ocean covers 71% of Earth.")

    assert result.success is False
    assert result.task_output.pydantic is None
    assert "Fact" in (result.error or "")
    # Raw is preserved for debugging.
    assert "ocean" in result.task_output.raw


def test_valid_json_sets_pydantic_instance():
    task = _make_task(output_pydantic=Fact)
    ctx = _make_context(task)
    result = _process_task_result(
        _StubAgentsInstance(), ctx, '{"title": "Depth", "detail": "Challenger Deep"}'
    )

    assert result.success is True
    assert isinstance(result.task_output.pydantic, Fact)
    assert result.task_output.pydantic.title == "Depth"
    assert result.task_output.output_format == "Pydantic"


def test_validation_error_missing_field_is_not_success():
    task = _make_task(output_pydantic=Fact)
    ctx = _make_context(task)
    # Valid JSON but wrong shape (missing 'detail').
    result = _process_task_result(_StubAgentsInstance(), ctx, '{"title": "only title"}')

    assert result.success is False
    assert result.task_output.pydantic is None


def test_output_json_prose_is_not_success():
    task = _make_task(output_json=True)
    ctx = _make_context(task)
    result = _process_task_result(_StubAgentsInstance(), ctx, "not json at all")

    assert result.success is False
    assert result.task_output.json_dict is None


def test_empty_json_object_is_success():
    task = _make_task(output_json=True)
    ctx = _make_context(task)
    result = _process_task_result(_StubAgentsInstance(), ctx, "{}")

    assert result.success is True
    assert result.task_output.json_dict == {}


def test_failed_results_preserve_parse_error_detail():
    # Pydantic path surfaces the underlying validation error.
    task = _make_task(output_pydantic=Fact)
    ctx = _make_context(task)
    result = _process_task_result(_StubAgentsInstance(), ctx, '{"title": "only title"}')
    assert result.success is False
    assert "detail" in (result.error or "").lower()

    # JSON path surfaces the underlying decode error.
    task_json = _make_task(output_json=True)
    ctx_json = _make_context(task_json)
    result_json = _process_task_result(_StubAgentsInstance(), ctx_json, "not json")
    assert result_json.success is False
    assert "(" in (result_json.error or "")


def test_freeform_prose_success_when_no_structured_output():
    task = _make_task()
    ctx = _make_context(task)
    result = _process_task_result(_StubAgentsInstance(), ctx, "just prose")

    assert result.success is True


def test_completion_checker_fails_closed_for_unparsed_pydantic():
    checker = PraisonAIAgents.default_completion_checker
    # pydantic requested but not produced -> not complete
    task = _make_task(output_pydantic=Fact, result=SimpleNamespace(pydantic=None, json_dict=None))
    assert checker(None, task, "some prose") is False

    # pydantic produced -> complete
    task_ok = _make_task(
        output_pydantic=Fact,
        result=SimpleNamespace(pydantic=Fact(title="a", detail="b"), json_dict=None),
    )
    assert checker(None, task_ok, "irrelevant") is True

    # no structured output -> non-empty prose is complete
    task_plain = _make_task()
    assert checker(None, task_plain, "prose") is True
    assert checker(None, task_plain, "   ") is False


def test_completion_checker_accepts_falsey_json():
    checker = PraisonAIAgents.default_completion_checker
    for value in ({}, [], False, 0):
        task = _make_task(
            output_json=True,
            result=SimpleNamespace(pydantic=None, json_dict=value),
        )
        assert checker(None, task, "irrelevant") is True

    # Missing structured output (json_dict is None) -> not complete.
    task_missing = _make_task(
        output_json=True, result=SimpleNamespace(pydantic=None, json_dict=None)
    )
    assert checker(None, task_missing, "prose") is False

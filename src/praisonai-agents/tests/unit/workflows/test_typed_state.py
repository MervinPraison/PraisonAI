"""A workflow's state can be typed.

Flow state was an untyped Dict[str, Any]. A typo -- ctx.variables["reserach_results"]
-- was found at runtime, if at all, and nothing told you what fields a workflow's
state carried without reading every step.
"""
import dataclasses
import pytest

from praisonaiagents.workflows.state import (
    WorkflowStateError,
    build_state,
    state_field_names,
    validate_variables,
)
from praisonaiagents.workflows.workflows import AgentFlow

pydantic = pytest.importorskip("pydantic")


class ReviewState(pydantic.BaseModel):
    draft: str = ""
    score: int = 0


@dataclasses.dataclass
class PlainState:
    draft: str = ""
    score: int = 0


class TestTypedAccess:
    def test_state_exposes_declared_fields(self):
        flow = AgentFlow(steps=[], state_model=ReviewState,
                         variables={"draft": "hi", "score": 7})
        assert flow.state.draft == "hi"
        assert flow.state.score == 7

    def test_a_dataclass_works_too(self):
        """Pydantic must not become a requirement for running a workflow."""
        flow = AgentFlow(steps=[], state_model=PlainState, variables={"draft": "hi"})
        assert flow.state.draft == "hi"

    def test_control_an_untyped_flow_is_unchanged(self):
        """Without a model, variables stay the untyped dict they always were."""
        flow = AgentFlow(steps=[], variables={"anything": 1})
        assert flow.state is None
        assert flow.variables == {"anything": 1}

    def test_state_is_none_not_an_empty_object_when_untyped(self):
        """Callers must be able to tell 'untyped' from 'typed and empty'."""
        assert AgentFlow(steps=[]).state is None


class TestMistakesAreCaughtAtBuildTime:
    def test_a_misspelled_variable_is_refused(self):
        with pytest.raises(WorkflowStateError, match="reserach_results"):
            AgentFlow(steps=[], state_model=ReviewState,
                      variables={"reserach_results": 1})

    def test_the_error_lists_the_declared_fields(self):
        """So the fix is visible without opening the model."""
        with pytest.raises(WorkflowStateError, match="draft"):
            AgentFlow(steps=[], state_model=ReviewState, variables={"nope": 1})

    def test_a_wrongly_typed_variable_is_refused(self):
        with pytest.raises(WorkflowStateError, match="do not fit state model"):
            AgentFlow(steps=[], state_model=ReviewState, variables={"score": "not an int"})

    def test_control_correct_variables_build_cleanly(self):
        AgentFlow(steps=[], state_model=ReviewState, variables={"score": 3})

    def test_a_model_with_no_fields_is_refused(self):
        class Empty:
            pass
        with pytest.raises(WorkflowStateError, match="declares no fields"):
            validate_variables(Empty, {"a": 1})


class TestRevalidation:
    def test_variables_written_later_can_be_rechecked(self):
        flow = AgentFlow(steps=[], state_model=ReviewState, variables={"score": 1})
        flow.variables["reserach_results"] = 2
        with pytest.raises(WorkflowStateError, match="reserach_results"):
            flow.validate_variables()

    def test_control_valid_later_writes_still_pass(self):
        flow = AgentFlow(steps=[], state_model=ReviewState, variables={"score": 1})
        flow.variables["draft"] = "later"
        flow.validate_variables()


class TestHelpers:
    def test_field_names_from_pydantic_and_dataclass_agree(self):
        assert state_field_names(ReviewState) == state_field_names(PlainState) == {"draft", "score"}

    def test_build_state_returns_none_without_a_model(self):
        assert build_state(None, {"a": 1}) is None

"""Typed workflow state.

A flow's state was an untyped ``Dict[str, Any]``. A typo in a variable name --
``ctx.variables["reserach_results"]`` -- was found at runtime, if at all, and
nothing told you what fields a workflow's state carried without reading every
step. CrewAI leads its production guide with typed flow state for exactly this
reason.

    class ReviewState(BaseModel):
        draft: str = ""
        score: int = 0

    flow = AgentFlow(steps=[...], state_model=ReviewState, variables={"draft": "hi"})
    flow.state.draft          # typed, and a typo is an AttributeError here
    flow.validate_variables() # raises on an unknown or ill-typed field

Works with a Pydantic model or a plain dataclass, because this package must not
require Pydantic for a workflow to run. Without ``state_model`` nothing changes:
``variables`` stays the untyped dict it has always been, so this is additive.
"""

import dataclasses
from typing import Any, Dict, Optional, Type

__all__ = ["WorkflowStateError", "build_state", "state_field_names", "validate_variables"]


class WorkflowStateError(ValueError):
    """Raised when variables do not match the declared state model."""


def _is_pydantic(model: Any) -> bool:
    return hasattr(model, "model_validate") or hasattr(model, "parse_obj")


def state_field_names(model: Type) -> set:
    """The field names a state model declares."""
    if model is None:
        return set()
    fields = getattr(model, "model_fields", None)  # pydantic v2
    if isinstance(fields, dict):
        return set(fields)
    fields = getattr(model, "__fields__", None)  # pydantic v1
    if isinstance(fields, dict):
        return set(fields)
    if dataclasses.is_dataclass(model):
        return {f.name for f in dataclasses.fields(model)}
    return set()


def validate_variables(model: Optional[Type], variables: Dict[str, Any]) -> None:
    """Raise unless ``variables`` fit ``model``.

    An UNKNOWN key is an error, not something to ignore: silently accepting
    ``reserach_results`` is precisely the typo this exists to catch.
    """
    if model is None:
        return
    declared = state_field_names(model)
    if not declared:
        raise WorkflowStateError(
            f"{getattr(model, '__name__', model)!r} declares no fields, so it cannot "
            f"describe this flow's state. Use a Pydantic model or a dataclass."
        )
    unknown = sorted(set(variables or {}) - declared)
    if unknown:
        raise WorkflowStateError(
            f"Unknown workflow variable(s) {unknown} for state model "
            f"{getattr(model, '__name__', model)!r}. Declared fields: "
            f"{sorted(declared)}. A misspelled variable would otherwise be "
            f"written, never read, and never reported."
        )
    build_state(model, variables)  # surfaces type errors too


def build_state(model: Optional[Type], variables: Dict[str, Any]) -> Any:
    """Construct the typed state instance from ``variables``."""
    if model is None:
        return None
    data = dict(variables or {})
    try:
        if _is_pydantic(model):
            if hasattr(model, "model_validate"):
                return model.model_validate(data)
            return model.parse_obj(data)
        if dataclasses.is_dataclass(model):
            return model(**data)
        return model(**data)
    except WorkflowStateError:
        raise
    except Exception as exc:
        raise WorkflowStateError(
            f"Workflow variables do not fit state model "
            f"{getattr(model, '__name__', model)!r}: {type(exc).__name__}: {exc}"
        ) from exc

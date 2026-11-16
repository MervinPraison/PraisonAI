"""Wrapper exceptions join the core ``PraisonAIError`` hierarchy (#6173)."""

import pytest

from praisonaiagents.errors import PraisonAIError

from praisonai.agents_generator import ToolTimeoutError
from praisonai.api.agent_invoke import AgentConfigError
from praisonai.auto import MergeConflictError
from praisonai.integrations.base import CLIExecutionError
from praisonai.integrations.managed_agents import ManagedSandboxRequired
from praisonai.jobs.executor import JobQueueFull
from praisonai.recipe.exceptions import RecipeError, RecipeNotFoundError
from praisonai.recipe.history import RunHistoryError, RunNotFoundError
from praisonai.recipe.policy import PolicyDeniedError, PolicyError
from praisonai.recipe.registry import RegistryError
from praisonai.recipe.security import SecurityError as RecipeSecurityError
from praisonai.replay.rerun import RerunError
from praisonai.templates.dependency_checker import StrictModeError
from praisonai.templates.tool_override import SecurityError as ToolSecurityError


@pytest.mark.parametrize(
    "exc, stdlib",
    [
        (ToolTimeoutError("t", 5, False), TimeoutError),
        (AgentConfigError("bad"), ValueError),
        (MergeConflictError("bad"), Exception),
        (CLIExecutionError(["claude"], 1, "boom"), RuntimeError),
        (ManagedSandboxRequired("need sandbox"), RuntimeError),
        (JobQueueFull(2.0), Exception),
        (RecipeError("x", recipe="r"), Exception),
        (RecipeNotFoundError("x"), Exception),
        (RunHistoryError("x"), Exception),
        (RunNotFoundError("x"), Exception),
        (PolicyError("x"), Exception),
        (PolicyDeniedError("x"), Exception),
        (RegistryError("x"), Exception),
        (RecipeSecurityError("x"), Exception),
        (RerunError("x"), RuntimeError),
        (StrictModeError("x", {}), Exception),
        (ToolSecurityError("x"), Exception),
    ],
)
def test_wrapper_errors_are_praisonai_errors(exc, stdlib):
    assert isinstance(exc, PraisonAIError)
    assert isinstance(exc, stdlib)  # existing stdlib catches still work
    with pytest.raises(PraisonAIError):
        raise exc


def test_message_args_and_attrs_preserved():
    assert str(AgentConfigError("bad config")) == "bad config"
    assert AgentConfigError("a", "b").args == ("a", "b")
    assert str(AgentConfigError()) == ""

    e = RecipeError("missing", recipe="r1", details={"k": 1})
    assert str(e) == "missing" and e.message == "missing"
    assert e.recipe == "r1" and e.details == {"k": 1}

    q = JobQueueFull(3.0)
    assert q.retry_after == 3.0 and str(q) == "Job queue is full; retry after 3.0s"

    t = ToolTimeoutError("search", 5, True)
    assert str(t) == "Tool 'search' exceeded 5s" and t.tool_name == "search"

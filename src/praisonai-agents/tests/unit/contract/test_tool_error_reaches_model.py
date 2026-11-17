"""D-03: a tool that raises is reported to the model; only transient errors retry.

Before: a raising tool body ran three times (side effects repeated) and the turn
ended with ToolExecutionError, so the model never saw what went wrong. Now a
non-transient error (card declined, bad arguments) runs once and reaches the
model as the tool result; a timeout or connection error is retried and then
reported the same way. Same behaviour on the OpenAI and litellm routes.
"""
import pytest

from tests.unit.contract.test_chat_path_contract import (  # noqa: F401  (fixture)
    REQUESTS, _agent, _tool_outputs, _turn, stub,
)

ROUTES = ["openai_client", "litellm_chat"]
MODES = ["chat", "achat"]


def _raising_tool(exc, calls):
    def lookup(query: str) -> str:
        """Look something up."""
        calls.append(query)
        raise exc
    return lookup


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", MODES)
def test_non_transient_error_runs_once_and_reaches_model(stub, route, mode):
    calls = []
    agent = _agent(route, stub, tools=[_raising_tool(RuntimeError("card declined"), calls)])
    _turn(agent, mode)  # must not raise ToolExecutionError
    assert len(calls) == 1
    assert any("card declined" in out for out in _tool_outputs())


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("msg", ["connection refused by business rule",
                                 "rate limit of 1 card per day", "request timed out"])
def test_non_transient_error_is_not_retried_on_its_wording(stub, route, mode, msg):
    calls = []
    agent = _agent(route, stub, tools=[_raising_tool(RuntimeError(msg), calls)])
    _turn(agent, mode)
    assert len(calls) == 1
    assert any(msg in out for out in _tool_outputs())


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("exc", [TimeoutError("upstream timed out"),
                                 ConnectionError("connection reset")])
def test_transient_error_is_retried_then_reaches_model(stub, route, mode, exc):
    calls = []
    agent = _agent(route, stub, tools=[_raising_tool(exc, calls)])
    _turn(agent, mode)
    assert len(calls) > 1
    assert any(str(exc) in out for out in _tool_outputs())


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", MODES)
def test_wrong_arguments_reach_model(stub, route, mode):
    calls = []

    def charge(amount: int) -> str:
        """Charge a card."""
        calls.append(amount)
        return "ok"

    agent = _agent(route, stub, tools=[charge])
    _turn(agent, mode)  # the stub calls the tool with {"query": ...}
    assert calls == []
    assert any("query" in out for out in _tool_outputs())

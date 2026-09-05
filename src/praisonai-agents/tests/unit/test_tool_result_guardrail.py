"""GuardrailProtocol.validate_tool_result gates a tool's raw output.

A tool's result used to flow straight back into the LLM context with no
guardrail call between execution and delivery, so a leaked secret or a
prompt-injection payload in the raw tool output was completely unguarded
(validate_output only ever sees the model's paraphrase). These tests cover the
new tool-result surface: rejection (fail-closed), in-place redaction, error
fail-closed, and the zero-overhead path when no such guardrail is set.
"""
import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents.guardrails import GuardrailChain
from praisonaiagents.guardrails.protocols import (
    GUARDRAIL_PROTOCOL_METHODS,
    is_guardrail_object,
)


def run_shell(cmd: str) -> str:
    return "API_KEY=sk-leaked-secret-123"


class NoSecretsGuardrail:
    def validate_input(self, content, **kwargs):
        return True, content

    def validate_output(self, content, **kwargs):
        return ("sk-" not in content), content

    def validate_tool_call(self, tool_name, arguments, **kwargs):
        return True, arguments

    def validate_tool_result(self, tool_name, result, **kwargs):
        return ("sk-" not in str(result)), result


class RedactingGuardrail:
    def validate_tool_result(self, tool_name, result, **kwargs):
        return True, str(result).replace("sk-leaked-secret-123", "[REDACTED]")


class RaisingGuardrail:
    def validate_tool_result(self, tool_name, result, **kwargs):
        raise RuntimeError("boom")


def _agent(guardrails):
    return Agent(name="Ops", instructions="test", llm="gpt-4o-mini",
                 tools=[run_shell], guardrails=guardrails)


class TestProtocolSurface:
    def test_method_is_part_of_protocol_surface(self):
        assert "validate_tool_result" in GUARDRAIL_PROTOCOL_METHODS

    def test_result_only_object_is_a_guardrail(self):
        assert is_guardrail_object(RedactingGuardrail()) is True


class TestGuardrailChain:
    def test_chain_rejects(self):
        ok, out = GuardrailChain([NoSecretsGuardrail()]).validate_tool_result(
            "run_shell", "API_KEY=sk-leaked-secret-123")
        assert ok is False

    def test_chain_redacts(self):
        ok, out = GuardrailChain([RedactingGuardrail()]).validate_tool_result(
            "run_shell", "API_KEY=sk-leaked-secret-123")
        assert ok is True
        assert out == "API_KEY=[REDACTED]"

    def test_chain_fail_closed_on_error(self):
        ok, _ = GuardrailChain([RaisingGuardrail()]).validate_tool_result("t", "x")
        assert ok is False

    def test_chain_fail_open_allows_on_error(self):
        ok, out = GuardrailChain([RaisingGuardrail()], fail_open=True).validate_tool_result("t", "x")
        assert ok is True
        assert out == "x"


class TestAgentWiring:
    def test_registered_when_exposed(self):
        a = _agent(NoSecretsGuardrail())
        assert a._tool_result_guardrails, "validate_tool_result surface not registered"

    def test_empty_without_guardrail(self):
        a = Agent(name="None", instructions="test", llm="gpt-4o-mini", tools=[run_shell])
        assert a._tool_result_guardrails == []

    def test_empty_for_plain_callable(self):
        def cb(task_output):
            return True, task_output
        a = _agent(cb)
        assert a._tool_result_guardrails == []


class TestSyncExecution:
    def test_leaked_secret_is_rejected(self):
        a = _agent(NoSecretsGuardrail())
        res = a.execute_tool("run_shell", {"cmd": "env"})
        assert isinstance(res, dict) and res.get("guardrail_denied") is True

    def test_secret_is_redacted(self):
        a = _agent(RedactingGuardrail())
        res = a.execute_tool("run_shell", {"cmd": "env"})
        assert res == "API_KEY=[REDACTED]"

    def test_fail_closed_on_guardrail_error(self):
        a = _agent(RaisingGuardrail())
        res = a.execute_tool("run_shell", {"cmd": "env"})
        assert isinstance(res, dict) and res.get("guardrail_denied") is True

    def test_passthrough_without_guardrail(self):
        a = Agent(name="None", instructions="test", llm="gpt-4o-mini", tools=[run_shell])
        assert a.execute_tool("run_shell", {"cmd": "env"}) == "API_KEY=sk-leaked-secret-123"


class TestAsyncExecution:
    def test_leaked_secret_is_rejected(self):
        a = _agent(NoSecretsGuardrail())
        res = asyncio.run(a.execute_tool_async("run_shell", {"cmd": "env"}))
        assert isinstance(res, dict) and res.get("guardrail_denied") is True


class TestErrorShapedResultsAreValidated:
    """A tool-authored ``{"error": ...}`` is still untrusted content and must be
    validated — only framework-issued denial markers skip re-inspection."""

    def test_error_dict_with_secret_is_still_validated(self):
        a = _agent(NoSecretsGuardrail())
        result = {"error": "partial failure", "content": "API_KEY=sk-leaked-secret-123"}
        out = a._apply_tool_result_guardrails("crawl", result)
        assert isinstance(out, dict) and out.get("guardrail_denied") is True

    def test_error_dict_is_redacted(self):
        a = _agent(RedactingGuardrail())
        result = {"error": "partial", "content": "API_KEY=sk-leaked-secret-123"}
        out = a._apply_tool_result_guardrails("crawl", result)
        assert "[REDACTED]" in str(out)
        assert "sk-leaked-secret-123" not in str(out)

    def test_framework_denial_dict_passes_through_untouched(self):
        a = _agent(NoSecretsGuardrail())
        denied = {"error": "denied by guardrail", "guardrail_denied": True,
                  "leak": "sk-leaked-secret-123"}
        out = a._apply_tool_result_guardrails("run_shell", denied)
        assert out is denied

    def test_policy_denial_dict_passes_through_untouched(self):
        a = _agent(NoSecretsGuardrail())
        denied = {"error": "denied by policy", "policy_denied": True}
        out = a._apply_tool_result_guardrails("run_shell", denied)
        assert out is denied


class TestAsyncMCPResultIsValidated:
    """The async MCP branch returns early — a successful MCP result must still be
    gated there, or configured tool-result guardrails would never see it."""

    def test_async_mcp_secret_is_rejected(self):
        a = _agent(NoSecretsGuardrail())

        def fake_resolve(function_name, arguments):
            return True, "API_KEY=sk-leaked-secret-123"

        a._resolve_mcp_tool_result = fake_resolve
        res = asyncio.run(a.execute_tool_async("mcp_tool", {}))
        assert isinstance(res, dict) and res.get("guardrail_denied") is True

    def test_async_mcp_secret_is_redacted(self):
        a = _agent(RedactingGuardrail())

        def fake_resolve(function_name, arguments):
            return True, "API_KEY=sk-leaked-secret-123"

        a._resolve_mcp_tool_result = fake_resolve
        res = asyncio.run(a.execute_tool_async("mcp_tool", {}))
        assert "[REDACTED]" in str(res)
        assert "sk-leaked-secret-123" not in str(res)

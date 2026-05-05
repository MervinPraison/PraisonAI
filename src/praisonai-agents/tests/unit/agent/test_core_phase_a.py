"""Phase A gap-closure tests: C1 seed, C2 cancel_token, C4 tool validator, C7 PII.

These tests exercise the four gap closures identified in the core-features gap
analysis. They target the existing infrastructure (InterruptController,
ToolValidatorProtocol, trace/redact rules) which was defined but not wired into
`Agent.chat()` / tool execution paths.
"""

from __future__ import annotations

from praisonaiagents import Agent
from praisonaiagents.tools.validators import (
    ToolValidatorProtocol,
    ValidationResult,
)


# ────────────────────────────────────────────────────────────────────────────
# C1 — seed threaded through Agent.chat()
# ────────────────────────────────────────────────────────────────────────────

class TestC1SeedPassthrough:
    def test_chat_signature_accepts_seed(self):
        """`Agent.chat` must accept a per-call `seed=` kwarg."""
        import inspect
        sig = inspect.signature(Agent.chat)
        assert "seed" in sig.parameters, (
            "Agent.chat() must expose seed= to let callers request determinism"
        )

    def test_seed_reaches_llm_build_params(self, monkeypatch):
        """A `seed=42` passed to chat() must appear in the LLM kwargs."""
        captured = {}

        # Use dict-form llm= so the custom-LLM path (with llm_instance) is taken.
        agent = Agent(name="C1", instructions="say hi", llm={"model": "gpt-4o-mini"})
        assert getattr(agent, "llm_instance", None) is not None, \
            "dict llm= must produce a materialised llm_instance"

        # Short-circuit the LLM call so nothing hits the network
        monkeypatch.setattr(
            agent.llm_instance,
            "get_response",
            lambda **kw: (captured.update(kw) or "ok"),
        )

        agent.chat("hello", seed=42)
        assert captured.get("seed") == 42, (
            f"seed=42 did not reach LLM call; kwargs were {list(captured)}"
        )


# ────────────────────────────────────────────────────────────────────────────
# C2 — cancel_token wired into chat()
# ────────────────────────────────────────────────────────────────────────────

class TestC2CancelToken:
    def test_chat_signature_accepts_cancel_token(self):
        import inspect
        sig = inspect.signature(Agent.chat)
        assert "cancel_token" in sig.parameters, (
            "Agent.chat() must expose cancel_token= for cooperative cancellation"
        )

    def test_preset_cancelled_token_aborts_chat_before_llm(self, monkeypatch):
        """If the cancel token is already set when chat() is called,
        the LLM is NEVER invoked and the call returns cleanly (None)."""
        from praisonaiagents.agent.interrupt import InterruptController

        agent = Agent(name="C2", instructions="irrelevant", llm={"model": "gpt-4o-mini"})

        called = {"n": 0}

        def must_not_be_called(**kwargs):
            called["n"] += 1
            return "should not be reached"

        monkeypatch.setattr(agent.llm_instance, "get_response", must_not_be_called)

        tok = InterruptController()
        tok.request("user-cancel")

        try:
            agent.chat("anything", cancel_token=tok)
        except InterruptedError:
            pass  # acceptable outcome
        assert called["n"] == 0, (
            "LLM was invoked despite pre-set cancel_token — cancellation not wired"
        )


# ────────────────────────────────────────────────────────────────────────────
# C4 — ToolValidatorProtocol wired into tool execution
# ────────────────────────────────────────────────────────────────────────────

class _RejectingValidator:
    """Minimal ToolValidatorProtocol impl that always rejects."""

    def validate_args(self, tool_name, args, context=None):
        return ValidationResult(
            valid=False,
            errors=[f"arg-validator rejected {tool_name}"],
            remediation="Fix your tool-call schema.",
        )

    def validate_result(self, tool_name, result, context=None):
        return ValidationResult(valid=True)


class TestC4ToolValidator:
    def test_validator_implements_protocol(self):
        """Sanity: our fixture validator satisfies the protocol."""
        v = _RejectingValidator()
        assert isinstance(v, ToolValidatorProtocol)

    def test_validator_rejects_before_tool_runs(self):
        """When agent._tool_validator rejects, the tool function is NEVER called
        and the returned string contains the validator's error."""

        calls = {"n": 0}

        def fake_tool(x: int) -> int:
            calls["n"] += 1
            return x * 2

        agent = Agent(name="C4", instructions="…", tools=[fake_tool], llm="gpt-4o-mini")
        agent._tool_validator = _RejectingValidator()

        result = agent.execute_tool("fake_tool", {"x": 5})

        assert calls["n"] == 0, "tool function was executed despite validator rejection"
        assert "rejected" in str(result).lower(), (
            f"validator error not surfaced: {result!r}"
        )


# ────────────────────────────────────────────────────────────────────────────
# C7 — enable_pii_redaction() registers a BEFORE_LLM middleware
# ────────────────────────────────────────────────────────────────────────────

class TestC7PIIRedaction:
    def test_enable_pii_redaction_is_importable(self):
        from praisonaiagents.trace.redact import enable_pii_redaction
        assert callable(enable_pii_redaction)

    def test_enable_pii_redaction_is_idempotent(self):
        """Calling enable_pii_redaction() twice must not double-register."""
        from praisonaiagents.trace.redact import (
            enable_pii_redaction,
            disable_pii_redaction,
        )
        disable_pii_redaction()  # ensure clean baseline
        enable_pii_redaction()
        first_state = _pii_state_snapshot()
        enable_pii_redaction()
        second_state = _pii_state_snapshot()
        assert first_state == second_state, "enable_pii_redaction is not idempotent"
        disable_pii_redaction()

    def test_pii_scrubber_scrubs_api_keys(self):
        """The scrubber function must redact API-key-shaped strings."""
        from praisonaiagents.trace.redact import scrub_pii_text

        raw = "my api_key=sk-ABCDEF12345 and password=hunter2"
        scrubbed = scrub_pii_text(raw)
        assert "sk-ABCDEF12345" not in scrubbed
        assert "hunter2" not in scrubbed
        assert "[REDACTED]" in scrubbed


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _pii_state_snapshot():
    """Snapshot of hook registry state used by C7 idempotency test."""
    from praisonaiagents.hooks import get_default_registry
    reg = get_default_registry()
    # Count hooks registered for BEFORE_LLM — we just want stable identity
    hooks = getattr(reg, "_hooks", None) or getattr(reg, "hooks", None) or {}
    if isinstance(hooks, dict):
        bl = hooks.get("before_llm") or hooks.get("BEFORE_LLM") or []
        return len(bl)
    return None

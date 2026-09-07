"""In-run guardrail retry signalling.

A guardrail normally reports failure by returning ``(False, "why")``. That works
when the validator *is* the thing doing the checking, but not when the check
lives several frames down - a Pydantic model that fails to parse, a lookup that
comes back empty, a helper that already raises. ``GuardrailRetry`` lets any of
those hand their reason straight back to the model:

    from praisonaiagents import Agent, GuardrailRetry

    def in_customer_country(output):
        if not output.raw.startswith("SW1"):
            raise GuardrailRetry("the postcode must be in the customer's country")
        return True, output

    agent = Agent(instructions="...", guardrails=in_customer_country)

The message is appended to the *same* conversation as a user turn, so the model
patches its previous answer in place instead of restarting the task, bounded by
``max_guardrail_retries`` (``GuardrailConfig(max_retries=...)``).

Any other exception raised by a guardrail is still treated as a validation
*error* and reported as such; ``GuardrailRetry`` is the deliberate "not
acceptable, here is why" signal.
"""

__all__ = ["GuardrailRetry"]


class GuardrailRetry(Exception):
    """Raised by a guardrail to send its reason back to the model for another attempt.

    Args:
        feedback: Plain-language reason the output was rejected. It is shown to
            the model verbatim, so write it as an instruction to the model
            ("the postcode must be in the customer's country"), not as a stack
            trace.

    Attributes:
        feedback: The same string, kept as a named attribute so callers do not
            have to ``str()`` the exception.
    """

    def __init__(self, feedback: str = "Output failed validation"):
        feedback = str(feedback) if feedback else "Output failed validation"
        super().__init__(feedback)
        self.feedback = feedback

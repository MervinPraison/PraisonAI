"""Model-family-aware agent harness, plus the test doubles for model calls.

Selects, by model id/family, a base/harness system-prompt fragment and a
preferred file-edit format (string-replace ``edit_file`` vs ``apply_patch``).

The default profile reproduces the current generic behaviour exactly, so
behaviour is unchanged when no family match applies. The registry is
data-driven and overridable; resolution is lazy with zero import-time cost.

Usage::

    from praisonaiagents.model_harness import resolve_harness

    profile = resolve_harness("claude-opus-4")
    profile.base_prompt          # optional prompt fragment (str or None)
    profile.preferred_edit_format  # "apply_patch" | "edit_file" | None

Testing::

    from praisonaiagents import Agent
    from praisonaiagents.model_harness import ScriptedModel, allow_model_requests

    allow_model_requests(False)   # nothing in this suite may reach a provider

    model = ScriptedModel(["Paris."])
    agent = Agent(instructions="You are a geography bot.", llm=model)
    assert agent.start("Capital of France?") == "Paris."
    assert model.requests[0].system_prompt.startswith("You are a geography bot.")

:class:`ScriptedModel` returns scripted replies in order, can script a tool call
followed by a final answer, records every request the agent sent, and raises
:class:`ScriptExhausted` when the script runs out. :func:`allow_model_requests`
is the global "no real model calls" switch.
"""

from praisonaiagents._lazy import create_lazy_getattr

_LAZY_IMPORTS = {
    "HarnessProfile": ("praisonaiagents.model_harness.profiles", "HarnessProfile"),
    "HarnessResolverProtocol": (
        "praisonaiagents.model_harness.profiles",
        "HarnessResolverProtocol",
    ),
    "resolve_harness": ("praisonaiagents.model_harness.profiles", "resolve_harness"),
    "register_profile": (
        "praisonaiagents.model_harness.profiles",
        "register_profile",
    ),
    "DEFAULT_PROFILE": (
        "praisonaiagents.model_harness.profiles",
        "DEFAULT_PROFILE",
    ),
    # Test doubles and the real-request guard.
    "ScriptedModel": ("praisonaiagents.model_harness.scripted", "ScriptedModel"),
    "ScriptedReply": ("praisonaiagents.model_harness.scripted", "ScriptedReply"),
    "ScriptedToolCall": (
        "praisonaiagents.model_harness.scripted",
        "ScriptedToolCall",
    ),
    "RecordedRequest": (
        "praisonaiagents.model_harness.scripted",
        "RecordedRequest",
    ),
    "ScriptExhausted": (
        "praisonaiagents.model_harness.scripted",
        "ScriptExhausted",
    ),
    "ScriptedModelError": (
        "praisonaiagents.model_harness.scripted",
        "ScriptedModelError",
    ),
    "allow_model_requests": (
        "praisonaiagents.model_harness.guard",
        "allow_model_requests",
    ),
    "model_requests_allowed": (
        "praisonaiagents.model_harness.guard",
        "model_requests_allowed",
    ),
    "no_model_requests": (
        "praisonaiagents.model_harness.guard",
        "no_model_requests",
    ),
    "ModelRequestBlocked": (
        "praisonaiagents.model_harness.guard",
        "ModelRequestBlocked",
    ),
}

__all__ = list(_LAZY_IMPORTS.keys())

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)

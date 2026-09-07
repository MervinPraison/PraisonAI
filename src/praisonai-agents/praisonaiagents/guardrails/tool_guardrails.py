"""Per-tool guardrails: validate the arguments and the result of ONE tool.

PraisonAI already had guardrails at two scopes and nothing in between:

* ``Agent(guardrail=...)`` / ``Task(guardrail=...)`` validate the **final
  output** of a whole run.
* The agent-wide tool surface (``_tool_call_guardrails`` /
  ``_tool_result_guardrails``, fed from a ``GuardrailProtocol`` object passed to
  ``Agent(guardrails=...)``) fires for **every tool** the agent can reach.
* ``approval`` gates a tool call on a **human**, interactively.

None of those let a tool author say "*this one* tool must never be called with a
recipient outside the company domain". Doing it today meant policing every tool
through interactive approval, or hand-wrapping the function body. This module
adds the missing scope, declared on the tool itself next to ``approval`` and
``restart_safe``::

    def internal_recipients_only(arguments: dict):
        if not arguments.get("to", "").endswith("@corp.com"):
            return False, "Recipient is outside the company domain."
        return True, arguments

    @tool(input_guardrails=[internal_recipients_only])
    def send_email(to: str, body: str) -> str:
        ...

The guardrail fires on every invocation of ``send_email`` and never for any
other tool.

What a guardrail function receives and returns
----------------------------------------------
An **input** guardrail takes one positional argument, the ``arguments`` dict the
model proposed. An **output** guardrail takes one positional argument, the raw
result the tool returned. Both use the ``(success, value)`` tuple convention
already used everywhere else in this package (``Agent(guardrail=fn)``,
``GuardrailProtocol``):

* ``(True, value)`` - allow; ``value`` replaces the arguments/result, so a
  guardrail can **rewrite** (sanitise arguments, redact a secret out of a
  result). ``(True, None)`` allows the original through unchanged.
* ``(False, "reason")`` - block. The reason is handed back to the **model** as
  the tool result so it can react and try something else; it is never raised at
  the user.
* A bare ``True`` / ``False`` works too, as does a
  :class:`~praisonaiagents.guardrails.GuardrailResult`.
* ``None`` (a validator that only ever returns ``False`` to object, and falls
  off the end otherwise) means "no opinion" - allow unchanged. The deny path is
  explicit, so nothing is lost by being permissive here.
* Anything else is a contract violation and **fails closed**: an unreadable
  verdict is not an approval.

A guardrail that raises also fails closed, matching ``GuardrailChain``'s
default. Pass an object exposing ``validate_tool_call`` / ``validate_tool_result``
(any ``GuardrailProtocol`` implementation, including a ``GuardrailChain``) to
reuse an existing guardrail unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .chain import GuardrailChain
from .guardrail_result import GuardrailResult

logger = logging.getLogger(__name__)

# Direction identifiers. An input guardrail gates the arguments before dispatch;
# an output guardrail gates the raw result before it re-enters the LLM context.
INPUT = "input"
OUTPUT = "output"

# The protocol method each direction drives. Per-tool guardrails deliberately
# speak the SAME protocol as agent-wide ones so a guardrail written for one
# scope drops into the other with no adaptation.
_METHOD_FOR = {INPUT: "validate_tool_call", OUTPUT: "validate_tool_result"}

_DEFAULT_REASON = {
    INPUT: "rejected by an input guardrail",
    OUTPUT: "rejected by an output guardrail",
}

# Attribute a tool declares its guardrails on, per direction.
ATTR_FOR = {INPUT: "input_guardrails", OUTPUT: "output_guardrails"}

# Where a coerced chain is memoised on a tool object, so a tool that declared a
# raw list (e.g. a ``BaseTool`` subclass with ``input_guardrails = [fn]`` as a
# class attribute) is only coerced once rather than on every invocation.
_CACHE_ATTR = "_praison_tool_guardrail_chains"


def _interpret(outcome: Any, original: Any, default_reason: str) -> Tuple[bool, Any, str]:
    """Normalise a user guardrail's return value into ``(ok, value, reason)``.

    Accepts every shape documented in the module docstring. Unknown shapes fail
    closed - a verdict we cannot read must not be treated as an approval.
    """
    if outcome is None:
        # "No opinion": a validator that objects explicitly (returns False or
        # raises) and simply falls off the end on the happy path.
        return True, original, ""

    if isinstance(outcome, GuardrailResult):
        if outcome.success:
            # ``result=None`` means "unchanged" - keep the caller's value rather
            # than replacing it with None.
            return True, original if outcome.result is None else outcome.result, ""
        return False, original, outcome.error or default_reason

    # bool must be checked before tuple; it is neither, but ordering keeps the
    # intent obvious next to the tuple branch.
    if isinstance(outcome, bool):
        return (True, original, "") if outcome else (False, original, default_reason)

    if isinstance(outcome, tuple) and len(outcome) == 2:
        ok, data = outcome
        if ok:
            return True, original if data is None else data, ""
        return False, original, str(data) if data else default_reason

    return False, original, (
        f"guardrail returned {type(outcome).__name__}; expected (bool, value), "
        "a bool, a GuardrailResult, or None"
    )


class _CallableToolGuardrail:
    """Adapts a plain ``fn(value) -> (ok, value)`` into the guardrail protocol.

    Keeping the adapter protocol-shaped (rather than special-casing callables in
    the executor) is what lets per-tool and agent-wide guardrails share one
    chain implementation and one call path.
    """

    direction = INPUT

    def __init__(self, fn, name: Optional[str] = None):
        if not callable(fn):
            raise TypeError(
                f"A tool guardrail must be callable or expose "
                f"{_METHOD_FOR[self.direction]}(); got {type(fn).__name__}."
            )
        self._fn = fn
        self.name = name or getattr(fn, "__name__", None) or type(fn).__name__

    def _run(self, value: Any) -> Tuple[bool, Any, str]:
        return _interpret(self._fn(value), value, _DEFAULT_REASON[self.direction])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.name}>"


class ToolInputGuardrail(_CallableToolGuardrail):
    """Gates a single tool's arguments before the tool runs.

    Wraps a ``fn(arguments: dict)`` validator. A rewrite must still be a mapping
    of keyword arguments - returning anything else is treated as a contract
    violation and blocks, because handing a non-mapping to the tool would raise
    inside user code instead of producing a message the model can act on.
    """

    direction = INPUT

    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any], **kwargs):
        ok, value, reason = self._run(arguments)
        if not ok:
            return False, reason
        if not isinstance(value, dict):
            return False, (
                f"input guardrail '{self.name}' rewrote the arguments to "
                f"{type(value).__name__}; expected a dict of keyword arguments"
            )
        return True, value


class ToolOutputGuardrail(_CallableToolGuardrail):
    """Gates a single tool's raw result before it re-enters the LLM context."""

    direction = OUTPUT

    def validate_tool_result(self, tool_name: str, result: Any, **kwargs):
        ok, value, reason = self._run(result)
        if not ok:
            return False, reason
        return True, value


class ToolGuardrailChain(GuardrailChain):
    """A :class:`GuardrailChain` that reports *why* a tool call was rejected.

    The base chain deliberately returns the **unchanged input** on failure
    (``return False, arguments``) because its agent-wide callers only need the
    boolean and want to keep their arguments intact. A per-tool guardrail has to
    hand a message back to the model so it can react, so this subclass
    propagates the guardrail's reason as the second element instead.

    Everything else - ordering, short-circuit on first failure, fail-closed on a
    raising guardrail, the ``fail_open`` escape hatch - is inherited unchanged.
    A second element that is not a non-empty string is not a reason (a raw
    ``GuardrailProtocol`` object echoes the arguments back), so the direction's
    default reason is used in that case.
    """

    def __init__(self, guardrails: List[Any], fail_open: bool = False, direction: str = INPUT):
        super().__init__(guardrails, fail_open=fail_open)
        self.direction = direction

    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any], **kwargs):
        return self._run_direction(INPUT, tool_name, arguments, **kwargs)

    def validate_tool_result(self, tool_name: str, result: Any, **kwargs):
        return self._run_direction(OUTPUT, tool_name, result, **kwargs)

    def _run_direction(self, direction: str, tool_name: str, value: Any, **kwargs):
        method_name = _METHOD_FOR[direction]
        default_reason = _DEFAULT_REASON[direction]
        for guardrail in self.guardrails:
            method = getattr(guardrail, method_name, None)
            if method is None:
                continue
            try:
                ok, processed = method(tool_name, value, **kwargs)
            except Exception as e:  # noqa: BLE001
                name = getattr(guardrail, "name", type(guardrail).__name__)
                if self.fail_open:
                    logger.warning(
                        "Tool guardrail '%s' raised on '%s' and fail_open is set; "
                        "allowing through: %s", name, tool_name, e
                    )
                    continue
                # Fail closed: a broken guardrail must block, not permit.
                return False, f"guardrail '{name}' failed: {e}"
            if not ok:
                reason = processed if isinstance(processed, str) and processed else default_reason
                return False, reason
            value = processed
        return True, value


def _coerce_one(item: Any, direction: str):
    """Turn one user-supplied entry into a protocol-conforming guardrail."""
    method_name = _METHOD_FOR[direction]
    if callable(getattr(item, method_name, None)):
        # Already speaks the protocol (a GuardrailProtocol object, a
        # GuardrailChain, another ToolGuardrailChain) - reuse it verbatim.
        return item
    if callable(item):
        adapter = ToolInputGuardrail if direction == INPUT else ToolOutputGuardrail
        return adapter(item)
    raise TypeError(
        f"{ATTR_FOR[direction]} entries must be callable or expose "
        f"{method_name}(); got {type(item).__name__}."
    )


def build_tool_guardrails(spec: Any, direction: str) -> Optional[ToolGuardrailChain]:
    """Coerce an ``input_guardrails=`` / ``output_guardrails=`` value into a chain.

    Accepts a single guardrail or a sequence of them; each entry may be a plain
    callable or any object already exposing the matching protocol method.
    Returns ``None`` when nothing was declared, which is what keeps the
    executor's fast path free of any per-call work for unguarded tools.
    """
    if spec is None:
        return None
    if isinstance(spec, ToolGuardrailChain):
        return spec
    if isinstance(spec, GuardrailChain):
        # Reuse the chain's contents and its fail_open posture; only the
        # reason-reporting behaviour differs.
        return ToolGuardrailChain(list(spec.guardrails), fail_open=spec.fail_open,
                                  direction=direction)
    if isinstance(spec, (str, bytes)) or not isinstance(spec, (list, tuple, set)):
        spec = [spec]
    items = [_coerce_one(item, direction) for item in spec]
    if not items:
        return None
    return ToolGuardrailChain(items, direction=direction)


def get_tool_guardrail_chain(tool_obj: Any, direction: str) -> Optional[ToolGuardrailChain]:
    """Return the guardrail chain declared on ``tool_obj``, or ``None``.

    ``@tool(...)`` coerces at definition time, so this is usually a single
    attribute read. A ``BaseTool`` subclass may instead declare a raw list as a
    class attribute; that is coerced on first use and memoised on the instance.
    A malformed declaration is logged and treated as "no guardrail" rather than
    breaking every call to the tool - the declaration error surfaces at import
    time for the ``@tool`` path, which is where it belongs.
    """
    if tool_obj is None:
        return None
    declared = getattr(tool_obj, ATTR_FOR[direction], None)
    if declared is None:
        return None
    if isinstance(declared, ToolGuardrailChain):
        return declared
    cache = getattr(tool_obj, _CACHE_ATTR, None)
    if isinstance(cache, dict) and direction in cache:
        return cache[direction]
    try:
        chain = build_tool_guardrails(declared, direction)
    except TypeError as e:
        logger.warning(
            "Ignoring malformed %s on tool '%s': %s",
            ATTR_FOR[direction], getattr(tool_obj, "name", tool_obj), e
        )
        chain = None
    try:
        if not isinstance(cache, dict):
            cache = {}
            setattr(tool_obj, _CACHE_ATTR, cache)
        cache[direction] = chain
    except Exception:  # noqa: BLE001 - e.g. a slotted or immutable tool object
        pass
    return chain

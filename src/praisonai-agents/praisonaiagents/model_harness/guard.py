"""Global guard that blocks real model requests.

A test suite that stubs the model in *most* places still bills a provider (and
goes flaky) the moment one path slips through. This module is the single switch
that turns that silent slip into a loud failure::

    from praisonaiagents.model_harness import allow_model_requests

    # conftest.py -- nothing in this suite may reach a provider
    allow_model_requests(False)

Once blocked, the two request paths an :class:`~praisonaiagents.agent.Agent`
uses -- ``LLM``/LiteLLM (Chat Completions and Responses, sync, async and
streaming) and the OpenAI-native client -- raise :class:`ModelRequestBlocked`
before any network I/O, and the message names the call site in *your* code that
triggered it.

Scope: this covers the agent's own turn-taking. Auxiliary model calls made by
other subsystems (memory scoring, embeddings) hold their own clients and are
not routed through these two paths.

A :class:`~praisonaiagents.model_harness.ScriptedModel` answers from its script
without touching either path, so scripted tests keep passing while the guard is
on. That is the intended pairing: block globally, script explicitly.

The initial state can also be set from the environment, which is handy for CI
without touching test code::

    PRAISONAI_ALLOW_MODEL_REQUESTS=0 pytest

Design note -- why :class:`BaseException`: the agent's tool loop wraps model
calls in broad ``except Exception`` handlers that degrade a failure into a
``None`` result. A guard that can be swallowed is not a guard, so this error
follows the precedent pytest sets with its own outcome exceptions and derives
from ``BaseException``.
"""

from __future__ import annotations

import os
import threading
import traceback
from contextlib import contextmanager
from typing import Iterator, Optional

__all__ = [
    "ModelRequestBlocked",
    "allow_model_requests",
    "model_requests_allowed",
    "no_model_requests",
    "check_model_request",
]


# Directory of the praisonaiagents package. Frames under it are library
# internals, never the line a user should be pointed at.
_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The stdlib directory, which also contains site-packages. Requests are often
# dispatched through an asyncio event loop or a worker thread, so the innermost
# non-praisonaiagents frame is usually ``asyncio/events.py`` rather than
# anything the caller wrote. Skipping these leaves the caller's own frame.
_STDLIB_ROOT = os.path.dirname(os.__file__)


def _is_internal(filename: str) -> bool:
    """Whether a frame belongs to praisonaiagents itself."""
    return bool(filename) and filename.startswith(_PACKAGE_ROOT + os.sep)


def _is_plumbing(filename: str) -> bool:
    """Whether a frame belongs to the stdlib / installed packages."""
    return bool(filename) and filename.startswith(_STDLIB_ROOT + os.sep)


def _initial_state() -> bool:
    """Read the starting allow/block state from the environment."""
    raw = os.environ.get("PRAISONAI_ALLOW_MODEL_REQUESTS")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


_lock = threading.RLock()
_allowed = _initial_state()
# Count of currently-active no_model_requests() scopes. Requests are blocked
# whenever this is non-zero, independently of the global _allowed flag, so
# overlapping or cross-thread scopes cannot restore a shared snapshot and
# re-enable requests while another scope is still open.
_block_depth = 0


class ModelRequestBlocked(BaseException):
    """Raised when a real model request is attempted while requests are blocked.

    Derives from ``BaseException`` on purpose: the agent's tool loop catches
    ``Exception`` broadly and turns failures into a ``None`` answer, which would
    hide exactly the leak this guard exists to expose.

    Attributes:
        model: The model id the blocked request named, if known.
        provider: The request path that was blocked (e.g. ``"litellm.completion"``).
        call_site: ``"<file>:<line> in <function>"`` for the outermost caller
            outside praisonaiagents, i.e. the line in your code to fix.
    """

    def __init__(
        self,
        message: str,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        call_site: Optional[str] = None,
    ):
        self.model = model
        self.provider = provider
        self.call_site = call_site
        super().__init__(message)


def allow_model_requests(allowed: bool = True) -> None:
    """Allow or block real model requests process-wide.

    Args:
        allowed: ``True`` restores normal behaviour; ``False`` makes every real
            model request raise :class:`ModelRequestBlocked`.
    """
    global _allowed
    with _lock:
        _allowed = bool(allowed)


def model_requests_allowed() -> bool:
    """Return whether real model requests are currently permitted."""
    with _lock:
        return _allowed and _block_depth == 0


@contextmanager
def no_model_requests() -> Iterator[None]:
    """Block real model requests for the duration of the ``with`` block.

    Composes with a suite-wide :func:`allow_model_requests` call and with other
    ``no_model_requests`` blocks. Rather than saving and restoring the global
    flag -- which lets an inner or cross-thread scope exiting first re-enable
    requests while an outer scope is still open -- this increments a block
    counter, so requests stay blocked until *every* open scope has exited::

        with no_model_requests():
            agent.start("hello")  # raises ModelRequestBlocked
    """
    global _block_depth
    with _lock:
        _block_depth += 1
    try:
        yield
    finally:
        with _lock:
            _block_depth -= 1


def _describe_call_site() -> Optional[str]:
    """Name the innermost stack frame that belongs to the caller's own code.

    Walking outward from the request, the first frame that is neither
    praisonaiagents nor stdlib/site-packages plumbing is the line the user
    wrote -- the test, script or handler that ultimately asked for the model
    call. Falls back to the nearest frame outside praisonaiagents, then to the
    request site itself, so the error always points somewhere concrete.
    """
    try:
        # Drop this helper and check_model_request() from the stack.
        stack = traceback.extract_stack()[:-2]
    except Exception:  # pragma: no cover - defensive
        return None
    if not stack:
        return None

    def described(frame) -> str:
        return f"{frame.filename}:{frame.lineno} in {frame.name}"

    fallback = None
    for frame in reversed(stack):
        filename = frame.filename or ""
        if _is_internal(filename):
            continue
        if _is_plumbing(filename):
            # Remember the nearest plumbing frame in case the whole stack is
            # library code (e.g. a request issued from a background worker).
            fallback = fallback or frame
            continue
        return described(frame)
    return described(fallback or stack[-1])


def check_model_request(model: Optional[str] = None, provider: Optional[str] = None) -> None:
    """Raise :class:`ModelRequestBlocked` if real model requests are blocked.

    Call this immediately before handing a request to a provider. When requests
    are allowed (the default) it is a single global read.

    Args:
        model: Model id the request names, used in the error message.
        provider: Short label for the request path being guarded, e.g.
            ``"litellm.completion"`` or ``"openai.chat.completions"``.

    Raises:
        ModelRequestBlocked: If requests are currently blocked.
    """
    with _lock:
        blocked = (not _allowed) or _block_depth > 0
    if not blocked:
        return
    call_site = _describe_call_site()
    target = f"model {model!r}" if model else "a model"
    via = f" via {provider}" if provider else ""
    where = f"\nCalled from {call_site}." if call_site else ""
    raise ModelRequestBlocked(
        f"Blocked a real request to {target}{via}: model requests are turned off "
        f"(praisonaiagents.model_harness.allow_model_requests(False))."
        f"{where}\n"
        "Script the reply instead -- Agent(llm=ScriptedModel([\"...\"])) -- or call "
        "allow_model_requests(True) if this call really should reach the network.",
        model=model,
        provider=provider,
        call_site=call_site,
    )

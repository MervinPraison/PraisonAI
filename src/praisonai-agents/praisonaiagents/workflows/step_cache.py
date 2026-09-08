"""Cache a workflow step's result by its inputs.

Prompt caching exists; caching a STEP's output by input key does not. A
deterministic step -- a formatter, a lookup, a summariser over unchanged text --
paid full price on every re-run, which is felt most while iterating on the steps
after it.

    flow = AgentFlow(steps=[...], cache=True)          # in-memory, this run
    flow = AgentFlow(steps=[...], cache=InMemoryStepCache(max_entries=256))

The key is (step identity, input, previous output, the variables the step can
see). Two different steps, or the same step on different input, never collide.

Deliberately OPT-IN. An agent step is not always deterministic -- temperature,
tools with side effects, a clock -- and silently serving a cached answer for a
call the user expected to happen again is the kind of quiet wrongness this
codebase has been full of. Nothing caches unless asked.
"""

import hashlib
import json
from collections import OrderedDict
from typing import Any, Dict, Optional

__all__ = ["StepCacheProtocol", "InMemoryStepCache", "make_step_key", "resolve_step_cache"]


def _identify(step: Any) -> str:
    # A bare string step IS its identity. Falling through to
    # type(step).__name__ would make every string step key as "str", so two
    # different steps would share a cache entry and one would be served the
    # other's answer. A test caught exactly that.
    if isinstance(step, str):
        return step
    for attr in ("name", "__name__"):
        value = getattr(step, attr, None)
        if isinstance(value, str) and value:
            return value
    # Last resort: include id() so two distinct anonymous steps of the same
    # type do not collide either.
    return f"{type(step).__name__}:{id(step)}"


def make_step_key(step: Any, previous_output: Any, input_text: str, variables: Dict[str, Any]) -> str:
    """A stable key for (this step, these inputs).

    Variables are included because a step reads them: two runs with the same
    prompt but different variables are different calls, and sharing a cache
    entry between them would serve one run's answer to another.
    """
    payload = {
        "step": _identify(step),
        "previous": previous_output if isinstance(previous_output, str) else str(previous_output),
        "input": input_text,
        "variables": {k: str(v) for k, v in sorted((variables or {}).items())},
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class StepCacheProtocol:
    """What a step cache must do. Any object with get/set works."""

    def get(self, key: str) -> Optional[Dict[str, Any]]:  # pragma: no cover - interface
        raise NotImplementedError

    def set(self, key: str, value: Dict[str, Any]) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class InMemoryStepCache:
    """Bounded LRU cache, scoped to the process.

    Bounded on purpose: an unbounded cache on a long-running flow is a memory
    leak that only shows up in production.
    """

    def __init__(self, max_entries: int = 128):
        if max_entries <= 0:
            raise ValueError("max_entries must be positive; a zero-size cache would never hit.")
        self.max_entries = max_entries
        self._entries: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self._entries:
            self._entries.move_to_end(key)
            self.hits += 1
            return self._entries[key]
        self.misses += 1
        return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        self._entries[key] = value
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
        self.hits = self.misses = 0

    def __len__(self) -> int:
        return len(self._entries)


def resolve_step_cache(cache: Any) -> Optional[Any]:
    """Turn a ``cache=`` value into a cache object, or None for 'do not cache'."""
    if cache is None or cache is False:
        return None
    if cache is True:
        return InMemoryStepCache()
    if hasattr(cache, "get") and hasattr(cache, "set"):
        return cache
    raise TypeError(
        f"cache= must be True, False/None, or an object with get()/set(); "
        f"got {type(cache).__name__}."
    )

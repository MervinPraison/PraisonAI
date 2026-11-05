"""Cache a workflow step's result by its inputs.

Prompt caching exists; caching a STEP's output by input key does not. A
deterministic step -- a formatter, a lookup, a summariser over unchanged text --
paid full price on every re-run, which is felt most while iterating on the steps
after it.

    flow = AgentFlow(steps=[...], cache=True)          # in-memory, this run
    flow = AgentFlow(steps=[...], cache=InMemoryStepCache(max_entries=256))
    flow = AgentFlow(steps=[...], cache=FileStepCache("run.json"))  # durable resume

The key is (step identity, input, previous output, the variables the step can
see). Two different steps, or the same step on different input, never collide.

Deliberately OPT-IN. An agent step is not always deterministic -- temperature,
tools with side effects, a clock -- and silently serving a cached answer for a
call the user expected to happen again is the kind of quiet wrongness this
codebase has been full of. Nothing caches unless asked.
"""

import copy
import hashlib
import json
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

__all__ = [
    "StepCacheProtocol", "InMemoryStepCache", "FileStepCache",
    "make_step_key", "resolve_step_cache",
]


def _snapshot(value: Any) -> Any:
    # Deep copy so a cached value cannot be mutated in place by later execution
    # (or a caller) and corrupt a future hit. Some step outputs hold objects a
    # deepcopy cannot handle (locks, live clients). The caller must treat a
    # failed snapshot as uncacheable, never retain a mutable original reference.
    return copy.deepcopy(value)


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


_SCALARS = (str, int, float, complex, bool, bytes, type(None), type(Ellipsis))


def _stable(value: Any, seen: set) -> str:
    # A text form that is the same in every process. repr() is not: a set or
    # frozenset (``x in {"a", "b"}`` compiles to a frozenset constant) iterates
    # in an order that depends on the per-process string hash seed.
    if hasattr(value, "co_code"):
        return _code_fingerprint(value, seen)
    if isinstance(value, (set, frozenset)):
        return "{" + ",".join(sorted(_stable(v, seen) for v in value)) + "}"
    if isinstance(value, (tuple, list)):
        return type(value).__name__ + "(" + ",".join(_stable(v, seen) for v in value) + ")"
    return repr(value)


def _code_fingerprint(code: Any, seen: set) -> str:
    # Bytecode, names and constants, recursing into nested code objects (whose
    # repr carries a memory address that would differ in every process).
    parts = [code.co_code.hex(), repr(code.co_names)]
    parts.extend(_stable(const, seen) for const in code.co_consts)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _immutable(value: Any) -> bool:
    if isinstance(value, _SCALARS):
        return True
    if isinstance(value, (tuple, frozenset)):
        return all(_immutable(v) for v in value)
    return False


def _function_fingerprint(fn: Any, seen: set) -> str:
    # The handler's code plus what it was configured with: immutable defaults
    # and closure values (a factory's ``output="v2"``), and the module-level
    # Python functions it calls. Mutable captured state (a list it appends to,
    # a client object) is left out, or the key would change as the run goes.
    if id(fn) in seen:
        return "recursive"
    seen.add(id(fn))
    parts = [_code_fingerprint(fn.__code__, seen)]
    captured = list(getattr(fn, "__defaults__", None) or ())
    captured += sorted((getattr(fn, "__kwdefaults__", None) or {}).items())
    for cell in getattr(fn, "__closure__", None) or ():
        try:
            captured.append(cell.cell_contents)
        except ValueError:  # empty cell
            continue
    for value in captured:
        if hasattr(value, "__code__"):
            parts.append(_function_fingerprint(value, seen))
        elif _immutable(value):
            parts.append(_stable(value, seen))
    fn_globals = getattr(fn, "__globals__", None) or {}
    for name in fn.__code__.co_names:
        helper = fn_globals.get(name)
        if hasattr(helper, "__code__") and not isinstance(helper, type):
            parts.append(name + "=" + _function_fingerprint(helper, seen))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


_CONFIG_ATTRS = ("role", "goal", "backstory", "instructions", "llm", "action",
                 "description", "expected_output")


def _config(obj: Any) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        a: getattr(obj, a) for a in _CONFIG_ATTRS if isinstance(getattr(obj, a, None), str)
    }
    tools = getattr(obj, "tools", None)
    if isinstance(tools, (list, tuple)):
        config["tools"] = sorted(
            t if isinstance(t, str) else str(getattr(t, "name", None) or getattr(t, "__name__", type(t).__name__))
            for t in tools
        )
    return config


def _definition(step: Any) -> Optional[str]:
    # A step edited but kept under the same name must not be served its old
    # result from a durable cache, so its definition is part of the key: a
    # handler's code and configuration, or an agent's instructions, model and
    # tool names.
    fn = step if hasattr(step, "__code__") else getattr(step, "handler", None)
    if hasattr(fn, "__code__"):
        return _function_fingerprint(fn, set())
    config = _config(step)
    # AgentFlow wraps an Agent step in a Task(agent=...), so the agent's own
    # role, instructions and model live one level down.
    agent = getattr(step, "agent", None)
    if agent is not None and not isinstance(agent, str):
        config["agent"] = _config(agent)
    agent_config = getattr(step, "agent_config", None)
    if isinstance(agent_config, dict):
        config["agent_config"] = {k: str(v) for k, v in sorted(agent_config.items())}
    if not config:
        return None
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def make_step_key(step: Any, previous_output: Any, input_text: str, variables: Dict[str, Any]) -> str:
    """A stable key for (this step, these inputs).

    Variables are included because a step reads them: two runs with the same
    prompt but different variables are different calls, and sharing a cache
    entry between them would serve one run's answer to another.
    """
    payload = {
        "step": _identify(step),
        "definition": _definition(step),
        "previous": previous_output if isinstance(previous_output, str) else str(previous_output),
        "input": input_text,
        # Tag each variable with its type so True and "True" (or 1 and "1") do
        # not collapse to the same key and serve one call's answer to another.
        "variables": {
            k: [type(v).__name__, _stable(v, set()) if isinstance(v, (set, frozenset)) else str(v)]
            for k, v in sorted((variables or {}).items())
        },
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class StepCacheProtocol:
    """What a step cache must do. Any object with get/set works."""

    def get(self, key: str) -> Optional[Dict[str, Any]]:  # pragma: no cover - interface
        raise NotImplementedError

    def set(self, key: str, value: Dict[str, Any]) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class _ScopedStepCache:
    """Share a parent's storage while keeping included recipes' keys separate."""

    def __init__(self, parent: Any, namespace: str):
        self.parent = parent
        self.namespace = hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self.parent.get(f"{self.namespace}:{key}")

    def set(self, key: str, value: Dict[str, Any]) -> None:
        self.parent.set(f"{self.namespace}:{key}", value)


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
        # Parallel branches share one cache: a membership check racing an
        # eviction on another thread would make move_to_end raise KeyError.
        # One lock guards every read/write so no caller sees a torn state.
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                try:
                    snapshot = _snapshot(entry)
                except Exception:
                    del self._entries[key]
                    self.misses += 1
                    return None
                self._entries.move_to_end(key)
                self.hits += 1
                # Snapshot out: a cached value contains live mutable objects
                # (e.g. the workflow's variables dict) that later execution
                # mutates. Handing back the stored object would let one run's
                # later mutations corrupt a future hit.
                return snapshot
            self.misses += 1
            return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        # Snapshot in for the same reason: freeze the value at store time so
        # the caller mutating it afterwards cannot alter what is cached.
        try:
            snapshot = _snapshot(value)
        except Exception:
            # An optional cache must not fail the workflow or serve stale data
            # if an existing key is replaced with an uncacheable value.
            with self._lock:
                self._entries.pop(key, None)
            return
        with self._lock:
            self._entries[key] = snapshot
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self.hits = self.misses = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


class FileStepCache:
    """Durable step cache: resume an interrupted flow in a later process.

        flow = AgentFlow(steps=[...], cache=FileStepCache("run.json"))
        flow.run("input")   # crashes at step 4
        flow.run("input")   # steps 1-3 are served from run.json; step 4 runs

    Resume is content-addressed, not index-based: each key covers the step's
    name and definition (a handler's code, its immutable defaults and closure
    values and the module-level functions it calls; an agent's role, goal,
    instructions, model and tool names), the input, the previous step's output
    and the variables, so renaming or editing a step or changing the input
    misses the cache from that step on and it runs again. Not covered: a
    change in mutable captured state, a method or imported library a handler
    calls, or a tool's implementation. After such an edit, call ``clear()``
    (or delete the file) to re-run. Steps without a stable name never hit
    across processes; they re-run.

    Every ``set`` is a locked read-modify-write of the file, so several caches
    (or processes) on one path add to it rather than erase each other's
    entries, and a crash mid-write keeps the last good file. A value that JSON
    cannot store unchanged (an object, int dict keys, a tuple) is rejected (the
    workflow logs a warning and carries on) rather than stored lossily.
    """

    def __init__(self, path: str):
        self.path = os.path.abspath(os.path.expanduser(str(path)))
        self._lock = threading.Lock()
        self._entries: Dict[str, Dict[str, Any]] = {}
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"{self.path} is not a step cache file.")
            self._entries = data

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._entries.get(key)
            return copy.deepcopy(entry) if entry is not None else None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        # Round-trip through JSON first so an unserialisable value raises here
        # and never reaches memory or disk in a form a later run cannot read.
        snapshot = json.loads(json.dumps(value))
        if snapshot != value:
            # e.g. {1: "x"} -> {"1": "x"} or (a, b) -> [a, b]: a resumed run
            # would see different data than the live run did.
            raise TypeError("Step cache value does not survive a JSON round trip unchanged.")
        from ..utils.atomic_io import update_json

        def _add(entries: Any) -> Dict[str, Any]:
            if not isinstance(entries, dict):
                raise ValueError(f"{self.path} is not a step cache file.")
            entries[key] = snapshot
            return dict(entries)

        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self._entries = update_json(self.path, _add)

    def clear(self) -> None:
        with self._lock:
            self._entries = {}
            if os.path.exists(self.path):
                os.remove(self.path)

    def __len__(self) -> int:
        with self._lock:
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

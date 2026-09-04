# praisonai/agents_generator.py

import sys
import os
import inspect
import logging
import threading
import uuid
import weakref
import re
import difflib
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from .version import __version__

# New architecture components are imported lazily to preserve the wrapper's
# lazy-import contract: eagerly importing them here would pull the heavy
# ``praisonaiagents.frameworks.*`` tree on every CLI command and ``praisonai.run``
# call. Runtime access goes through ``_get_default_adapter_registry()`` below;
# these type-only imports carry no runtime cost.
if TYPE_CHECKING:
    from .framework_adapters.base import FrameworkAdapter
    from .framework_adapters.registry import FrameworkAdapterRegistry

logger = logging.getLogger("praisonai.agents_generator")


def _yaml_safe_load(stream):
    """Lazy alias for yaml.safe_load."""
    import yaml
    return yaml.safe_load(stream)


def _strict_validation_enabled() -> bool:
    """True when PRAISONAI_VALIDATE_STRICT is set to a truthy value."""
    return os.getenv("PRAISONAI_VALIDATE_STRICT", "false").lower() == "true"


def _list_to_dict(entries: list, prefix: str, kind: str) -> dict:
    """Convert a list of named entries to a dict, preserving duplicates.

    Duplicate ``name`` keys would otherwise silently clobber each other. Instead
    we raise under ``PRAISONAI_VALIDATE_STRICT`` or warn loudly and keep both by
    suffixing the colliding key, so a multi-agent YAML never quietly shrinks.
    """
    normalized: dict = {}
    duplicates: list = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        key = entry.get("name") or f"{prefix}_{i}"
        if key in normalized:
            duplicates.append(key)
            key = f"{key}__dup_{i}"
        normalized[key] = entry
    if duplicates:
        msg = f"Duplicate {kind} name(s) in YAML: {sorted(set(duplicates))}"
        if _strict_validation_enabled():
            raise ValueError(msg)
        logger.warning("%s — kept both by suffixing keys; rename to silence.", msg)
    return normalized


def _normalize_yaml_config(config: dict) -> dict:
    """Normalise list-format agents/tasks YAML to dict format expected by merge/run."""
    if not isinstance(config, dict):
        return config

    agents = config.get("agents")
    if isinstance(agents, list):
        config["agents"] = _list_to_dict(agents, "agent", "agent")

    for bucket_key in ("agents", "roles"):
        bucket = config.get(bucket_key)
        if isinstance(bucket, dict):
            for agent_config in bucket.values():
                if isinstance(agent_config, dict) and "instructions" in agent_config and "backstory" not in agent_config:
                    agent_config["backstory"] = agent_config["instructions"]

    roles = config.get("roles")
    if isinstance(roles, list):
        config["roles"] = _list_to_dict(roles, "role", "role")

    tasks = config.get("tasks")
    if isinstance(tasks, list):
        bucket_from_roles = "roles" in config
        bucket = config.get("roles") or config.get("agents") or {}
        if not isinstance(bucket, dict):
            bucket = {}
        for i, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            agent_key = task.get("agent")
            if not agent_key or agent_key not in bucket or not isinstance(bucket[agent_key], dict):
                msg = (
                    f"Task {task.get('name', f'task_{i}')!r} references "
                    f"unknown agent {agent_key!r}; skipping."
                )
                if _strict_validation_enabled():
                    raise ValueError(msg)
                logger.warning(msg)
                continue
            entry = bucket[agent_key].setdefault("tasks", {})
            task_name = task.get("name", f"task_{i}")
            if task_name in entry:
                dup_msg = (
                    f"Duplicate task name {task_name!r} for agent {agent_key!r} in YAML"
                )
                if _strict_validation_enabled():
                    raise ValueError(dup_msg)
                logger.warning("%s — kept both by suffixing keys; rename to silence.", dup_msg)
                task_name = f"{task_name}__dup_{i}"
            entry[task_name] = {
                k: v for k, v in task.items() if k != "agent"
            }
        if not bucket_from_roles and bucket:
            config["roles"] = {k: v for k, v in bucket.items()}
        config.pop("tasks", None)

    return config


def _get_default_adapter_registry():
    """Lazy import for the adapter registry — defers entry-point discovery."""
    from .framework_adapters.registry import get_default_registry
    return get_default_registry()

# Import availability flags
# Compatibility imports - now handled by centralized detection
# (inbuilt_tools still defines these but they're read-only compatibility)

# BaseTool import is now handled centrally by ToolResolver

# Framework availability detection (lazy via __getattr__)
from ._framework_availability import is_available

# Lazy constants mapping for backward compatibility
_AVAIL = {
    "PRAISONAI_TOOLS_AVAILABLE": "praisonai_tools",
    "CREWAI_AVAILABLE": "crewai",
    "AUTOGEN_AVAILABLE": "autogen",
    "AG2_AVAILABLE": "ag2",
    "PRAISONAI_AVAILABLE": "praisonaiagents",
    "AGENTOPS_AVAILABLE": "agentops",
}

__all__ = list(_AVAIL.keys())

def __getattr__(name):
    """Lazy attribute access for framework availability constants.
    
    This allows backward compatibility while avoiding import-time probing.
    Only probes the framework when the constant is actually accessed.
    """
    if name in _AVAIL:
        return is_available(_AVAIL[name])
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def __dir__():
    return sorted(set(globals()) | set(_AVAIL))

# Framework adapter registry - now uses proper registry pattern
# This replaces the hardcoded FRAMEWORK_ADAPTERS dict

# Note: OTEL_SDK_DISABLED moved to CLI entry point per issue requirements



_DEFAULT_TOOL_TIMEOUT_WORKERS = 32


class ToolTimeoutError(TimeoutError):
    """Raised when a wrapped tool exceeds its per-call timeout.

    Preserves the tool's declared return-type contract: instead of silently
    downgrading a typed return value to a JSON string, the wrapper raises this
    so the framework adapter (a per-adapter concern) can translate it into
    whatever its framework expects.
    """

    def __init__(self, tool_name, timeout_seconds, background_work_may_continue):
        super().__init__(
            f"Tool {tool_name!r} exceeded {timeout_seconds}s"
        )
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        self.background_work_may_continue = background_work_may_continue


def _resolve_tool_timeout_workers():
    """Resolve the timeout worker count, tolerating a bad env value.

    A typo or non-positive ``PRAISONAI_TOOL_TIMEOUT_WORKERS`` must not crash
    every timed tool call; we warn and fall back to the safe default instead.
    """
    raw = os.environ.get("PRAISONAI_TOOL_TIMEOUT_WORKERS")
    if raw is None:
        return _DEFAULT_TOOL_TIMEOUT_WORKERS
    try:
        workers = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid PRAISONAI_TOOL_TIMEOUT_WORKERS=%r; using default of %d.",
            raw, _DEFAULT_TOOL_TIMEOUT_WORKERS,
        )
        return _DEFAULT_TOOL_TIMEOUT_WORKERS
    if workers < 1:
        logger.warning(
            "PRAISONAI_TOOL_TIMEOUT_WORKERS must be >= 1 (got %d); using default of %d.",
            workers, _DEFAULT_TOOL_TIMEOUT_WORKERS,
        )
        return _DEFAULT_TOOL_TIMEOUT_WORKERS
    return workers


def _looks_like_framework_tool(tool) -> bool:
    """Whether ``tool`` is a framework tool object carrying a typed schema.

    CrewAI / LangChain ``BaseTool`` instances and praisonai ``@tool`` objects
    expose ``name``/``description`` plus an ``args_schema`` (or a dedicated
    ``_run``/``run`` execution method). Such metadata is what the downstream
    framework uses to advertise the tool to the LLM, so it must survive
    timeout-wrapping. A bare function or a plain class returns False.
    """
    if isinstance(tool, type):
        return False
    has_schema = any(
        hasattr(tool, attr) for attr in ("args_schema", "name", "description")
    )
    has_exec_method = any(
        callable(getattr(tool, m, None)) for m in ("_run", "run")
    )
    return has_schema and has_exec_method


# Marker attribute stamped on wrappers produced by ``_wrap_with_timeout``. Its
# *value* is the owning executor_factory's identity (not just True) so a shared
# framework-tool object is never re-wrapped by the same generator (idempotency),
# yet is correctly re-wrapped when a *different* generator takes ownership.
_TIMEOUT_MARKER = "__praisonai_timeout_wrapped__"
# Reference to the pre-wrap callable, so a re-wrap for a new owner wraps the
# original method rather than stacking on a foreign generator's wrapper.
_TIMEOUT_ORIGINAL = "__praisonai_timeout_original__"


class _TimeoutBoundTool:
    """Per-generator proxy that adds timeout enforcement to a framework tool.

    Framework tool objects (CrewAI/LangChain ``BaseTool``, praisonai ``@tool``)
    are frequently cached and shared across generators (``ToolResolver``, plugin
    registries). Mutating their ``_run``/``run`` in place would let generator B's
    executor leak into generator A's calls; when B's pool is shut down, A's tool
    call raises ``RuntimeError: cannot schedule new futures after shutdown``.

    Each generator instead installs its own proxy: the underlying object is never
    mutated, and every framework-visible attribute (``name``/``description``/
    ``args_schema`` …) is delegated through ``__getattr__`` so the LLM still sees
    the correct schema. Only ``_run``/``run`` route through this generator's own
    timeout wrapper.

    The proxy is instantiated as a *dynamic subclass of the wrapped tool's own
    class* (see :func:`_make_timeout_proxy`) so ``isinstance(proxy, BaseTool)``
    still holds. Downstream executors (``praisonaiagents`` tool_execution,
    CrewAI/LangChain) route on ``isinstance(tool, BaseTool)`` to call ``.run``;
    a plain proxy would fail that check *and* is not ``callable``, so the tool
    call would silently execute nothing. Keeping the type identity preserves the
    old in-place behaviour for every consumer while still isolating executors.
    """

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_inner"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_inner"), name, value)

    def run(self, *args, **kwargs):
        fn = object.__getattribute__(self, "_wrapped_run")
        if fn is None:
            return object.__getattribute__(self, "_inner").run(*args, **kwargs)
        return fn(*args, **kwargs)

    def _run(self, *args, **kwargs):
        fn = object.__getattribute__(self, "_wrapped__run")
        if fn is None:
            return object.__getattribute__(self, "_inner")._run(*args, **kwargs)
        return fn(*args, **kwargs)


# Cache of dynamically-generated ``(_TimeoutBoundTool, type(inner))`` subclasses
# keyed by the inner class, so we build one proxy type per tool class instead of
# per tool instance.
#
# The value is held WEAKLY (``WeakValueDictionary``), not the key. A weak *key*
# does not work here: the cached ``proxy_cls`` value inherits from ``inner_cls``,
# so it strongly retains its own key through ``__bases__``/``__mro__`` — the key
# could then never die and the cache would pin every per-request tool class for
# the process lifetime. Keying weakly on the value instead breaks that cycle: the
# proxy class stays cached only while live proxy instances (whose ``__class__`` is
# ``proxy_cls``) keep it — and those instances transitively keep ``inner_cls``
# alive via their ``_inner`` reference anyway. Once the last proxy dies, the proxy
# class is collected, the entry auto-evicts, and ``inner_cls`` is released. This
# reclaims tool classes minted per-request in long-lived hosts (``praisonai
# serve`` / gateway / jobs) instead of pinning them forever, while a fallback to
# the un-subclassable ``_TimeoutBoundTool`` (which cannot be weakly referenced,
# being module-global and never collected) is simply not cached.
_TIMEOUT_PROXY_TYPES: "weakref.WeakValueDictionary[type, type]" = weakref.WeakValueDictionary()
_TIMEOUT_PROXY_TYPES_LOCK = threading.Lock()


def _make_timeout_proxy(inner, wrapped_run=None, wrapped__run=None):
    """Build a per-generator timeout proxy that keeps ``inner``'s type identity.

    The returned object is an instance of a subclass of both
    ``_TimeoutBoundTool`` and ``type(inner)`` so ``isinstance(proxy, BaseTool)``
    (and any other base of the wrapped tool) still passes for downstream
    executors, while ``_run``/``run`` route through this generator's timeout
    wrapper and every other attribute is delegated to the shared inner object.
    The inner object itself is never mutated.
    """
    inner_cls = type(inner)
    proxy_cls = _TIMEOUT_PROXY_TYPES.get(inner_cls)
    if proxy_cls is None:
        with _TIMEOUT_PROXY_TYPES_LOCK:
            proxy_cls = _TIMEOUT_PROXY_TYPES.get(inner_cls)
            if proxy_cls is None:
                try:
                    proxy_cls = type(
                        f"_TimeoutBound_{getattr(inner_cls, '__name__', 'Tool')}",
                        (_TimeoutBoundTool, inner_cls),
                        {},
                    )
                    # Only the dynamically-minted subclass is cached, and only
                    # weakly (see _TIMEOUT_PROXY_TYPES). The un-subclassable
                    # fallback below is never cached: it is the module-global
                    # _TimeoutBoundTool (immortal, so caching buys nothing) and
                    # a WeakValueDictionary cannot retain it usefully anyway.
                    _TIMEOUT_PROXY_TYPES[inner_cls] = proxy_cls
                except TypeError:
                    # Some tool classes forbid subclassing (e.g. custom
                    # metaclass/__slots__ conflicts); fall back to the plain
                    # proxy. isinstance() will not match, but callability of the
                    # inner is still exposed via __getattr__ delegation, and the
                    # generic callable branch is preserved by the caller.
                    proxy_cls = _TimeoutBoundTool

    proxy = proxy_cls.__new__(proxy_cls)
    object.__setattr__(proxy, "_inner", inner)
    object.__setattr__(proxy, "_wrapped_run", wrapped_run)
    object.__setattr__(proxy, "_wrapped__run", wrapped__run)
    return proxy


def _wrap_with_timeout(tool, timeout_seconds: float, executor_factory, on_leaked=None, owner_key=None):
    """Enforce a per-call timeout on a tool, sync or async.

    For async tools the underlying task is cancelled on timeout. For sync tools
    the call runs in an instance-owned bounded thread pool obtained from
    ``executor_factory``; on timeout we best-effort cancel the future. Note: a
    synchronous call that has already started cannot be forcibly interrupted, so
    background work may continue executing. When the cancel fails (the worker is
    leaked), ``on_leaked`` is invoked so the owning generator can recycle its
    pool before every worker is permanently starved.

    On timeout the wrapper raises :class:`ToolTimeoutError` rather than returning
    a JSON string, so a tool's declared return-type contract is never silently
    downgraded; the framework adapter decides how to surface the timeout.
    """
    if timeout_seconds is None or timeout_seconds <= 0:
        return tool

    import asyncio
    import concurrent.futures
    import functools
    import inspect

    # Identity of the wrapper's owner so a shared framework-tool object wrapped
    # by one generator is transparently re-wrapped (not skipped) when a
    # *different* generator processes it — otherwise it would keep the first
    # generator's executor/timeout even after that generator's pool is closed.
    # Prefer a caller-supplied stable key (the generator pins a uuid at
    # construction). Never derive it from ``id(executor_factory)``: each access
    # to a bound method yields a fresh object, so its id() churns and the guard
    # would compare against a value that never repeats. Fall back to a per-call
    # sentinel so an owner-less caller is always treated as its own owner.
    _owner_key = owner_key if owner_key is not None else object()

    def _wrap_callable(fn):
        """Return a timeout-enforcing wrapper around a bare callable."""
        if not callable(fn):
            return fn

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def _async_wrapped(*args, **kwargs):
                try:
                    return await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    # asyncio.wait_for cancels the underlying task, so no work leaks.
                    raise ToolTimeoutError(
                        tool_name=getattr(fn, "__name__", repr(fn)),
                        timeout_seconds=timeout_seconds,
                        background_work_may_continue=False,
                    )
            return _async_wrapped

        @functools.wraps(fn)
        def _sync_wrapped(*args, **kwargs):
            executor = executor_factory()
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                # Best-effort cancel; only effective if the future has not started.
                # A started sync call cannot be interrupted, so warn operators that
                # the worker may keep running (and its side effects may still occur).
                cancelled = future.cancel()
                if not cancelled and on_leaked is not None:
                    # The worker is stuck and OS-owned; let the generator recycle
                    # the pool so new submissions are not permanently queued behind
                    # leaked threads.
                    on_leaked()
                logger.warning(
                    "Tool %r exceeded %.1fs (cancel=%s); worker may continue "
                    "executing in the background.",
                    getattr(fn, "__name__", repr(fn)),
                    timeout_seconds, cancelled,
                )
                raise ToolTimeoutError(
                    tool_name=getattr(fn, "__name__", repr(fn)),
                    timeout_seconds=timeout_seconds,
                    background_work_may_continue=not cancelled,
                )
        return _sync_wrapped

    # Framework tool object (CrewAI/LangChain BaseTool, praisonai @tool). These
    # carry name / description / args_schema that the downstream framework needs
    # to advertise the tool to the LLM. Replacing them with a bare function
    # (functools.wraps copies only __name__/__doc__ etc., NOT args_schema) makes
    # the framework infer a (*args, **kwargs) schema and the LLM emits malformed
    # tool_calls. Instead, wrap only the execution method IN PLACE so the object
    # — and its schema — survive.
    if not callable(tool) or _looks_like_framework_tool(tool):
        # Idempotency guard for shared framework tool objects (cached by
        # ToolResolver / passed via plugin registries). If this generator already
        # wrapped the object, its proxy is stamped with our owner key — return it
        # unchanged so re-wrapping on every generate_crew_and_kickoff() does not
        # rebuild proxies. A proxy owned by a *different* generator is unwrapped
        # back to the shared inner object and re-wrapped here, so this generator's
        # calls always bind to its own executor/timeout (never a foreign pool
        # that may already be shut down). Compare by value, not identity: a stale
        # ``is`` check against uuids/ints could silently never match.
        existing_owner = getattr(tool, _TIMEOUT_MARKER, None)
        if isinstance(tool, _TimeoutBoundTool) and existing_owner == _owner_key:
            return tool
        inner = getattr(tool, _TIMEOUT_ORIGINAL, tool)

        wrapped_methods = {}
        for method_name in ("_run", "run"):
            method = getattr(inner, method_name, None)
            if callable(method):
                wrapped = _wrap_callable(method)
                if wrapped is not method:
                    wrapped_methods[method_name] = wrapped

        if wrapped_methods:
            # Build a fresh per-generator proxy; the shared inner object is never
            # mutated, so cross-generator contamination is impossible. The proxy
            # subclasses ``type(inner)`` so ``isinstance(proxy, BaseTool)`` still
            # holds for downstream executors.
            proxy = _make_timeout_proxy(
                inner,
                wrapped_run=wrapped_methods.get("run"),
                wrapped__run=wrapped_methods.get("_run"),
            )
            object.__setattr__(proxy, _TIMEOUT_MARKER, _owner_key)
            object.__setattr__(proxy, _TIMEOUT_ORIGINAL, inner)
            return proxy

        # No patchable execution method or non-callable object; return as-is so
        # we never silently drop a tool object we couldn't safely wrap.
        if not callable(tool):
            return tool

    # Plain callable — safe to wrap as a function. If it is already wrapped by
    # this same owner, return as-is (idempotent). A callable already owned by a
    # *different* generator is left untouched: it is a fresh per-generator
    # wrapper object here (not shared in place), so we never stack wrappers.
    if getattr(tool, _TIMEOUT_MARKER, None) is not None:
        return tool
    wrapped = _wrap_callable(tool)
    if wrapped is not tool:
        try:
            setattr(wrapped, _TIMEOUT_MARKER, _owner_key)
            setattr(wrapped, _TIMEOUT_ORIGINAL, tool)
        except (AttributeError, TypeError):
            pass
    return wrapped


def _resolve_yaml_cli_backend(cli_backend_config, logger):
    """Resolve a YAML ``cli_backend`` field to a CliBackendProtocol instance."""
    if cli_backend_config is None:
        return None
    try:
        from praisonai.cli_backends import resolve_cli_backend_config
        return resolve_cli_backend_config(cli_backend_config)
    except (ImportError, ValueError, TypeError) as exc:
        logger.warning("Failed to resolve cli_backend %r: %s", cli_backend_config, exc)
        return None


class AgentsGenerator:
    def __init__(self, agent_file, framework, config_list, log_level=None, agent_callback=None, task_callback=None, agent_yaml=None, tools=None, cli_config=None, adapter_registry=None, tool_timeout_executor=None, tool_resolver=None, adapter=None):
        """
        Initialize the AgentsGenerator object.

        Parameters:
            agent_file (str): The path to the agent file.
            framework (str): The framework to be used for the agents.
            config_list (list): A list of configurations for the agents.
            log_level (int, optional): The logging level to use. Defaults to logging.INFO.
            agent_callback (callable, optional): A callback function to be executed after each agent step.
            task_callback (callable, optional): A callback function to be executed after each tool run.
            agent_yaml (str, optional): The content of the YAML file. Defaults to None.
            tools (dict, optional): A dictionary containing the tools to be used for the agents. Defaults to None.
            cli_config (dict, optional): CLI configuration to override YAML settings. Defaults to None.
            adapter_registry (FrameworkAdapterRegistry, optional): Registry for framework adapters. Defaults to process default.
            tool_resolver (ToolResolver, optional): Canonical tool resolver. Defaults to the shared context-local resolver so discovery runs once per run.

        Attributes:
            agent_file (str): The path to the agent file.
            framework (str): The framework to be used for the agents.
            config_list (list): A list of configurations for the agents.
            log_level (int): The logging level to use.
            agent_callback (callable, optional): A callback function to be executed after each agent step.
            task_callback (callable, optional): A callback function to be executed after each tool run.
            tools (dict): A dictionary containing the tools to be used for the agents.
        """
        self.agent_file = agent_file
        self.framework = framework
        self.config_list = config_list
        self.log_level = log_level
        self.agent_callback = agent_callback
        self.task_callback = task_callback
        self.agent_yaml = agent_yaml
        self.tools = tools or []  # Store tool class names as a list
        self.cli_config = cli_config or {}  # Store CLI configuration overrides
        # Use namespaced logger - no hot-path basicConfig calls
        from ._logging import get_logger
        self.logger = get_logger("agents_generator")
        
        # Set level if provided, but don't mutate root logger
        if log_level:
            if isinstance(log_level, str):
                self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
            else:
                self.logger.setLevel(log_level)
        elif os.environ.get('LOGLEVEL'):
            self.logger.setLevel(getattr(logging, os.environ.get('LOGLEVEL', 'INFO').upper(), logging.INFO))
        
        # Initialize tool resolver (single source of truth for tool resolution).
        # DI-friendly: callers (e.g. AutoGenerator hand-off, tests) may pass a
        # resolver; otherwise share the context-local default so tool discovery
        # runs once per run instead of once per generator construction.
        if tool_resolver is None:
            from .tool_resolver import _get_default_resolver
            tool_resolver = _get_default_resolver()
        self.tool_resolver = tool_resolver
        
        # DI-friendly: tests/multi-tenant runtimes pass their own registry;
        # CLI users get the process default.
        self._adapter_registry = adapter_registry or _get_default_adapter_registry()

        # Optional pre-resolved adapter handed down from the entry point so the
        # winning adapter from pick_default() is not constructed (and re-validated)
        # a second time on the hot path. Reused only when the requested framework
        # matches; otherwise we fall back to registry.create().
        self._adapter = adapter

        # Instance-owned tool-timeout executor so multi-tenant runtimes can scope
        # it per session (no process-wide singleton). Created lazily on first use
        # to avoid spawning threads for generators that never time a sync tool.
        # A caller-supplied executor is treated as borrowed and never shut down.
        self._tool_timeout_executor = tool_timeout_executor
        self._owns_tool_timeout_executor = tool_timeout_executor is None
        self._tool_timeout_executor_lock = threading.Lock()
        # Track workers permanently held by stuck sync tools. Once half the pool
        # is leaked we recycle it so new tool calls aren't starved forever.
        self._leaked_workers = 0
        self._max_leaked_workers = max(1, _resolve_tool_timeout_workers() // 2)
        # Stable per-generator identity for timeout-wrapper ownership. A bound
        # method (self._get_tool_timeout_executor) yields a fresh object with a
        # different id() on every access, so it cannot be used as a reliable
        # owner key; a uuid pinned at construction can.
        self._timeout_owner_key = uuid.uuid4()
        
        # Defer framework adapter creation until YAML is loaded
        # This fixes the issue where empty framework string fails before YAML framework is read
        self.framework_adapter = None

    def _get_tool_timeout_executor(self):
        """Lazily create this generator's bounded sync-tool-timeout thread pool.

        The pool is owned by the instance (not a module global), so concurrent
        sessions / tenants never share workers and a stuck tool in one session
        cannot starve another. If enough workers have leaked to stuck tools, the
        pool is recycled: leaked threads keep running until their syscall returns,
        but new submissions get a fresh set of workers instead of queuing behind
        the dead ones forever.
        """
        import concurrent.futures

        with self._tool_timeout_executor_lock:
            recycle = (
                self._owns_tool_timeout_executor
                and self._tool_timeout_executor is not None
                and self._leaked_workers >= self._max_leaked_workers
            )
            if recycle:
                self._tool_timeout_executor.shutdown(wait=False, cancel_futures=True)
                self._tool_timeout_executor = None
                self._leaked_workers = 0
            if self._tool_timeout_executor is None:
                # Resolve once so the pool size and the leak threshold that
                # governs its recycling always agree, even if the env var was
                # changed between construction and (re)creation.
                workers = _resolve_tool_timeout_workers()
                self._tool_timeout_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix=f"praisonai-tool-timeout-{id(self):x}",
                )
                self._max_leaked_workers = max(1, workers // 2)
                self._owns_tool_timeout_executor = True
            # Capture the reference inside the lock so a concurrent close() can
            # never null the attribute out between the check and the return.
            return self._tool_timeout_executor

    def _note_leaked_worker(self):
        """Record a worker permanently held by a stuck sync tool."""
        with self._tool_timeout_executor_lock:
            self._leaked_workers += 1

    def _wrap_tool_with_timeout(self, tool, timeout_seconds):
        """Wrap a tool with this generator's instance-owned timeout executor."""
        return _wrap_with_timeout(
            tool,
            timeout_seconds,
            self._get_tool_timeout_executor,
            on_leaked=self._note_leaked_worker,
            owner_key=self._timeout_owner_key,
        )

    def close(self):
        """Release the owned tool-timeout executor; safe to call repeatedly."""
        with self._tool_timeout_executor_lock:
            if self._owns_tool_timeout_executor and self._tool_timeout_executor is not None:
                self._tool_timeout_executor.shutdown(wait=False, cancel_futures=True)
                self._tool_timeout_executor = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def _get_framework_adapter(self, framework: str) -> "FrameworkAdapter":
        """
        Get the appropriate framework adapter for the given framework.
        
        Args:
            framework: Name of the framework
            
        Returns:
            Framework adapter instance
            
        Raises:
            ValueError: If framework is not supported
        """
        # Reuse the pre-resolved adapter from the entry point when it matches the
        # requested framework, avoiding a second construction + protocol
        # re-validation on the hot path.
        injected = getattr(self, "_adapter", None)
        if injected is not None and getattr(injected, "name", None) == framework:
            return injected
        return self._adapter_registry.create(framework)

    def _merge_cli_config(self, config, cli_config):
        """
        Merge CLI configuration with YAML configuration.
        
        CLI configuration takes precedence over YAML configuration for:
        - Global config fields (acp, lsp) -> config.config
        - Agent-level fields (trust, tool_timeout, planning_tools, autonomy, guardrail, approval) -> applied to all agents
        
        Args:
            config (dict): The parsed YAML configuration
            cli_config (dict): The CLI configuration to merge
        """
        self.logger.debug(f"Merging CLI config: {cli_config}")
        
        # Handle global config overrides (acp, lsp)
        if 'acp' in cli_config or 'lsp' in cli_config:
            if 'config' not in config:
                config['config'] = {}
            
            if 'acp' in cli_config:
                config['config']['acp'] = cli_config['acp']
                self.logger.debug(f"CLI override: acp = {cli_config['acp']}")
            
            if 'lsp' in cli_config:
                config['config']['lsp'] = cli_config['lsp'] 
                self.logger.debug(f"CLI override: lsp = {cli_config['lsp']}")

        # Handle workflow input/topic override. A caller-supplied prompt (e.g.
        # the Jobs API ``job.prompt`` or the serve HTTP ``query``) is the input
        # for this run and must drive the workflow topic instead of being
        # dropped. Only override when a non-empty value is provided so a static
        # YAML ``input``/``topic`` is preserved when no per-run prompt is given.
        for _key in ('input', 'topic'):
            _val = cli_config.get(_key)
            if _val:
                config['input'] = _val
                config.pop('topic', None)
                self.logger.debug(f"CLI override: {_key} = {_val}")
                break

        # Handle agent-level overrides using unified approach
        agent_level_fields = ['tool_timeout', 'tool_retry_policy', 'planning_tools', 'autonomy', 'planning', 'web', 'web_fetch']
        agent_overrides = {k: v for k, v in cli_config.items() if k in agent_level_fields}

        if "tool_retry_policy" in agent_overrides:
            policy = agent_overrides["tool_retry_policy"]
            try:
                from praisonaiagents.tools.retry import RetryPolicy

                if isinstance(policy, RetryPolicy):
                    agent_overrides["tool_retry_policy"] = {
                        "max_attempts": policy.max_attempts,
                        "delay": policy.initial_delay_ms / 1000.0,
                        "backoff_factor": policy.backoff_factor,
                        "max_delay": policy.max_delay_ms / 1000.0,
                    }
            except ImportError as exc:
                # The optional retry backend is missing. The CLI accepted
                # --tool-retry-* flags, so surface a warning instead of
                # silently telling the user their settings were honoured.
                self.logger.warning(
                    "tool_retry_policy requested but retry backend unavailable: %r",
                    exc,
                )
        
        # Handle handoff configuration - convert CLI flags into handoff dict
        handoff_fields = ['handoff', 'handoff_policy', 'handoff_timeout', 'handoff_max_depth', 'handoff_max_concurrent', 'handoff_detect_cycles']
        if any(field in cli_config for field in handoff_fields):
            handoff_config = {}
            if 'handoff' in cli_config:
                # Convert comma-separated roles to list
                handoff_roles = [role.strip() for role in cli_config['handoff'].split(',') if role.strip()]
                handoff_config['to'] = handoff_roles
            if 'handoff_policy' in cli_config:
                handoff_config['policy'] = cli_config['handoff_policy']
            if 'handoff_timeout' in cli_config:
                handoff_config['timeout'] = cli_config['handoff_timeout']
            if 'handoff_max_depth' in cli_config:
                handoff_config['max_depth'] = cli_config['handoff_max_depth']
            if 'handoff_max_concurrent' in cli_config:
                handoff_config['max_concurrent'] = cli_config['handoff_max_concurrent']
            if 'handoff_detect_cycles' in cli_config:
                handoff_config['detect_cycles'] = cli_config['handoff_detect_cycles'].lower() == 'true'
            
            if handoff_config:
                agent_overrides['handoff'] = handoff_config
        
        # Handle approval configuration using unified spec
        approval_fields = ['trust', 'approval', 'approve_all_tools', 'approval_timeout', 'approve_level']
        if any(field in cli_config for field in approval_fields):
            from ._approval_spec import ApprovalSpec
            
            # Create a mock args object for CLI parsing
            class MockArgs:
                def __init__(self, cli_config):
                    for field in approval_fields:
                        setattr(self, field, cli_config.get(field))
                    self.guardrail = cli_config.get('guardrail')
            
            spec = ApprovalSpec.from_cli(MockArgs(cli_config))
            if spec.enabled:
                agent_overrides['approval'] = spec.to_dict()
            
        # Handle guardrail separately
        if 'guardrail' in cli_config:
            agent_overrides['guardrails'] = cli_config['guardrail']
        
        if agent_overrides:
            # Apply to all agents in the config
            roles = config.get('roles', {})
            agents = config.get('agents', {})
            
            # Apply to 'roles' section (canonical format)
            for role_name, role_config in roles.items():
                for field, value in agent_overrides.items():
                    role_config[field] = value
                    self.logger.debug(f"CLI override for role {role_name}: {field} = {value}")
            
            # Apply to 'agents' section (backward compatibility)
            for agent_name, agent_config in agents.items():
                for field, value in agent_overrides.items():
                    agent_config[field] = value
                    self.logger.debug(f"CLI override for agent {agent_name}: {field} = {value}")

    def _prepare_for_run(self, config):
        """
        Single source of truth for YAML normalisation, validation,
        CLI-backend compatibility, tool resolution, AutoGen version
        selection, and adapter resolution. Used by BOTH sync and async.
        """
        # Canonical format conversion: 'agents' -> 'roles', 'instructions' -> 'backstory'
        if 'agents' in config and 'roles' not in config:
            config['roles'] = {}
            for agent_name, agent_config in config['agents'].items():
                role_config = dict(agent_config) if agent_config else {}
                # Convert 'instructions' to 'backstory' if present
                if 'instructions' in role_config and 'backstory' not in role_config:
                    role_config['backstory'] = role_config['instructions']
                # Ensure required fields have defaults
                if 'role' not in role_config:
                    role_config['role'] = agent_name.replace('_', ' ').title()
                if 'goal' not in role_config:
                    role_config['goal'] = role_config.get('backstory', 'Complete the assigned task')
                if 'backstory' not in role_config:
                    role_config['backstory'] = f'You are a {role_config["role"]}'
                config['roles'][agent_name] = role_config

        # Get workflow input: 'input' is canonical, 'topic' is alias for backward compatibility
        topic = config.get('input', config.get('topic', ''))
        
        # Validate agents configuration for typos in field names
        self._validate_agents_config(config)
        
        # Build tools dictionary using shared logic
        tools_dict = self._build_tools_dict(config)
        
        # Select framework and resolve adapter variant
        framework_name = self.framework or config.get('framework', 'praisonai')
        adapter = self._select_framework(framework_name, config)
        
        # Validate framework availability through the injected registry so a
        # scoped/per-tenant adapter registered on this generator's registry is
        # not rejected just because it is absent from the process default.
        from .framework_adapters.validators import assert_framework_available
        assert_framework_available(adapter.name, registry=self._adapter_registry)
        
        # Validate cli_backend compatibility
        self._validate_cli_backend_compatibility(config, adapter.name, adapter=adapter)

        # Update framework reference if resolution changed it
        self.framework = adapter.name
        self.framework_adapter = adapter

        # NB: adapter setup is intentionally NOT run here. The caller opens the
        # observability_session (which owns init/finalize for every adapter) and
        # then invokes _run_adapter_setup INSIDE that session, so setup events —
        # and any setup/import failure — are recorded and finalized instead of
        # slipping outside observability. See generate_crew_and_kickoff /
        # agenerate_crew_and_kickoff.
        return {
            'adapter': adapter,
            'config': config,
            'topic': topic,
            'tools_dict': tools_dict,
        }

    def _run_adapter_setup(self, adapter):
        """Run an adapter's setup hooks.

        Kept as a tiny seam so both the sync and async run paths execute setup
        *inside* the observability_session, keeping init/setup/run/finalize
        bracketed together for every adapter.
        """
        adapter.setup(framework_tag=adapter.name)
    
    def _build_tools_dict(self, config):
        """Shared tool resolution logic for sync and async paths."""
        tools_dict = self.tool_resolver.resolve_all_from_yaml(config)
        for tool_class in self.tools:
            if isinstance(tool_class, type):
                try:
                    tools_dict[tool_class.__name__] = tool_class()
                except (TypeError, ValueError, RuntimeError) as e:
                    self.logger.warning(f"Failed to instantiate tool class {tool_class.__name__}: {e}")

        # Enforce tool_timeout from CLI/YAML at the wrapper layer so the field is
        # not silently dropped. The timeout stack (_wrap_tool_with_timeout) is
        # framework-agnostic and works for both the native and external adapters.
        # Determine whether a single uniform timeout applies to every agent, or
        # whether agents declared *heterogeneous* per-agent budgets. A uniform
        # value can still be wrapped once onto the shared dict (cheapest path);
        # heterogeneous values must be wrapped per-agent so a documented
        # per-agent ``tool_timeout`` is honoured instead of being silently
        # downgraded to the tightest value for the whole run.
        # The uniform and per-agent paths are mutually exclusive. Always resolve
        # BOTH internal keys on every call (setting the inactive one to None) so
        # that when the *same* generator instance is reused with a different
        # timeout layout, a stale closure from a previous run can never leak into
        # the adapters and apply the wrong budget to the current run.
        uniform = self._resolve_uniform_tool_timeout(config)
        wrap = None
        resolver = None
        if uniform and uniform > 0:
            wrap = lambda t, _sec=uniform: self._wrap_tool_with_timeout(t, _sec)
            tools_dict = {name: wrap(tool) for name, tool in tools_dict.items()}
        else:
            # No single uniform timeout. If any agent declared a per-agent
            # tool_timeout, expose a resolver so adapters wrap each agent's tools
            # with that agent's own budget (tools stay shared; only the guard
            # closure differs). Falls back to no wrap for agents without one.
            resolver = self.make_agent_tool_wrap_resolver(config)

        # Expose the per-run wrap so adapters that inject *more* tools after this
        # point (e.g. PraisonAIAdapter's ACP/LSP centric tools) apply the same
        # timeout guard instead of silently bypassing it; expose the per-agent
        # resolver for heterogeneous budgets. Both keys are written every time so
        # the inactive path is cleared rather than left holding a prior closure.
        self.cli_config = {
            **(self.cli_config or {}),
            "_tool_timeout_wrap": wrap,
            "_agent_tool_wrap_resolver": resolver,
        }
        return tools_dict

    def _resolve_effective_tool_timeout(self, config):
        """Resolve the effective per-tool timeout in seconds.

        Precedence: an explicit CLI ``tool_timeout`` wins; otherwise the tightest
        (smallest) ``tool_timeout`` declared on any role/agent is applied to the
        shared tool dict. The tightest value is the safe-by-default choice for a
        multi-agent run: an agent that asked to bail out quickly is never forced
        to wait for another agent's larger budget. Any agent whose declared value
        is overridden is warned about so the collapse is never silent. Returns
        ``None`` when nothing declares a timeout.
        """
        cli_timeout = (self.cli_config or {}).get("tool_timeout")
        if isinstance(cli_timeout, (int, float)) and not isinstance(cli_timeout, bool):
            return float(cli_timeout)

        entities = {**(config.get("roles") or {}), **(config.get("agents") or {})}

        def _declared(entity):
            v = entity.get("tool_timeout") if isinstance(entity, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
            return None

        timeouts = [v for v in (_declared(e) for e in entities.values()) if v is not None]
        if not timeouts:
            return None

        tightest = float(min(timeouts))
        for name, entity in entities.items():
            v = _declared(entity)
            if v is not None and float(v) != tightest:
                self.logger.warning(
                    "Agent %r declared tool_timeout=%s but a shared tool dict "
                    "forces the tightest value %ss for the whole run.",
                    name, v, tightest,
                )
        return tightest

    @staticmethod
    def _declared_agent_timeout(entity):
        """Return a positive numeric ``tool_timeout`` declared on an entity, else None."""
        v = entity.get("tool_timeout") if isinstance(entity, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        return None

    def _resolve_uniform_tool_timeout(self, config):
        """Return a single timeout to wrap every tool with, or ``None``.

        A uniform value exists when the CLI sets ``tool_timeout`` (applies to all
        agents), or when *every* agent/role declares ``tool_timeout`` and they
        all declare the *same* value. If any agent omits ``tool_timeout``, or
        declared values differ, returns ``None`` so the shared dict stays
        unwrapped and the per-agent resolver becomes the sole guard — this
        avoids both the old "tightest wins for everyone" downgrade and forcing a
        lone declared budget onto agents that never asked for one (greptile P1).
        """
        cli_timeout = (self.cli_config or {}).get("tool_timeout")
        if isinstance(cli_timeout, (int, float)) and not isinstance(cli_timeout, bool):
            return float(cli_timeout)

        entities = {**(config.get("roles") or {}), **(config.get("agents") or {})}
        if not entities:
            return None

        values = set()
        for entity in entities.values():
            t = self._declared_agent_timeout(entity)
            if t is None:
                # An agent without a declared budget must not inherit another
                # agent's timeout via the shared-dict wrap. Defer entirely to the
                # per-agent resolver.
                return None
            values.add(t)
        if len(values) == 1:
            return next(iter(values))
        return None

    def resolve_agent_tool_timeout(self, agent_key, config):
        """Per-agent effective timeout: agent value > CLI value > ``None``.

        Never downgrades across agents — each agent gets its own declared budget
        (or the CLI default, or nothing).
        """
        entities = {**(config.get("roles") or {}), **(config.get("agents") or {})}
        val = self._declared_agent_timeout(entities.get(agent_key) or {})
        if val is not None:
            return val
        cli_timeout = (self.cli_config or {}).get("tool_timeout")
        if isinstance(cli_timeout, (int, float)) and not isinstance(cli_timeout, bool):
            return float(cli_timeout)
        return None

    def make_agent_tool_wrap_resolver(self, config):
        """Return ``resolver(agent_key) -> wrap|None`` for heterogeneous budgets.

        Returns ``None`` when no agent declares a per-agent ``tool_timeout`` (so
        adapters skip per-agent wrapping entirely). The returned ``wrap`` closes
        over that agent's timeout; tool objects stay shared, only the guard
        closure differs per agent.
        """
        entities = {**(config.get("roles") or {}), **(config.get("agents") or {})}
        declared_any = any(
            self._declared_agent_timeout(e) is not None for e in entities.values()
        )
        if not declared_any:
            return None

        def resolver(agent_key):
            t = self.resolve_agent_tool_timeout(agent_key, config)
            if not t or t <= 0:
                return None
            return lambda tool, _sec=t: self._wrap_tool_with_timeout(tool, _sec)

        return resolver

    # Mirror the legacy CLI's --tool-timeout argparse default so the workflow
    # validation can tell an implicit default apart from a user request.
    _CLI_TOOL_TIMEOUT_DEFAULT = 60

    def _resolve_explicit_workflow_tool_timeout(self, config):
        """Resolve a tool_timeout the user *explicitly* requested, else ``None``.

        The workflow path cannot enforce per-tool timeouts, so it fails fast on
        a requested one. But the legacy CLI always injects its --tool-timeout
        argparse default into ``cli_config`` (see direct_prompt.py), so a plain
        ``_resolve_effective_tool_timeout`` would flag every ordinary workflow
        run. Here a per-agent/role YAML timeout always counts as explicit; a CLI
        value only counts when the user actually changed it away from the bare
        argparse default. The per-agent/role resolution is delegated to
        ``_resolve_effective_tool_timeout`` so both paths share one source of
        truth and its override warnings still fire.
        """
        # A per-agent/role YAML timeout is always an explicit request. Resolve it
        # from config alone (ignoring the always-injected CLI default) via the
        # shared effective resolver, so the tightest-value warning still fires.
        cli_timeout = (self.cli_config or {}).get("tool_timeout")
        cli_changed = (
            isinstance(cli_timeout, (int, float))
            and not isinstance(cli_timeout, bool)
            and float(cli_timeout) != float(self._CLI_TOOL_TIMEOUT_DEFAULT)
        )
        if cli_changed:
            return float(cli_timeout)

        # No user-changed CLI value: fall back to a YAML-declared timeout, if any.
        # Temporarily mask the injected CLI default so the effective resolver
        # reports only what the YAML declared.
        saved_cli_config = self.cli_config
        try:
            if isinstance(self.cli_config, dict) and "tool_timeout" in self.cli_config:
                self.cli_config = {
                    k: v for k, v in self.cli_config.items() if k != "tool_timeout"
                }
            declared = self._resolve_effective_tool_timeout(config)
        finally:
            self.cli_config = saved_cli_config
        if declared and declared > 0:
            return float(declared)
        return None
    
    def _select_framework(self, framework: str, config: Dict[str, Any]) -> Any:
        """Select and resolve the appropriate framework adapter.
        
        Args:
            framework: The base framework name (e.g., "autogen", "crewai")
            config: Framework configuration
            
        Returns:
            The resolved FrameworkAdapter instance
        """
        # Get the base adapter
        adapter = self._get_framework_adapter(framework)
        
        # Let the adapter resolve its own variant using the standardized resolve() method
        # This replaces the old resolve_variant approach and follows the Protocol
        resolved_adapter = adapter.resolve(config=config)
        
        return resolved_adapter
    
    def _validate_cli_backend_compatibility(self, config, framework, *, adapter=None):
        """Validate that cli_backend and runtime are only used with compatible frameworks."""
        # Check if any agent/role defines cli_backend or runtime
        all_entities = {
            **(config.get('roles') or {}),
            **(config.get('agents') or {}),
        }
        
        has_cli_backend = any(
            isinstance(details, dict) and details.get('cli_backend')
            for details in all_entities.values()
        )
        
        has_runtime = any(
            isinstance(details, dict) and details.get('runtime')
            for details in all_entities.values()
        )
        
        # Check for model-scoped runtime in models section
        has_model_runtime = False
        models_config = config.get('models', {})
        if isinstance(models_config, dict):
            has_model_runtime = any(
                isinstance(model_config, dict) and model_config.get('runtime')
                for model_config in models_config.values()
            )
        
        # Check for provider-scoped runtime in providers section
        has_provider_runtime = False
        providers_config = config.get('providers', {})
        if isinstance(providers_config, dict):
            has_provider_runtime = any(
                isinstance(provider_config, dict) and provider_config.get('runtime_default')
                for provider_config in providers_config.values()
            )
        
        # Ask the adapter whether it supports runtime features instead of
        # hardcoding a framework-name check. Third-party adapters can opt in by
        # setting ``SUPPORTS_RUNTIME_FEATURES = True``.
        supports_runtime_features: Optional[bool]
        if adapter is not None:
            # A concrete adapter object was supplied: read its flag directly.
            supports_runtime_features = bool(
                getattr(adapter, "SUPPORTS_RUNTIME_FEATURES", False)
            )
        else:
            # Only a name was supplied: resolve the capability through the
            # protocol (memoised) rather than voting for "praisonai" by name.
            from .framework_adapters.registry import (
                adapter_capability,
                get_default_registry,
            )
            _registry = getattr(self, "_adapter_registry", None) or get_default_registry()
            supports_runtime_features = adapter_capability(
                str(framework),
                "SUPPORTS_RUNTIME_FEATURES",
                registry=_registry,
            )
            if supports_runtime_features is None:
                # ``None`` means "couldn't construct the adapter". Distinguish a
                # KNOWN framework whose optional dependency/entry point merely
                # isn't installed (e.g. ``autogen``/``crewai``) from a genuinely
                # unknown name. A known built-in that can't be constructed still
                # cannot support praisonai-specific runtime features, so treat it
                # as unsupported (historical behaviour); only a name neither
                # registered nor a known built-in triggers the "cannot verify"
                # refusal below. ``DEFAULT_PRIORITY`` is the canonical built-in
                # set and is resolvable even in a source checkout where the
                # entry-point registrations aren't installed.
                known = set(getattr(type(_registry), "DEFAULT_PRIORITY", ()))
                try:
                    known |= set(_registry.list_names())
                except Exception:  # noqa: BLE001 -- registry probe must not crash validation
                    pass
                if str(framework).lower() in {n.lower() for n in known}:
                    supports_runtime_features = False

        uses_runtime_features = (
            has_cli_backend or has_runtime or has_model_runtime or has_provider_runtime
        )

        if uses_runtime_features and supports_runtime_features is None:
            # The name is not a registered adapter at all, so we cannot verify the
            # capability. Refuse instead of silently downgrading an unknown
            # third-party adapter to unsupported by a hardcoded name check.
            raise ValueError(
                f"Cannot verify runtime-feature support for framework='{framework}': "
                "the adapter is not resolvable. Install its extra or register it via "
                "the 'praisonai.framework_adapters' entry-point group."
            )

        if uses_runtime_features and not supports_runtime_features:
            runtime_features = []
            if has_cli_backend:
                runtime_features.append('cli_backend')
            if has_runtime:
                runtime_features.append('runtime')
            if has_model_runtime:
                runtime_features.append('models.*.runtime')
            if has_provider_runtime:
                runtime_features.append('providers.*.runtime_default')
            
            features_str = ', '.join(runtime_features)
            logger = getattr(self, "logger", None)
            if logger is not None:
                logger.error(
                    f"Runtime features ({features_str}) are not supported for framework='{framework}'. "
                    f"Remove these fields from your YAML or switch to a framework whose adapter "
                    f"sets SUPPORTS_RUNTIME_FEATURES = True (e.g. framework='praisonai')."
                )
            raise ValueError(
                f"Runtime features ({features_str}) are not supported for framework='{framework}'. "
                f"Use a framework whose adapter sets SUPPORTS_RUNTIME_FEATURES = True "
                f"(e.g. framework='praisonai')."
            )

    def _validate_agents_config(self, config):
        """
        Validate agent configuration with fail-fast validation and aggregated errors.
        
        Args:
            config (dict): The parsed YAML configuration
            
        Raises:
            ValueError: If configuration has validation errors
        """
        # Use the new comprehensive validator
        from .config.validator import ConfigValidator
        
        # Use existing tool resolver if available
        validator = ConfigValidator(tool_resolver=self.tool_resolver)
        
        # Check for strict mode from environment or config
        import os
        strict_mode = os.getenv('PRAISONAI_VALIDATE_STRICT', 'false').lower() == 'true'
        
        # Validate configuration
        result = validator.validate_config(config, strict=strict_mode)
        
        # Log warnings
        for warning in result.warnings:
            self.logger.warning(warning)
        
        # If there are errors, fail fast with aggregated error message
        if not result.valid:
            error_msg = f"Configuration validation failed with {len(result.errors)} error(s):\n"
            for i, error in enumerate(result.errors, 1):
                error_msg += f"  {i}. {error}\n"
            
            # Include warnings if any
            if result.warnings:
                error_msg += f"\nAdditionally, there are {len(result.warnings)} warning(s):\n"
                for i, warning in enumerate(result.warnings, 1):
                    error_msg += f"  {i}. {warning}\n"
            
            self.logger.error(error_msg)
            raise ValueError(error_msg)



    def _load_config(self):
        """Load configuration from agent file or agent_yaml."""
        if self.agent_yaml:
            config = _yaml_safe_load(self.agent_yaml)
        else:
            if self.agent_file in ('/app/api:app', 'api:app'):
                self.agent_file = 'agents.yaml'
            # Let FileNotFoundError surface so the Python API, HTTP handlers,
            # and tests can distinguish "no such file" from "no result".
            # Downgrading it to a print (returning None) made every public
            # entry point return a silent None for a missing file.
            with open(self.agent_file, 'r') as f:
                config = _yaml_safe_load(f)

        config = _normalize_yaml_config(config or {})

        # Apply CLI config overrides to both paths (agent_yaml and agent_file)
        if self.cli_config:
            self._merge_cli_config(config, self.cli_config)
        return config

    def _is_workflow_yaml(self, config):
        """Check if configuration is workflow mode YAML."""
        process_type = config.get('process', 'sequential')
        has_steps = 'steps' in config
        has_workflow_config = 'workflow' in config
        workflow_type = config.get('type')
        return (
            process_type == 'workflow'
            or (has_steps and has_workflow_config)
            or workflow_type in {'job', 'hybrid'}
        )

    def _validate_adapter_cli_capabilities(self, adapter) -> None:
        """Reject CLI modes an adapter would otherwise silently ignore."""
        cli_config = getattr(self, "cli_config", None) or {}
        adapter_name = getattr(adapter, "name", type(adapter).__name__)

        if cli_config.get("resume_session") and not getattr(
            adapter, "SUPPORTS_SESSION_CONTINUITY", False
        ):
            raise ValueError(
                "--resume / --session / --continue / --fork are not supported "
                f"by framework {adapter_name!r}. Use --framework praisonai or "
                "an adapter that declares SUPPORTS_SESSION_CONTINUITY = True."
            )

        output_mode = cli_config.get("output") or cli_config.get("output_format")
        if output_mode == "stream-json" and not getattr(
            adapter, "SUPPORTS_STREAM_BRIDGE", False
        ):
            raise ValueError(
                "--output stream-json is not supported by framework "
                f"{adapter_name!r}. Use --framework praisonai or an adapter "
                "that declares SUPPORTS_STREAM_BRIDGE = True."
            )

    def _validate_workflow_cli_capabilities(self) -> None:
        """Reject CLI modes the native workflow path would silently ignore.

        Workflow YAMLs run through the native ``YAMLWorkflowParser`` rather than
        ``PraisonAIAdapter.run``/``arun``, so session continuity and the
        ``stream-json`` bridge are not wired up. Fail fast instead of accepting
        the flags and ignoring them.
        """
        cli_config = getattr(self, "cli_config", None) or {}

        if cli_config.get("resume_session"):
            raise ValueError(
                "--resume / --session / --continue / --fork are not supported "
                "for workflow YAMLs. Session continuity is only available on "
                "the sequential/hierarchical praisonai path."
            )

        output_mode = cli_config.get("output") or cli_config.get("output_format")
        if output_mode == "stream-json":
            raise ValueError(
                "--output stream-json is not supported for workflow YAMLs. "
                "Use the sequential/hierarchical praisonai path for the "
                "stream-json bridge."
            )

    def generate_crew_and_kickoff(self):
        """
        Generates a crew of agents and initiates tasks based on the provided configuration.

        Parameters:
            agent_file (str): The path to the agent file.
            framework (str): The framework to be used for the agents.
            config_list (list): A list of configurations for the agents.

        Returns:
            str: The output of the tasks performed by the crew of agents.

        Raises:
            FileNotFoundError: If the specified agent file does not exist.

        This function first loads the agent configuration from the specified file. It then initializes the tools required for the agents based on the specified framework. If the specified framework is "autogen", it loads the LLM configuration dynamically and creates an AssistantAgent for each role in the configuration. It then adds tools to the agents if specified in the configuration. Finally, it prepares tasks for the agents based on the configuration and initiates the tasks using the crew of agents. If the specified framework is not "autogen", it creates a crew of agents and initiates tasks based on the configuration.
        """
        config = self._load_config()
        from .observability.hooks import observability_session
        if self._is_workflow_yaml(config):
            # Bracket the workflow run in the same observability session the
            # sequential/hierarchical path uses so AgentOps init/finalize fires
            # for workflow YAMLs too. Workflow YAMLs are native-only, so tag
            # them 'praisonai'.
            self._validate_workflow_cli_capabilities()
            with observability_session("praisonai"):
                return self._run_yaml_workflow(config)

        # Use shared preparation logic
        prep = self._prepare_for_run(config)
        self._validate_adapter_cli_capabilities(prep['adapter'])
        
        self.logger.info(f"Using framework: {prep['adapter'].name}")
        # Own the observability lifecycle here so init and finalize are always
        # paired for every adapter (the CM finalizes on success and error alike).
        with observability_session(prep['adapter'].name):
            # Run setup INSIDE the session so setup events and any setup/import
            # failure are recorded and finalized, not dropped outside observability.
            self._run_adapter_setup(prep['adapter'])
            return prep['adapter'].run(
                prep['config'],
                self.config_list,
                prep['topic'],
                tools_dict=prep['tools_dict'],
                agent_callback=getattr(self, 'agent_callback', None),
                task_callback=getattr(self, 'task_callback', None),
                cli_config=getattr(self, 'cli_config', None),
            )

    async def _aload_config(self):
        """Async-safe config loading (blocking file I/O off the event loop)."""
        import asyncio
        return await asyncio.to_thread(self._load_config)

    async def _aprepare_for_run(self, config):
        """Async-safe run preparation (heavy imports off the loop). Adapter setup
        runs later, inside the observability_session (see agenerate_crew_and_kickoff)."""
        import asyncio
        return await asyncio.to_thread(self._prepare_for_run, config)

    async def agenerate_crew_and_kickoff(self):
        """
        Async version of generate_crew_and_kickoff.
        Generates a crew of agents and initiates tasks based on the provided configuration.
        """
        config = await self._aload_config()
        import asyncio
        from .observability.hooks import observability_session
        if self._is_workflow_yaml(config):
            # Bracket the async workflow run in the same observability session
            # the sequential/hierarchical path uses so AgentOps init/finalize
            # fires for workflow YAMLs too. Workflow YAMLs are native-only, so
            # tag them 'praisonai'.
            self._validate_workflow_cli_capabilities()
            with observability_session("praisonai"):
                return await self._arun_yaml_workflow(config)

        # Use shared preparation logic (off the event loop to avoid blocking imports)
        prep = await self._aprepare_for_run(config)
        self._validate_adapter_cli_capabilities(prep['adapter'])
        
        self.logger.info(f"Using framework: {prep['adapter'].name}")
        # Own the observability lifecycle here so init and finalize are always
        # paired for every adapter (the CM finalizes on success and error alike).
        with observability_session(prep['adapter'].name):
            # Run setup INSIDE the session (off the event loop, as it may block)
            # so setup events and any setup/import failure are recorded and
            # finalized, not dropped outside observability.
            await asyncio.to_thread(self._run_adapter_setup, prep['adapter'])
            return await prep['adapter'].arun(
                prep['config'],
                self.config_list,
                prep['topic'],
                tools_dict=prep['tools_dict'],
                agent_callback=getattr(self, 'agent_callback', None),
                task_callback=getattr(self, 'task_callback', None),
                cli_config=getattr(self, 'cli_config', None),
            )


    def _build_yaml_workflow(self, config):
        """
        Single source of truth for YAML workflow preparation.

        Handles: praisonaiagents availability check, parser import guard,
        name defaulting, framework validation, default_llm merge, yaml.dump,
        and parser.parse_string. Returns the parsed workflow plus input data.

        Args:
            config (dict): The parsed YAML configuration

        Returns:
            Tuple[Any, Any]: (workflow, input_data)
        """
        if not is_available("praisonaiagents"):
            raise ImportError("PraisonAI is not installed. Please install it with 'pip install praisonaiagents'")

        try:
            from praisonaiagents.workflows import YAMLWorkflowParser
        except ImportError as err:
            raise ImportError("YAMLWorkflowParser not available. Please update praisonaiagents.") from err

        # Ensure name is present (YAMLWorkflowParser handles roles->agents conversion)
        if 'name' not in config:
            config['name'] = config.get('topic', 'Workflow')

        from .framework_adapters.workflow_framework import (
            framework_from_config,
            validate_workflow_framework,
        )
        # Validate the YAML-declared framework first so a non-native workflow
        # YAML (e.g. framework: crewai) can't slip through just because the
        # generator instance still holds the default 'praisonai'.
        workflow_framework = framework_from_config(config)
        validate_workflow_framework(
            workflow_framework,
            source="agents.yaml workflow section",
        )
        if self.framework:
            validate_workflow_framework(
                self.framework,
                source="AgentsGenerator framework",
            )

        # Parity with the sequential/hierarchical path: reject an incompatible
        # cli_backend in a workflow YAML at build time instead of accepting it
        # silently. Workflow YAMLs are native-only, so validate against
        # 'praisonai'.
        self._validate_cli_backend_compatibility(config, workflow_framework or 'praisonai')

        # The framework-level check above passes for 'praisonai' because the
        # sequential/hierarchical adapter does support cli_backend — but
        # workflow YAMLs run through YAMLWorkflowParser, which builds agents
        # natively and has no cli_backend wiring. Fail fast instead of
        # silently executing on the native LLM path with different tools,
        # credentials, and workspace behavior than the declared backend.
        workflow_entities = {
            **(config.get('roles') or {}),
            **(config.get('agents') or {}),
        }
        cli_backend_entities = sorted(
            name
            for name, details in workflow_entities.items()
            if isinstance(details, dict) and details.get('cli_backend')
        )
        if cli_backend_entities:
            raise ValueError(
                f"cli_backend (declared by: {', '.join(cli_backend_entities)}) is not "
                "supported for 'process: workflow' YAMLs; the workflow engine runs "
                "agents natively. Remove cli_backend or convert to a "
                "sequential/hierarchical process."
            )

        # tool_timeout is enforced by _wrap_tool_with_timeout on the
        # sequential/hierarchical path via tools_dict. The native workflow engine
        # resolves its own tools by name, so that wrapper hook does not apply
        # here. Fail fast rather than accepting the field and silently ignoring
        # it, mirroring _validate_workflow_cli_capabilities which already
        # refuses --resume/--session/--fork and --output stream-json on this
        # path. A warn-only no-op left the same CLI+YAML surface with silently
        # different execution semantics gated on the process: value.
        #
        # Only an *explicit* request is rejected: the legacy CLI always injects
        # its --tool-timeout argparse default (60) into cli_config, so treating
        # that implicit value as a user request would break every ordinary
        # workflow YAML run. We therefore ignore the bare CLI default and only
        # fail on a per-agent/role YAML tool_timeout or a CLI value the user
        # actually changed. The per-agent/role resolution is delegated to
        # _resolve_effective_tool_timeout so the sequential/hierarchical and
        # workflow paths share one source of truth.
        explicit_timeout = self._resolve_explicit_workflow_tool_timeout(config)
        if explicit_timeout and explicit_timeout > 0:
            raise ValueError(
                f"tool_timeout={explicit_timeout} is not supported for "
                "'process: workflow' YAMLs; per-tool timeouts are only enforced "
                "on the sequential/hierarchical path. Either remove tool_timeout "
                "or convert to a sequential/hierarchical process."
            )

        # Pass model from config_list to workflow as default_llm
        if self.config_list and self.config_list[0].get('model'):
            model_from_cli = self.config_list[0]['model']
            if 'workflow' not in config:
                config['workflow'] = {}
            if 'default_llm' not in config['workflow']:
                config['workflow']['default_llm'] = model_from_cli

        # Convert config back to YAML string for parser
        # Note: YAMLWorkflowParser handles 'roles' to 'agents' conversion internally
        import yaml as yaml_module
        yaml_content = yaml_module.dump(config, default_flow_style=False)

        parser = YAMLWorkflowParser()
        workflow = parser.parse_string(yaml_content)

        # Get input: 'input' is canonical, 'topic' is alias for backward compatibility
        input_data = config.get('input', config.get('topic', ''))

        return workflow, input_data

    @staticmethod
    def _finalise_workflow_result(result):
        """Normalize a workflow execution result into a string."""
        if result.get("status") == "completed":
            return result.get("output", "Workflow completed successfully")
        return f"Workflow failed: {result.get('error', 'Unknown error')}"

    async def _arun_yaml_workflow(self, config):
        """
        Async version of _run_yaml_workflow using YAMLWorkflowParser.

        This method handles agents.yaml files that have:
        - process: workflow

        Args:
            config: YAML configuration dictionary

        Returns:
            str: Workflow execution result
        """
        import asyncio
        workflow, input_data = await asyncio.to_thread(self._build_yaml_workflow, config)

        self.logger.info(f"Starting async YAML workflow with topic: {input_data}")

        if hasattr(workflow, 'astart'):
            result = await workflow.astart(input_data)
        else:
            result = await asyncio.to_thread(workflow.start, input_data)

        return self._finalise_workflow_result(result)

    def _run_yaml_workflow(self, config):
        """
        Run a YAML workflow using the YAMLWorkflowParser.

        This method handles agents.yaml files that have:
        - process: workflow
        - steps section with workflow patterns (route, parallel, loop, repeat)

        Args:
            config (dict): The parsed YAML configuration

        Returns:
            str: Result of the workflow execution
        """
        workflow, input_data = self._build_yaml_workflow(config)

        self.logger.debug(f"Running workflow: {workflow.name}")
        result = workflow.start(input_data)

        return self._finalise_workflow_result(result)


# Standalone function for backward compatibility with tests
def safe_format(template, **kwargs):
    """
    Safe string formatting that preserves JSON/dict literals while substituting variables.

    This function only substitutes placeholders that look like identifiers (e.g., {topic})
    while preserving JSON structures like {"level": 2}.

    Delegates to the single source of truth,
    ``BaseFrameworkAdapter._format_template`` in the core SDK, so the wrapper
    and core cannot drift (non-string short-circuit, regex, missing-key
    handling). ``_format_template`` is stateless; a fresh instance is free.

    Args:
        template (str): Template string with placeholders
        **kwargs: Values to substitute

    Returns:
        str: Formatted string with safe substitutions
    """
    from praisonaiagents.frameworks.base import BaseFrameworkAdapter
    return BaseFrameworkAdapter._format_template(
        BaseFrameworkAdapter(), template, **kwargs
    )

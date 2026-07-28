"""Bridge that lets model-generated code call registered tools (code mode).

This connects three pieces that already live in core but were not wired
together:

  * the in-process code executor (``tools/python_tools.py``)
  * the runtime tool registry (``tools/registry.py``)
  * the approval framework (``approval/__init__.py``)

When enabled, the sandbox namespace is populated with thin proxies for the
agent's *allowed* tools.  Each proxy call resolves the name against the
``ToolRegistry``, enforces an explicit per-run allow-list, passes through the
existing ``require_approval`` gate, runs the real tool, and returns the result
into the running script.  Only the script's stdout / return value flows back to
the model — intermediate tool results never enter the context window.

Safe by default: tools are callable from code only when the developer turns the
mode on and only for tools on the allow-list; every call still passes the
approval gate.

Security note: the proxy must never expose the underlying ``ToolRegistry`` or
the allow-list to sandboxed code.  Storing them as instance attributes is unsafe
because plain ``obj._registry`` attribute access bypasses ``__getattr__`` (the
attribute is found in ``__dict__`` first) and the sandbox's ``getattr`` guard
(direct attribute access compiles to ``LOAD_ATTR``, not a ``getattr`` call).  We
therefore keep all state in a closure that is unreachable from any attribute.
"""

from typing import Any, Callable, Dict, Iterable, Optional, Protocol, runtime_checkable

from .registry import ToolRegistry, get_registry


@runtime_checkable
class CodeToolBridge(Protocol):
    """Transport-agnostic contract for calling tools from *isolated* code.

    The in-process code executor injects :class:`ToolProxy` so a script can call
    tools directly.  When the script instead runs under real isolation (a
    subprocess/Docker/E2B/… sandbox) it cannot see the registry, so tool calls
    must cross a process boundary.  This protocol is that boundary: an
    implementation carries a single ``(name, args, kwargs)`` request from the
    isolated child to the parent, where :func:`serve_tool_call` runs the real
    tool under the existing allow-list + approval gate, and returns the result.

    Core defines only the contract (and the parent-side :func:`serve_tool_call`
    helper).  Concrete transports — a Unix socket for local subprocess, a mounted
    request/response dir for Docker, etc. — live in the sandbox/wrapper layer so
    core stays lightweight and dependency-free.
    """

    def run_code(
        self,
        code: str,
        *,
        allowed_tools: Iterable[str] = (),
        registry: Optional[ToolRegistry] = None,
        timeout: int = 30,
        max_output_size: int = 10000,
    ) -> Dict[str, Any]:
        """Run *code* under isolation, servicing tool calls over the transport.

        The caller's *invocation policy* is passed explicitly so the transport
        never has to rely on bridge-owned defaults: ``allowed_tools`` /
        ``registry`` are forwarded to :func:`serve_tool_call` in the parent for
        every tool request (so an isolated call is gated by the same allow-list
        and approval framework as the in-process path — never a weaker one), and
        ``timeout`` / ``max_output_size`` bound the isolated run.

        Returns the same ``{result, stdout, stderr, success}`` dict shape as the
        in-process executor so callers are transport-agnostic.
        """
        ...


def serve_tool_call(
    name: str,
    args: Iterable[Any],
    kwargs: Dict[str, Any],
    allowed: Iterable[str],
    registry: Optional[ToolRegistry] = None,
) -> Any:
    """Parent-side handler for a single bridged tool call.

    A :class:`CodeToolBridge` transport calls this for every tool request it
    receives from isolated code.  It reuses the exact allow-list resolution and
    ``require_approval`` gate as the in-process proxy, so an isolated call is
    subject to the same policy as an in-process one — never a weaker path.
    """
    allowed_set = frozenset(allowed)
    resolved_registry = registry or get_registry()
    if name not in allowed_set:
        raise PermissionError(f"tool '{name}' is not allowed from code")
    tool = resolved_registry.get(name)
    if tool is None:
        raise NameError(f"tool '{name}' is not registered")
    return _invoke_with_approval(name, tool, tuple(args), dict(kwargs))


def _resolve_callable(tool: Any) -> Callable[..., Any]:
    """Return the underlying callable for a registered tool/BaseTool."""
    callable_tool = tool.run if hasattr(tool, "run") and not callable(tool) else tool
    if not callable(callable_tool):
        callable_tool = getattr(tool, "run", tool)
    return callable_tool


def _invoke_with_approval(
    name: str, tool: Any, args: tuple, kwargs: Dict[str, Any]
) -> Any:
    """Run a registered tool honouring the existing approval framework.

    The ``require_approval`` decorator (when applied to the tool) already gates
    the call.  For tools that are not decorated but are registered as requiring
    approval, we apply the same gate here so code-mode calls cannot bypass it.

    Positional arguments are bound to their parameter names before being sent to
    the approval backend so the human approver sees every argument value and can
    rewrite any of them via ``decision.modified_args``.
    """
    from ..approval import (
        is_approval_required,
        is_yaml_approved,
        is_env_auto_approve,
        request_approval,
    )

    callable_tool = _resolve_callable(tool)

    # Note: unlike the regular agent path we deliberately do NOT honour the
    # per-session ``is_already_approved`` sticky flag, nor do we call
    # ``mark_approved`` after approval. In code mode the model controls the whole
    # script, so a single approved call must not silently unlock every later call
    # to the same tool with attacker-chosen arguments. Each code-mode call is
    # gated independently (YAML / env auto-approve still apply as configured).
    needs_gate = is_approval_required(name) and not (
        is_yaml_approved(name)
        or is_env_auto_approve()
    )

    if needs_gate:
        from ..utils.async_bridge import (
            is_async_context,
            run_coroutine_from_any_context,
        )

        if is_async_context():
            raise PermissionError(
                f"Tool '{name}' requires approval but cannot prompt from an "
                f"async context. Configure a non-console approval backend."
            )

        # Bind positional args to parameter names so the approval backend sees
        # (and can modify) every argument, not just the keyword ones.
        approval_args: Dict[str, Any] = dict(kwargs)
        bound = None
        try:
            import inspect

            signature = inspect.signature(callable_tool)
            bound = signature.bind_partial(*args, **kwargs)
            approval_args = dict(bound.arguments)
        except (TypeError, ValueError):
            # Signature unavailable/unbindable: fall back to positional preview.
            for index, value in enumerate(args):
                approval_args.setdefault(f"arg{index}", value)

        decision = run_coroutine_from_any_context(
            request_approval(name, approval_args)
        )
        if not decision.approved:
            raise PermissionError(
                f"Execution of {name} denied: {decision.reason}"
            )
        if decision.modified_args:
            approval_args.update(decision.modified_args)
            if bound is not None:
                try:
                    rebound = signature.bind_partial(**approval_args)
                    return callable_tool(*rebound.args, **rebound.kwargs)
                except TypeError:
                    pass
            # Fall back: apply only keyword modifications.
            kwargs.update(
                {k: v for k, v in decision.modified_args.items() if k in kwargs}
            )

    return callable_tool(*args, **kwargs)


def _make_proxy(
    name: str,
    allowed: frozenset,
    registry: ToolRegistry,
) -> Callable[..., Any]:
    """Build a single tool proxy enforcing the allow-list and approval gate."""
    if name not in allowed:
        raise PermissionError(f"tool '{name}' is not allowed from code")
    tool = registry.get(name)
    if tool is None:
        raise NameError(f"tool '{name}' is not registered")

    def _proxy(*args: Any, **kwargs: Any) -> Any:
        return _invoke_with_approval(name, tool, args, kwargs)

    _proxy.__name__ = name
    return _proxy


class ToolProxy:
    """Namespace object exposed to sandboxed code as ``tools``.

    Resolves tool names against a :class:`ToolRegistry`, enforces an
    allow-list, and routes each call through the approval gate.

    The registry and allow-list are held in a closure (``__getattribute__``
    override) rather than as instance attributes, so sandboxed code cannot reach
    them through plain attribute access (e.g. ``tools._registry``) to bypass the
    allow-list or approval gate.

    Example (inside model-generated code)::

        best = min(extract_price(fetch(u)) for u in urls)
        print(best)

    where ``fetch`` / ``extract_price`` are exposed as proxies.
    """

    def __init__(
        self,
        allowed: Iterable[str],
        registry: Optional[ToolRegistry] = None,
    ) -> None:
        allowed_set = frozenset(allowed)
        resolved_registry = registry or get_registry()

        def _getter(name: str) -> Callable[..., Any]:
            return _make_proxy(name, allowed_set, resolved_registry)

        # Stash all state inside a closure; never as an instance attribute.
        object.__setattr__(self, "_ToolProxy__getter", _getter)
        object.__setattr__(self, "_ToolProxy__names", sorted(allowed_set))

    def __getattribute__(self, name: str) -> Any:
        # Allow a tiny set of dunder methods needed for normal object use;
        # everything else is treated as a tool-name lookup.
        # NB: ``__init__`` is deliberately excluded — exposing it would let
        # sandboxed code call ``tools.__init__([...])`` to re-bind the proxy's
        # closure to the global registry with an attacker-chosen allow-list,
        # bypassing the per-run allow-list entirely.
        if name in ("__class__", "__dict__", "__repr__", "__dir__"):
            return object.__getattribute__(self, name)
        if name.startswith("_"):
            raise AttributeError(name)
        getter = object.__getattribute__(self, "_ToolProxy__getter")
        return getter(name)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("ToolProxy is read-only")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("ToolProxy is read-only")

    def __dir__(self):
        return list(object.__getattribute__(self, "_ToolProxy__names"))

    def __repr__(self) -> str:
        names = object.__getattribute__(self, "_ToolProxy__names")
        return f"ToolProxy(allowed={names})"


def build_tool_namespace(
    allowed: Iterable[str],
    registry: Optional[ToolRegistry] = None,
) -> Dict[str, Callable[..., Any]]:
    """Build a dict of ``{tool_name: proxy_callable}`` for the allow-list.

    The returned mapping can be merged directly into the executor globals so
    the model can call ``fetch(...)`` by bare name, in addition to the
    ``tools.fetch(...)`` form via :class:`ToolProxy`.
    """
    allowed_set = frozenset(allowed)
    resolved_registry = registry or get_registry()
    namespace: Dict[str, Callable[..., Any]] = {}
    for name in sorted(allowed_set):
        try:
            namespace[name] = _make_proxy(name, allowed_set, resolved_registry)
        except NameError:
            # Tool on the allow-list but not registered yet — skip silently;
            # calling it would raise NameError at runtime anyway.
            continue
    return namespace

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
"""

from typing import Any, Callable, Dict, Iterable, Optional

from .registry import ToolRegistry, get_registry


def _invoke_with_approval(
    name: str, tool: Any, args: tuple, kwargs: Dict[str, Any]
) -> Any:
    """Run a registered tool honouring the existing approval framework.

    The ``require_approval`` decorator (when applied to the tool) already gates
    the call.  For tools that are not decorated but are registered as requiring
    approval, we apply the same gate here so code-mode calls cannot bypass it.
    """
    from ..approval import (
        is_approval_required,
        is_already_approved,
        is_yaml_approved,
        is_env_auto_approve,
        mark_approved,
        request_approval,
    )

    callable_tool = tool.run if hasattr(tool, "run") and not callable(tool) else tool
    if not callable(callable_tool):
        callable_tool = getattr(tool, "run", tool)

    needs_gate = is_approval_required(name) and not (
        is_already_approved(name)
        or is_yaml_approved(name)
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
        decision = run_coroutine_from_any_context(request_approval(name, kwargs))
        if not decision.approved:
            raise PermissionError(
                f"Execution of {name} denied: {decision.reason}"
            )
        mark_approved(name)
        if decision.modified_args:
            kwargs.update(decision.modified_args)

    return callable_tool(*args, **kwargs)


class ToolProxy:
    """Namespace object exposed to sandboxed code as ``tools``.

    Resolves tool names against a :class:`ToolRegistry`, enforces an
    allow-list, and routes each call through the approval gate.

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
        # Use object.__setattr__ so __setattr__ guard below never trips here.
        object.__setattr__(self, "_registry", registry or get_registry())
        object.__setattr__(self, "_allowed", set(allowed))

    def _make_proxy(self, name: str) -> Callable[..., Any]:
        if name not in self._allowed:
            raise PermissionError(
                f"tool '{name}' is not allowed from code"
            )
        tool = self._registry.get(name)
        if tool is None:
            raise NameError(f"tool '{name}' is not registered")

        def _proxy(*args: Any, **kwargs: Any) -> Any:
            return _invoke_with_approval(name, tool, args, kwargs)

        _proxy.__name__ = name
        return _proxy

    def __getattr__(self, name: str) -> Callable[..., Any]:
        # Only reached for names not found as real attributes.
        if name.startswith("_"):
            raise AttributeError(name)
        return self._make_proxy(name)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("ToolProxy is read-only")

    def __dir__(self):
        return sorted(self._allowed)

    def __repr__(self) -> str:
        return f"ToolProxy(allowed={sorted(self._allowed)})"


def build_tool_namespace(
    allowed: Iterable[str],
    registry: Optional[ToolRegistry] = None,
) -> Dict[str, Callable[..., Any]]:
    """Build a dict of ``{tool_name: proxy_callable}`` for the allow-list.

    The returned mapping can be merged directly into the executor globals so
    the model can call ``fetch(...)`` by bare name, in addition to the
    ``tools.fetch(...)`` form via :class:`ToolProxy`.
    """
    proxy = ToolProxy(allowed, registry=registry)
    namespace: Dict[str, Callable[..., Any]] = {}
    for name in proxy._allowed:
        try:
            namespace[name] = proxy._make_proxy(name)
        except NameError:
            # Tool on the allow-list but not registered yet — skip silently;
            # calling it would raise NameError at runtime anyway.
            continue
    return namespace

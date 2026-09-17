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
    # ``registry is not None`` (not truthiness): an empty ToolRegistry is a
    # meaningful, deliberate boundary ("this agent granted no tools"), and
    # ToolRegistry is falsy when empty (__len__), so ``registry or ...`` would
    # silently fall back to the process-global registry and leak un-granted
    # tools into code mode.
    resolved_registry = registry if registry is not None else get_registry()
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
        # ``is not None`` so an explicitly-passed empty (agent-scoped) registry
        # is honoured rather than falling back to the global one.
        resolved_registry = registry if registry is not None else get_registry()

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


# Protocol markers for the parent/child line protocol used by
# :class:`LocalProcessBridge`. Each is a stdout line prefix the child emits and
# the parent recognises; anything else the child prints is captured as the
# script's ordinary stdout.
_BRIDGE_CALL = "\x00PRAISON_TOOL_CALL\x00"
_BRIDGE_DONE = "\x00PRAISON_DONE\x00"


class LocalProcessBridge:
    """Zero-config :class:`CodeToolBridge`: subprocess isolation + bridged tools.

    This is the shipped default transport for ``code_mode="isolated"``. The
    model-generated script runs in a **separate Python process** (real
    isolation with a clean environment and, on POSIX, resource limits), while
    every allow-listed tool call is marshalled back to *this* parent process and
    serviced by :func:`serve_tool_call` — the exact same allow-list + approval
    gate as the in-process path, never a weaker one. Only the script's
    stdout / last-expression value returns to the caller; intermediate tool
    results stay out of the context window.

    No new dependencies: the parent<->child channel is a newline-delimited JSON
    protocol over the child's stdin/stdout.
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
        import os
        import subprocess
        import sys
        import tempfile

        allowed = sorted({str(a) for a in allowed_tools})
        script = _CHILD_TEMPLATE.format(
            code=repr(code),
            allowed=repr(allowed),
            call_marker=repr(_BRIDGE_CALL),
            done_marker=repr(_BRIDGE_DONE),
        )

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as handle:
                handle.write(script)
                temp_file = handle.name
        except OSError as exc:
            return {
                "result": None,
                "stdout": "",
                "stderr": f"Isolated execution error: {exc}",
                "success": False,
            }

        try:
            preexec_fn = None
            if os.name == "posix":
                try:
                    from .python_tools import _make_resource_preexec
                    from ..sandbox.protocols import ResourceLimits

                    limits = ResourceLimits.minimal()
                    limits.timeout_seconds = timeout
                    preexec_fn = _make_resource_preexec(limits)
                except Exception:
                    preexec_fn = None

            process = subprocess.Popen(
                [sys.executable, temp_file],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={},  # clean environment: no parent env leaks into the child
                text=True,
                shell=False,
                cwd=tempfile.gettempdir(),
                preexec_fn=preexec_fn,
            )
            # NB: policy errors (PermissionError/NameError from serve_tool_call)
            # are re-raised out of _pump_bridge so the isolated path fails the
            # same way as the in-process one — do not wrap this in a broad
            # try/except that would swallow them.
            return _pump_bridge(
                process, allowed, registry, timeout, max_output_size
            )
        finally:
            if temp_file:
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass


def _pump_bridge(process, allowed, registry, timeout, max_output_size):
    """Drive the child: service tool-call requests, collect the result.

    Runs in the parent. Tool-call request lines are serviced by
    :func:`serve_tool_call` (same allow-list + approval gate as in-process); the
    first policy failure is captured and re-raised after the child exits so a
    disallowed/denied tool surfaces as ``PermissionError`` exactly like the
    in-process path.
    """
    import json
    import threading

    outcome: Dict[str, Any] = {}
    captured_stdout: list = []
    policy_error: list = []

    def _drive():
        # Reads the child's stdout and services tool-call requests. Runs in its
        # own thread so the parent can enforce the wall-clock timeout by killing
        # the child. Do NOT use process.communicate() here: it would consume the
        # same stdout this loop is reading and deadlock the line protocol.
        try:
            for line in process.stdout:
                line = line.rstrip("\n")
                if line.startswith(_BRIDGE_CALL):
                    payload = json.loads(line[len(_BRIDGE_CALL):])
                    response = _service_bridge_call(
                        payload, allowed, registry, policy_error
                    )
                    try:
                        encoded = json.dumps(response)
                    except (TypeError, ValueError):
                        # A tool returned a value JSON cannot carry across the
                        # boundary; degrade to its string form rather than
                        # crashing the whole run.
                        encoded = json.dumps(
                            {"ok": response.get("ok", True),
                             "value": str(response.get("value")),
                             "error": response.get("error")}
                        )
                    try:
                        process.stdin.write(encoded + "\n")
                        process.stdin.flush()
                    except (BrokenPipeError, ValueError, OSError):
                        break
                elif line.startswith(_BRIDGE_DONE):
                    outcome.update(json.loads(line[len(_BRIDGE_DONE):]))
                else:
                    captured_stdout.append(line)
        except Exception:  # pragma: no cover - defensive
            pass

    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    driver.join(timeout=timeout)
    if driver.is_alive():
        process.kill()
        driver.join(timeout=1)
        try:
            process.stdout.close()
            process.stdin.close()
        except Exception:
            pass
        return {
            "result": None,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds",
            "success": False,
        }

    try:
        process.wait(timeout=1)
    except Exception:
        process.kill()
    stderr = ""
    try:
        stderr = process.stderr.read() or ""
    except Exception:
        stderr = ""

    # The parent's gate decision is authoritative: re-raise the first denial.
    if policy_error:
        raise policy_error[0]

    stdout = outcome.get("stdout") or "\n".join(captured_stdout)
    if len(stdout) > max_output_size:
        tail = min(max_output_size // 5, 500)
        stdout = (
            stdout[: max_output_size - tail]
            + f"\n...[{len(stdout):,} chars, truncated]...\n"
            + stdout[-tail:]
        )

    if not outcome:
        # The child exited without reporting a result: a crash, an OOM/CPU
        # resource-limit kill (SIGKILL/SIGXCPU from the preexec limits), or a
        # non-zero exit. Surface the exit code so this isn't mistaken for a
        # clean empty run.
        rc = process.poll()
        detail = stderr or "Isolated child produced no result"
        if rc is not None and rc != 0:
            detail = (
                stderr
                or f"Isolated child exited abnormally (code {rc}); it may have "
                "hit a CPU/memory limit or been killed."
            )
        return {
            "result": None,
            "stdout": stdout,
            "stderr": detail,
            "success": False,
        }
    outcome["stdout"] = stdout
    if stderr and not outcome.get("stderr"):
        outcome["stderr"] = stderr
    return outcome


def _service_bridge_call(payload, allowed, registry, policy_error):
    """Run one bridged tool call in the parent under the shared gate."""
    name = payload.get("name")
    args = payload.get("args", [])
    kwargs = payload.get("kwargs", {})
    try:
        value = serve_tool_call(
            name, args, kwargs, allowed=allowed, registry=registry
        )
        return {"ok": True, "value": value}
    except BaseException as exc:  # noqa: BLE001 - propagate to child + parent
        # Capture the first policy/tool failure so the parent can re-raise it
        # (authoritative), and tell the child to raise so the script stops.
        if not policy_error:
            policy_error.append(exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# Source of the isolated child. It mirrors the in-process executor's security
# posture (imports/eval/exec/open blocked via restricted builtins) and adds a
# ``tools`` proxy + bare-name proxies that marshal calls to the parent. Kept as
# a module-level template so LocalProcessBridge.run_code stays small.
_CHILD_TEMPLATE = '''\
import ast
import io
import json
import sys

_CALL = {call_marker}
_DONE = {done_marker}
_USER_CODE = {code}
_ALLOWED = {allowed}

_real_stdout = sys.stdout


def _emit(marker, obj):
    _real_stdout.write(marker + json.dumps(obj) + "\\n")
    _real_stdout.flush()


def _call_tool(_name, *args, **kwargs):
    _emit(_CALL, {{"name": _name, "args": list(args), "kwargs": kwargs}})
    line = sys.stdin.readline()
    resp = json.loads(line)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "tool call failed"))
    return resp["value"]


class _ToolNamespace:
    def __getattribute__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        # Marshal every access to the parent so the parent's allow-list +
        # approval gate is the single authoritative decision (a call to a
        # disallowed tool via tools.<name> is rejected there, not silently in
        # the child).
        def _proxy(*a, **k):
            return _call_tool(name, *a, **k)
        return _proxy


def _main():
    buf = io.StringIO()
    result = None
    try:
        tree = ast.parse(_USER_CODE)
    except SyntaxError:
        _emit(_DONE, {{"result": None, "stdout": "",
                       "stderr": "Syntax Error in provided code",
                       "success": False}})
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _emit(_DONE, {{"result": None, "stdout": "",
                           "stderr": "Import statements are not allowed",
                           "success": False}})
            return

    safe_builtins = {{
        "print": print, "len": len, "range": range, "enumerate": enumerate,
        "zip": zip, "map": map, "filter": filter, "sum": sum, "min": min,
        "max": max, "abs": abs, "round": round, "sorted": sorted,
        "reversed": reversed, "any": any, "all": all, "int": int,
        "float": float, "str": str, "bool": bool, "list": list,
        "tuple": tuple, "dict": dict, "set": set, "pow": pow,
        "divmod": divmod, "isinstance": isinstance, "type": type,
        "hasattr": hasattr, "getattr": getattr,
        "Exception": Exception, "ValueError": ValueError,
        "TypeError": TypeError, "KeyError": KeyError,
        "IndexError": IndexError, "RuntimeError": RuntimeError,
        "PermissionError": PermissionError,
        "__build_class__": __build_class__,
    }}
    g = {{"__builtins__": safe_builtins, "tools": _ToolNamespace()}}
    for _n in _ALLOWED:
        def _make(nm):
            return lambda *a, **k: _call_tool(nm, *a, **k)
        g[_n] = _make(_n)

    last = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body.pop()
    try:
        sys.stdout = buf
        exec(compile(tree, "<isolated>", "exec"), g)
        if last is not None:
            result = eval(
                compile(ast.Expression(last.value), "<isolated>", "eval"), g
            )
        sys.stdout = _real_stdout
        _emit(_DONE, {{"result": str(result) if result is not None else None,
                       "stdout": buf.getvalue(), "stderr": "",
                       "success": True}})
    except BaseException as exc:
        sys.stdout = _real_stdout
        _emit(_DONE, {{"result": None, "stdout": buf.getvalue(),
                       "stderr": "Error: " + str(exc), "success": False}})


_main()
'''


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
    # ``is not None`` so an explicitly-passed empty (agent-scoped) registry is
    # honoured rather than falling back to the global one.
    resolved_registry = registry if registry is not None else get_registry()
    namespace: Dict[str, Callable[..., Any]] = {}
    for name in sorted(allowed_set):
        try:
            namespace[name] = _make_proxy(name, allowed_set, resolved_registry)
        except NameError:
            # Tool on the allow-list but not registered yet — skip silently;
            # calling it would raise NameError at runtime anyway.
            continue
    return namespace

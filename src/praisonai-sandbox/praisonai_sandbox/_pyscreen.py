"""Python screen for SecurityPolicy: a safety net, not isolation (SECURITY.md).
Follows __import__, importlib, getattr, __builtins__ and posix.system; applies
allowed_imports, allow_subprocess=False and path literals."""
import ast
import builtins
import dataclasses
from typing import Callable, Dict, Optional

# Screened when allow_subprocess=False: modules and calls that start a process.
SPAWN = """subprocess multiprocessing pty pexpect os.system os.popen os.fork os.forkpty os.posix_spawn
    os.posix_spawnp asyncio.create_subprocess_exec asyncio.create_subprocess_shell""".split() + [
    f"os.{p}{s}" for p in ("exec", "spawn") for s in ("l", "le", "lp", "lpe", "v", "ve", "vp", "vpe")]
_DYNAMIC_IMPORTS = {"__import__", "importlib.import_module", "importlib.__import__", "builtins.__import__"}
_INTERNALS = {"__builtins__", "__globals__", "__subclasses__"}  # lead back to every builtin

def _canonical(name: str) -> str:
    head, dot, rest = name.partition(".")  # posix.system is os.system
    return {"posix": "os", "nt": "os"}.get(head, head) + dot + rest

def screen_python(code: str, policy, check_command: Callable) -> Optional[str]:
    """Return an error when *code* breaks *policy*; *check_command* screens paths."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # the interpreter reports the syntax error
    nodes = list(ast.walk(tree))
    literals = [n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value and len(n.value.split()) == 1 and ("/" in n.value or n.value[0] in "~.")]
    error = literals and check_command(["python", *literals], dataclasses.replace(  # open("/etc/x")
        policy, blocked_commands=[], allowed_commands=[], allow_subprocess=True))
    if error:
        return error
    blocked = [b for b in policy.blocked_imports or [] if b]
    blocked += [] if policy.allow_subprocess else SPAWN
    allowed = {a.split(".")[0] for a in policy.allowed_imports or [] if a}
    if not blocked and not allowed:
        return None
    modules = {b for b in blocked if "." not in b}
    dotted = {b for b in blocked if "." in b}
    def module_error(name: str) -> Optional[str]:
        root = _canonical(name).split(".")[0]
        if root in modules or name in modules or root == "builtins" or (allowed and root not in allowed):
            return f"Blocked import: {name}"
    binds: Dict[str, str] = {}  # local name -> real dotted name
    for n in nodes:
        if isinstance(n, ast.Import):
            for a in n.names:
                binds[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                binds[a.asname or a.name] = _canonical(f"{n.module}.{a.name}")
    def dotted_name(expr) -> Optional[str]:
        parts = []
        while isinstance(expr, ast.Attribute):
            parts.append(expr.attr)
            expr = expr.value
        root = binds.get(expr.id, expr.id) if isinstance(expr, ast.Name) else None
        if (isinstance(expr, ast.Call) and dotted_name(expr.func) in _DYNAMIC_IMPORTS
                and expr.args and isinstance(expr.args[0], ast.Constant)):
            root = str(expr.args[0].value)  # __import__("os").system
        return root and _canonical(".".join([root, *reversed(parts)]))
    for n in nodes:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in n.names] if isinstance(n, ast.Import) else (
                [n.module, *(f"{n.module}.{a.name}" for a in n.names)] if n.module and not n.level else [])
            for name in names:
                if module_error(name) or _canonical(name) in dotted:
                    return f"Blocked import: {name}"
        elif isinstance(n, ast.Call):
            func = dotted_name(n.func)
            arg = n.args[0] if n.args else None
            if func in _DYNAMIC_IMPORTS:
                error = module_error(arg.value) if isinstance(arg, ast.Constant) and isinstance(
                    arg.value, str) else "Blocked call: import of a computed module name"
                if error:
                    return error
            elif func == "getattr" and len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                attr, target = str(n.args[1].value), dotted_name(arg)
                if attr in modules or (f"{target}.{attr}" in dotted if target else any(
                        d.rsplit(".", 1)[1] == attr for d in dotted)):
                    return f"Blocked call: {target or '?'}.{attr}"
        elif isinstance(n, ast.Attribute):
            if n.attr in _INTERNALS or dotted_name(n) in dotted:
                return f"Blocked attribute: {dotted_name(n) or n.attr}"
        elif isinstance(n, ast.Constant) and n.value in _INTERNALS:
            return f"Blocked attribute: {n.value}"  # globals()["__builtins__"]
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            # `e = eval; e(...)`: a blocked builtin read as a value is called later.
            if n.id in _INTERNALS or (n.id in modules and hasattr(builtins, n.id)) \
                    or binds.get(n.id) in dotted:
                return f"Blocked call: {binds.get(n.id, n.id)}"
    return None

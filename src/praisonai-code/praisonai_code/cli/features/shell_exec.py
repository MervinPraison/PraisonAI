"""A shell tool that is either a real shell, or honest about not being one.

Background
----------
``praisonaiagents.tools.execute_command`` runs ``shlex.split`` +
``subprocess.Popen(..., shell=False)``.  ``shell=False`` is a deliberate and
legitimate prompt-injection defence, and this module does **not** remove it.
The defect is what happens to a command that contains shell syntax::

    execute_command("echo written > redir.txt")
    -> {"exit_code": 0, "success": True, "stdout": "written > redir.txt\\n"}
       and redir.txt was never created

``>`` became a literal argument to ``echo``.  The model is told its redirect
succeeded, so there is no signal to correct on -- strictly worse than an error.
Same for ``cd .. && pwd`` (exit 0, empty stdout) and ``a | wc -l``.

The headless ACP path had the opposite failure: ``_sanitize_command`` rejected
any command containing ``&&``, ``|``, ``>``, ``;``, backtick or ``$(``, so
ordinary build-test-fix one-liners were refused outright even when the operator
had containment available.

What this module does
---------------------
Three modes, selected by ``PRAISON_SHELL`` (or the ``mode=`` argument):

``off`` (default)
    Shell syntax is detected *before* execution and the call fails loudly,
    naming the operator that would have been silently dropped and telling the
    agent what to do instead.  Simple commands run exactly as before.

``sandboxed``
    A real ``/bin/sh -c`` runs inside OS-native containment (Seatbelt on macOS,
    bubblewrap on Linux) whose enforcement has been *measured* this process --
    see :mod:`praisonai_code.cli.features.os_sandbox`.  If containment cannot be
    proven, this mode refuses to run rather than quietly degrading to an
    uncontained shell.

``unsafe``
    A real ``/bin/sh -c`` with no containment.  Opt-in only, never a fallback.

The one thing that is never done is reporting success for a redirect that did
not happen.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "MODE_ENV_VAR",
    "find_shell_syntax",
    "resolve_mode",
    "run_shell_command",
    "execute_command",
]

MODE_ENV_VAR = "PRAISON_SHELL"

MODE_OFF = "off"
MODE_SANDBOXED = "sandboxed"
MODE_UNSAFE = "unsafe"
_VALID_MODES = (MODE_OFF, MODE_SANDBOXED, MODE_UNSAFE)

# Two-character operators are checked before single characters so that ``&&``
# is reported as ``&&`` rather than ``&``.
_TWO_CHAR_OPS = ("&&", "||", ">>", "2>", "$(", "<<")
_ONE_CHAR_OPS = ("|", ">", "<", ";", "&", "`")


def find_shell_syntax(command: str) -> Optional[str]:
    """Return the first *active* shell operator in ``command``, else ``None``.

    Quote-aware on purpose: ``echo "a > b"`` contains no redirect, and calling
    it one would break commit messages, grep patterns and JSON payloads.

    But POSIX command substitution stays *active inside double quotes*:
    ``echo "$(id)"`` and ``echo "`id`"`` both run the inner command. Reporting
    those as inert would reintroduce the false-success bug this module exists to
    kill -- the ``shell=False`` executor would print the literal ``$(id)`` and
    claim success. So ``$(`` and the backtick are detected even within double
    quotes; single quotes still suppress everything.
    """
    if not command:
        return None
    i = 0
    n = len(command)
    quote: Optional[str] = None
    while i < n:
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            # Command substitution is not suppressed by double quotes.
            if quote == '"':
                if command[i:i + 2] == "$(":
                    return "$("
                if ch == "`":
                    return "`"
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        two = command[i:i + 2]
        if two in _TWO_CHAR_OPS:
            return two
        if ch in _ONE_CHAR_OPS:
            return ch
        if ch in ("\n", "\r"):
            return "newline"
        i += 1
    if quote:
        # An unterminated quote can hide an operator from this scan
        # ('echo "a ; rm -rf /'), and shlex.split would raise on it anyway.
        # Report it so the command is refused rather than waved through.
        return "unterminated-quote"
    return None


def resolve_mode(mode: Optional[str] = None) -> str:
    """Resolve the effective shell mode from an argument or the environment."""
    raw = (mode if mode is not None else os.environ.get(MODE_ENV_VAR, "")).strip().lower()
    if raw in ("", "0", "false", "no", "none"):
        return MODE_OFF
    if raw in ("1", "true", "yes", "sandbox", "sandboxed", "native"):
        return MODE_SANDBOXED
    if raw in ("unsafe", "raw", "host"):
        return MODE_UNSAFE
    if raw in _VALID_MODES:
        return raw
    logger.warning(
        "Unrecognised %s=%r; treating as %r", MODE_ENV_VAR, raw, MODE_OFF
    )
    return MODE_OFF


def _refusal(command: str, operator: str, reason: str) -> Dict[str, Union[str, int, bool]]:
    return {
        "command": command,
        "stdout": "",
        "stderr": reason,
        "exit_code": 126,
        "success": False,
        "error": reason,
        "shell_syntax": operator,
    }


def _shell_syntax_refusal(command: str, operator: str, mode: str, detail: str = "") -> Dict:
    reason = (
        f"Refused: this command contains the shell operator {operator!r}, which "
        f"this executor does not interpret. Running it would pass {operator!r} to "
        f"the program as a literal argument and report success for work that "
        f"never happened (e.g. a redirect that creates no file).\n"
    )
    if mode == MODE_OFF:
        reason += (
            "Do one of these instead:\n"
            "  - split it into separate execute_command calls "
            "(one per '&&' / ';' step);\n"
            "  - for a redirect, run the program and write its output with "
            "write_file;\n"
            "  - for a pipe, run the first command and filter the result with "
            "grep/read_file;\n"
            f"  - or ask the operator to set {MODE_ENV_VAR}=sandboxed, which runs "
            "a real /bin/sh inside OS-native containment."
        )
    else:
        reason += detail
    return _refusal(command, operator, reason)


def _strip_wrapping_quotes(command: str) -> str:
    if command and len(command) >= 2 and command[0] == command[-1] and command[0] in ("'", '"'):
        inner = command[1:-1]
        # Only strip when the quotes really wrap the whole string.
        if command[0] not in inner:
            return inner
    return command


def _delegate(command: str, **kwargs) -> Dict:
    """Run a metacharacter-free command through the existing safe executor."""
    from praisonaiagents.tools import execute_command as _base
    return _base(command, **kwargs)


def _kill_process_tree(proc: "subprocess.Popen") -> None:
    """Terminate a timed-out shell and every descendant it spawned.

    The child was started with ``start_new_session=True`` (POSIX), so it leads
    its own process group; killing the group reaches backgrounded descendants
    (``& wait``) that a plain ``proc.kill()`` would orphan and leave running.
    Falls back to killing just the process where a process group is unavailable
    (Windows, or a session that could not be created).
    """
    import signal

    if os.name == "posix":
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):  # pragma: no cover - already gone
        pass


def _run_real_shell(
    command: str,
    cwd: Optional[str],
    timeout: int,
    env: Optional[Dict[str, str]],
    max_output_size: int,
    contained: bool,
    writable_paths=None,
    network: bool = False,
) -> Dict[str, Union[str, int, bool]]:
    argv = ["/bin/sh", "-c", command]
    backend = "none"
    wrapper = None
    if contained:
        from .os_sandbox import build_wrapper

        paths = list(writable_paths or [cwd or os.getcwd()])
        wrapper = build_wrapper(writable_paths=paths, network=network)
        if wrapper is None:  # pragma: no cover - guarded by caller
            return _refusal(command, "", "No OS sandbox backend available")
        argv = wrapper.wrap(argv)
        backend = wrapper.backend

    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    # Run the shell in its own process group so a timeout can kill the whole
    # tree, not just the immediate ``/bin/sh``. Without this a command like
    # ``(sleep 60; mutate) & wait`` times out, loses only the top shell, and
    # leaves the backgrounded descendant running and mutating files after the
    # tool has reported that execution stopped.
    popen_kwargs = {}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True

    proc = None
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd or None,
            env=proc_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **popen_kwargs,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            out, err = proc.communicate()
            return {
                "command": command,
                "stdout": out or "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": 124,
                "success": False,
                "error": f"Command timed out after {timeout}s",
                "sandbox": backend,
            }
    except OSError as exc:
        return _refusal(command, "", f"Failed to start shell: {exc}")
    finally:
        if wrapper is not None:
            wrapper.cleanup()

    class _Completed:
        pass

    completed = _Completed()
    completed.stdout = out
    completed.stderr = err
    completed.returncode = proc.returncode

    def _cap(text: str) -> str:
        if max_output_size and len(text) > max_output_size:
            half = max_output_size // 2
            return text[:half] + "\n... [output truncated] ...\n" + text[-half:]
        return text

    return {
        "command": command,
        "stdout": _cap(completed.stdout or ""),
        "stderr": _cap(completed.stderr or ""),
        "exit_code": completed.returncode,
        "success": completed.returncode == 0,
        "error": None,
        "sandbox": backend,
    }


def _real_shell(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 30,
    env: Optional[Dict[str, str]] = None,
    max_output_size: int = 10000,
    contained: bool = True,
    writable_paths=None,
    network: bool = False,
) -> Dict[str, Union[str, int, bool]]:
    """Approval-gated entry point for the real-shell path.

    Renamed to ``execute_command`` *before* decoration so it registers under the
    same tool identity and the same ``critical`` risk level as the existing
    ``praisonaiagents`` shell tool.  Without this the real-shell path would run
    outside the approval registry entirely -- a strictly weaker guard than the
    ``shell=False`` executor it stands beside.
    """
    return _run_real_shell(
        command, cwd, timeout, env, max_output_size,
        contained=contained, writable_paths=writable_paths, network=network,
    )


_real_shell.__name__ = "execute_command"


def _approved_real_shell(*args, **kwargs):
    """Lazily wrap :func:`_real_shell` in ``require_approval`` on first use.

    Fails closed: if the approval machinery cannot be imported, the real shell
    does not run.
    """
    global _APPROVED_REAL_SHELL
    if _APPROVED_REAL_SHELL is None:
        from praisonaiagents.approval import require_approval

        _APPROVED_REAL_SHELL = require_approval(risk_level="critical")(_real_shell)
    return _APPROVED_REAL_SHELL(*args, **kwargs)


_APPROVED_REAL_SHELL = None


def run_shell_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 30,
    env: Optional[Dict[str, str]] = None,
    max_output_size: int = 10000,
    mode: Optional[str] = None,
    writable_paths=None,
    network: bool = False,
    **kwargs,
) -> Dict[str, Union[str, int, bool]]:
    """Execute ``command``, never claiming success for syntax it dropped."""
    command = _strip_wrapping_quotes(command or "")
    if not command.strip():
        return _refusal("", "", "Empty command")

    operator = find_shell_syntax(command)
    effective = resolve_mode(mode)

    if operator is None:
        return _delegate(
            command,
            cwd=cwd,
            timeout=timeout,
            env=env,
            max_output_size=max_output_size,
            **kwargs,
        )

    if effective == MODE_OFF:
        return _shell_syntax_refusal(command, operator, MODE_OFF)

    if effective == MODE_SANDBOXED:
        from .os_sandbox import probe_enforcement

        enforcing, backend, detail = probe_enforcement()
        if not enforcing:
            return _shell_syntax_refusal(
                command,
                operator,
                MODE_SANDBOXED,
                detail=(
                    f"{MODE_ENV_VAR}=sandboxed was requested but containment could "
                    f"not be proven on this machine ({detail}). Refusing to run a "
                    f"real shell uncontained -- a sandbox that is assumed but not "
                    f"enforcing is worse than none. Set {MODE_ENV_VAR}=unsafe to "
                    f"accept an uncontained shell deliberately."
                ),
            )
        return _approved_real_shell(
            command, cwd, timeout, env, max_output_size,
            contained=True, writable_paths=writable_paths, network=network,
        )

    return _approved_real_shell(
        command, cwd, timeout, env, max_output_size, contained=False,
    )


def execute_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 30,
    env: Optional[Dict[str, str]] = None,
    max_output_size: int = 10000,
    **kwargs,
) -> Dict[str, Union[str, int, bool]]:
    """Execute a shell command.

    Shell operators (``&&``, ``||``, ``|``, ``>``, ``>>``, ``;``, ``` ` ```,
    ``$(``) are only honoured when a real shell has been enabled via
    ``PRAISON_SHELL``. Otherwise the call FAILS with an explanation instead of
    silently dropping them and reporting success.

    Args:
        command: Command to execute
        cwd: Working directory
        timeout: Maximum execution time in seconds
        env: Extra environment variables
        max_output_size: Maximum output size in bytes

    Returns:
        Dict with ``stdout``, ``stderr``, ``exit_code``, ``success``, ``error``.
    """
    return run_shell_command(
        command,
        cwd=cwd,
        timeout=timeout,
        env=env,
        max_output_size=max_output_size,
        **kwargs,
    )

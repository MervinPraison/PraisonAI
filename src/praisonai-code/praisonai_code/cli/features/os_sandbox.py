"""OS-native containment for agent-run shell commands.

``praisonaiagents.sandbox.SandboxConfig.native()`` advertises "macOS: Seatbelt
(sandbox-exec), Linux: Landlock + bubblewrap", but
``SandboxManager._create_sandbox`` maps ``native`` straight to the ``sandlock``
backend, which is Linux-only and needs the optional ``sandlock`` wheel plus
Landlock ABI >= 6.  On macOS -- and on any Linux box without that wheel -- the
call raises ``ImportError`` and there is no containment at all.  So the coding
agent had nothing to reach for.

This module provides the missing piece: a *process wrapper* that puts a real
child process inside a kernel-enforced filesystem jail.

  * macOS   -> ``sandbox-exec`` (Seatbelt) with a generated profile.
  * Linux   -> ``bwrap`` (bubblewrap) with a read-only root and bind-mounted
                writable paths.
  * elsewhere -> nothing; :func:`build_wrapper` returns ``None``.

The critical design rule is that this module **never claims containment it has
not observed**.  :func:`probe_enforcement` actually runs a child under the
wrapper and tries to write outside the writable set.  If that write succeeds,
the backend is reported unavailable rather than trusted.  A sandbox that is
believed but not enforcing is worse than no sandbox, because callers relax on
the strength of the belief.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "SandboxUnavailable",
    "SandboxWrapper",
    "build_wrapper",
    "describe_backend",
    "probe_enforcement",
    "reset_probe_cache",
]

# Directories a child always needs to write to for ordinary tooling to work
# (pty allocation, /dev/null, temp files created by compilers and test runners).
_ALWAYS_WRITABLE_DARWIN = ("/dev",)


class SandboxUnavailable(RuntimeError):
    """Raised when containment was required but no backend can enforce it."""


@dataclass
class SandboxWrapper:
    """A command prefix that confines a child process.

    ``argv_prefix`` is prepended to the real argv.  ``backend`` is one of
    ``seatbelt`` / ``bubblewrap``.  ``cleanup`` removes any temp profile file.
    """

    backend: str
    argv_prefix: List[str]
    writable_paths: List[str] = field(default_factory=list)
    network: bool = False
    _profile_path: Optional[str] = None

    def wrap(self, argv: Sequence[str]) -> List[str]:
        return [*self.argv_prefix, *argv]

    def cleanup(self) -> None:
        if self._profile_path and os.path.exists(self._profile_path):
            try:
                os.unlink(self._profile_path)
            except OSError:  # pragma: no cover - best effort
                pass
            self._profile_path = None

    def __enter__(self) -> "SandboxWrapper":
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()


def _resolve(path: str) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def _sb_quote(path: str) -> str:
    """Quote a path for a Seatbelt profile string literal."""
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _seatbelt_profile(writable: Sequence[str], network: bool) -> str:
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
    ]
    subpaths = list(_ALWAYS_WRITABLE_DARWIN) + list(writable)
    if subpaths:
        lines.append("(allow file-write*")
        for p in subpaths:
            lines.append(f"    (subpath {_sb_quote(p)})")
        lines.append(")")
    if not network:
        lines.append("(deny network*)")
        # Unix-domain sockets are modelled as network-outbound to a path; keep
        # them so local IPC (DNS resolver handshake, pty helpers) still works.
        lines.append('(allow network-outbound (subpath "/private/var/run"))')
        lines.append('(allow network-outbound (subpath "/var/run"))')
    return "\n".join(lines) + "\n"


def _build_seatbelt(writable: Sequence[str], network: bool) -> Optional[SandboxWrapper]:
    exe = shutil.which("sandbox-exec")
    if not exe:
        return None
    profile = _seatbelt_profile(writable, network)
    fd, path = tempfile.mkstemp(prefix="praisonai_seatbelt_", suffix=".sb")
    with os.fdopen(fd, "w") as fh:
        fh.write(profile)
    return SandboxWrapper(
        backend="seatbelt",
        argv_prefix=[exe, "-f", path],
        writable_paths=list(writable),
        network=network,
        _profile_path=path,
    )


def _build_bubblewrap(writable: Sequence[str], network: bool) -> Optional[SandboxWrapper]:
    exe = shutil.which("bwrap")
    if not exe:
        return None
    argv = [
        exe,
        "--die-with-parent",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
    ]
    for p in writable:
        if os.path.exists(p):
            argv += ["--bind", p, p]
    if not network:
        argv += ["--unshare-net"]
    return SandboxWrapper(
        backend="bubblewrap",
        argv_prefix=argv,
        writable_paths=list(writable),
        network=network,
    )


def build_wrapper(
    writable_paths: Optional[Sequence[str]] = None,
    network: bool = False,
    include_tmp: bool = True,
) -> Optional[SandboxWrapper]:
    """Build a containment wrapper for this platform, or ``None``.

    ``None`` means *no containment is available* -- callers must not pretend
    otherwise.  This does not probe; use :func:`probe_enforcement` for that.
    """
    paths = [_resolve(p) for p in (writable_paths or [os.getcwd()])]
    # A temp dir is normally needed: pip, compilers and test runners all use it.
    # ``include_tmp=False`` is used by the enforcement probe, which must place
    # its escape target somewhere genuinely outside the writable set.
    if include_tmp:
        tmp = _resolve(tempfile.gettempdir())
        if tmp not in paths:
            paths.append(tmp)

    system = platform.system()
    if system == "Darwin":
        return _build_seatbelt(paths, network)
    if system == "Linux":
        return _build_bubblewrap(paths, network)
    return None


def describe_backend() -> str:
    """Human-readable name of the backend that would be used, or ``none``."""
    system = platform.system()
    if system == "Darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if system == "Linux" and shutil.which("bwrap"):
        return "bubblewrap"
    return "none"


_PROBE_CACHE: Optional[tuple] = None


def reset_probe_cache() -> None:
    global _PROBE_CACHE
    _PROBE_CACHE = None


def probe_enforcement() -> tuple:
    """Actually verify the backend blocks a write outside the writable set.

    Returns ``(enforcing: bool, backend: str, detail: str)``.  Cached per
    process because it spawns a child.

    This exists because a wrapper that *looks* configured but does not enforce
    is the worst outcome: callers would run untrusted commands believing they
    were jailed.  So we measure instead of assuming.
    """
    global _PROBE_CACHE
    if _PROBE_CACHE is not None:
        return _PROBE_CACHE

    backend = describe_backend()
    if backend == "none":
        _PROBE_CACHE = (False, "none", "no OS sandbox backend on this platform")
        return _PROBE_CACHE

    workdir = tempfile.mkdtemp(prefix="praisonai_sbprobe_ws_")
    outside_dir = tempfile.mkdtemp(prefix="praisonai_sbprobe_out_")
    target = os.path.join(outside_dir, "escaped.txt")
    canary = os.path.join(workdir, "canary.txt")
    try:
        wrapper = build_wrapper(
            writable_paths=[workdir], network=False, include_tmp=False
        )
        if wrapper is None:
            _PROBE_CACHE = (False, backend, "wrapper could not be built")
            return _PROBE_CACHE
        # The probe writes an in-jail canary AND attempts an out-of-jail escape
        # in the same child. The escape target sits outside every writable path
        # (gettempdir() is auto-added as writable, so a nested dir is used that
        # bubblewrap/seatbelt would only expose if enforcement is absent).
        #
        # The canary is the guard against a false positive: if ``bwrap`` cannot
        # create namespaces or ``sandbox-exec`` rejects its profile, the wrapper
        # exits *before* running the child. The escape file is then absent not
        # because containment blocked it but because nothing ran. Requiring the
        # canary to exist proves the child actually executed inside the jail, so
        # the missing escape file can be trusted as real enforcement.
        script = (
            f"printf canary > {canary}; "
            f"printf escaped > {target}"
        )
        try:
            with wrapper:
                argv = wrapper.wrap(["/bin/sh", "-c", script])
                subprocess.run(
                    argv, cwd=workdir, capture_output=True, timeout=20, text=True
                )
        except (OSError, subprocess.SubprocessError) as exc:
            _PROBE_CACHE = (False, backend, f"probe failed to run: {exc}")
            return _PROBE_CACHE

        ran = os.path.exists(canary)
        escaped = os.path.exists(target)
        if not ran:
            _PROBE_CACHE = (
                False,
                backend,
                f"{backend} wrapper did not run the probe child (in-jail write "
                f"never happened); treating as unavailable rather than enforcing",
            )
        elif escaped:
            _PROBE_CACHE = (
                False,
                backend,
                f"{backend} did not block a write outside the writable set",
            )
        else:
            _PROBE_CACHE = (True, backend, f"{backend} blocked an out-of-jail write")
        return _PROBE_CACHE
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(outside_dir, ignore_errors=True)

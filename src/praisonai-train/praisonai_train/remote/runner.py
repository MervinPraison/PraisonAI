"""Train on another machine over SSH — preflight, ship, run, tail, fetch, stop.

This is the implementation the ``praisonai-train remote`` CLI wraps. It speaks
plain ``ssh``/``scp`` through :mod:`subprocess` so there is **no third-party
dependency**: any host reachable from ``~/.ssh/config`` works.

The design keeps one guarantee above all: a run **outlives the SSH session that
started it**. ``start`` launches training under ``nohup`` in a detached process
group and returns a :class:`RemoteRun` handle immediately; a dropped laptop
connection therefore never kills training, and the run id in the handle is
enough to reattach (:meth:`RemoteRunner.tail`), inspect (:meth:`status`),
retrieve (:meth:`fetch`) or kill it (:meth:`stop`) later.

Nothing here imports anything heavy; the module is safe to import from the CLI
without pulling in torch or unsloth.
"""
from __future__ import annotations

import pathlib
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional


class RemoteError(RuntimeError):
    """A remote operation could not be completed.

    Raised for the failures a caller can act on — an unready host, a refused
    start, a missing artifact — as opposed to programmer errors. The CLI turns
    these into a clear message and a non-zero exit rather than a traceback.
    """


# --------------------------------------------------------------------------- #
# Low-level SSH plumbing
# --------------------------------------------------------------------------- #
# Batch mode never prompts (a hung password prompt in CI is worse than a clean
# failure); a short connect timeout keeps an unreachable host from wedging.
_SSH_OPTS: List[str] = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=accept-new",
]


@dataclass
class _Completed:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class RemoteHost:
    """One SSH destination, addressed by its ``~/.ssh/config`` alias.

    Resolving ``~`` in the workdir is done **once, on the host**, so every
    subsequent command can use an absolute path and the CLI can build run
    directories without guessing the remote home.
    """

    alias: str
    python: str = "python3"
    workdir: str = "~/.praisonai-train"
    _resolved_workdir: Optional[str] = field(default=None, init=False, repr=False)

    def run(self, command: str, timeout: Optional[int] = None) -> _Completed:
        """Run a shell ``command`` on the host and capture its output."""
        argv = ["ssh", *_SSH_OPTS, self.alias, command]
        return self._exec(argv, timeout=timeout)

    def check(self, command: str, timeout: Optional[int] = None) -> str:
        """Like :meth:`run`, but raise :class:`RemoteError` on non-zero exit."""
        done = self.run(command, timeout=timeout)
        if not done.ok:
            detail = (done.stderr or done.stdout or "").strip()
            raise RemoteError(f"{self.alias}: `{command}` failed: {detail}")
        return done.stdout

    def resolve_workdir(self) -> str:
        """Absolute working directory on the host, expanded and cached."""
        if self._resolved_workdir is None:
            # Quoting the workdir stops the remote shell expanding `~`, so a
            # directory literally named `~` is created and every derived path
            # lands there. The workdir has to reach the shell unquoted --
            # validate it (same rule as settings.validate) so it stays safe.
            if not re.fullmatch(r"~?[A-Za-z0-9._/-]*", self.workdir):
                raise RemoteError(
                    f"{self.alias}: workdir {self.workdir!r} may only contain "
                    "letters, digits and ._-/~ -- it is expanded by the remote "
                    "shell."
                )
            # `cd ... && pwd` expands ~ using the host's own shell. `-m 700`
            # because the run directory holds the shipped config and any
            # dataset; a shared box's umask should not decide who can read them.
            # `--` ends option parsing so a workdir like `-p` is treated as a
            # path, not a flag; `~` is expanded by the shell before either
            # command sees it, so the guard never breaks tilde expansion.
            expanded = self.run(
                f"mkdir -p -m 700 -- {self.workdir} && "
                f"cd -- {self.workdir} && pwd"
            )
            if not expanded.ok:
                raise RemoteError(
                    f"{self.alias}: could not resolve workdir "
                    f"{self.workdir!r}: {(expanded.stderr or '').strip()}"
                )
            self._resolved_workdir = expanded.stdout.strip() or self.workdir
        return self._resolved_workdir

    @staticmethod
    def _exec(argv: List[str], timeout: Optional[int] = None) -> _Completed:
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout,
            )
        except FileNotFoundError as exc:  # ssh/scp not installed
            raise RemoteError(f"{argv[0]} not found on this machine") from exc
        except subprocess.TimeoutExpired as exc:
            raise RemoteError(f"timed out running {argv[0]}") from exc
        return _Completed(proc.returncode, proc.stdout or "", proc.stderr or "")


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #
@dataclass
class RemotePreflight:
    """The verdict of a readiness check, with the reason it failed if it did.

    ``ok`` being false is an *answer*, not an error: the useful part is
    :meth:`why_not`, which the CLI shows as remediation.
    """

    ok: bool
    reasons: List[str] = field(default_factory=list)

    def why_not(self) -> Optional[str]:
        if self.ok:
            return None
        return "; ".join(self.reasons) if self.reasons else "host is not ready"


# --------------------------------------------------------------------------- #
# A single run
# --------------------------------------------------------------------------- #
@dataclass
class RemoteRun:
    """A handle to one training run on a host — enough to reattach to it later.

    Deliberately a plain data holder: the id and paths survive the process that
    started the run, so they can be reconstructed from just ``host`` +
    ``run_id`` (see the CLI's ``tail``/``status``/``stop``).
    """

    host: str
    run_id: str
    remote_dir: str
    log_path: str

    @property
    def pid_path(self) -> str:
        return f"{self.remote_dir}/train.pid"

    @property
    def status_path(self) -> str:
        return f"{self.remote_dir}/status"


# A run id names a directory on the far host and is interpolated into remote
# paths. Quoting makes it safe; this makes it *sane*, so a typo fails here
# rather than creating a directory called `x;touch /tmp/pwned`.
_RUN_ID_OK = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_run_id(run_id: str) -> str:
    """Reject anything that is not a plain identifier."""
    if not isinstance(run_id, str) or not _RUN_ID_OK.match(run_id):
        raise RemoteError(
            f"run id {run_id!r} is not usable: letters, digits, dot, dash and "
            "underscore only, starting with a letter or digit, up to 64 chars.")
    return run_id


def validate_remote_rel(path: str) -> str:
    """Reject a fetch path that climbs out of the run directory.

    `fetch <run> ../../../../etc/passwd` passed the existence check and copied
    the file back, because the path is only ever joined, never checked.
    """
    if not isinstance(path, str) or not path.strip():
        raise RemoteError("nothing to fetch: give a path inside the run directory")
    if path.startswith("/") or ".." in pathlib.PurePosixPath(path).parts:
        raise RemoteError(
            f"{path!r} points outside the run directory. Fetch paths are "
            "relative to it, e.g. 'lora_model' or 'train.log'.")
    return path


def _new_run_id() -> str:
    # Sortable and unique enough for a per-user host; no dependency on uuid's
    # opacity when a timestamp reads better in `ls`.
    return f"run-{int(time.time())}"


# --------------------------------------------------------------------------- #
# The runner
# --------------------------------------------------------------------------- #
class RemoteRunner:
    """Drive a training run on a remote GPU host over SSH.

    Construct one per host. Every method is independent and reconnects, so a
    runner can be discarded and rebuilt from ``host`` + ``run_id`` at any time —
    which is exactly what the CLI does when reattaching to a run it did not
    start.
    """

    def __init__(self, alias: str, python: str = "python3",
                 workdir: str = "~/.praisonai-train"):
        self.host = RemoteHost(alias=alias, python=python, workdir=workdir)

    # -- readiness -------------------------------------------------------- #
    def preflight(self, expect_gpus: int = 1) -> RemotePreflight:
        """Check the host can actually train before shipping anything to it.

        Verifies reachability, an importable Python, and that ``nvidia-smi``
        reports at least ``expect_gpus`` GPUs. Any shortfall is collected into
        the returned verdict rather than raised: "not ready" is an answer.
        """
        reasons: List[str] = []

        reachable = self.host.run("echo ok")
        if not reachable.ok:
            reasons.append(
                f"cannot reach {self.host.alias}: "
                f"{(reachable.stderr or 'ssh failed').strip()}"
            )
            # Nothing else is meaningful if we can't even connect.
            return RemotePreflight(ok=False, reasons=reasons)

        py = self.host.run(f"{shlex.quote(self.host.python)} --version")
        if not py.ok:
            reasons.append(
                f"{self.host.python} not usable on {self.host.alias}"
            )

        gpus = self._count_gpus()
        if gpus < expect_gpus:
            reasons.append(
                f"needs {expect_gpus} GPU(s), found {gpus} "
                f"(no CUDA GPU visible to nvidia-smi)"
                if gpus == 0 else
                f"needs {expect_gpus} GPU(s), found {gpus}"
            )

        return RemotePreflight(ok=not reasons, reasons=reasons)

    def _count_gpus(self) -> int:
        probe = self.host.run(
            "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || true"
        )
        if not probe.ok:
            return 0
        return len([ln for ln in probe.stdout.splitlines() if ln.strip()])

    # -- start ------------------------------------------------------------ #
    def start(self, config_path: Path, dataset_path: Optional[Path] = None,
              run_id: Optional[str] = None, expect_gpus: int = 1,
              env: Optional[dict] = None) -> RemoteRun:
        """Ship the job and launch it detached; return a handle immediately.

        Refuses (with :class:`RemoteError`) if the host fails preflight, so a
        job is never shipped to a box that cannot run it. The training process
        is started under ``nohup`` in its own session, so it survives this SSH
        connection closing.
        """
        config_path = Path(config_path)
        if not config_path.exists():
            raise RemoteError(f"config not found: {config_path}")

        ready = self.preflight(expect_gpus=expect_gpus)
        if not ready.ok:
            raise RemoteError(f"{self.host.alias}: {ready.why_not()}")

        rid = validate_run_id(run_id) if run_id else _new_run_id()
        base = self.host.resolve_workdir()
        remote_dir = f"{base}/{rid}"
        run = RemoteRun(
            host=self.host.alias, run_id=rid, remote_dir=remote_dir,
            log_path=f"{remote_dir}/train.log",
        )

        self.host.check(f"mkdir -p {shlex.quote(remote_dir)}")
        self._ship(config_path, f"{remote_dir}/config.yaml")
        dataset_arg = ""
        if dataset_path is not None:
            dataset_path = Path(dataset_path)
            if not dataset_path.exists():
                raise RemoteError(f"dataset not found: {dataset_path}")
            self._ship(dataset_path, f"{remote_dir}/{dataset_path.name}")
            dataset_arg = f" {shlex.quote(dataset_path.name)}"

        launched = self.host.run(self._launch_script(run, dataset_arg, env))
        if not launched.ok:
            detail = (launched.stderr or launched.stdout or "").strip()
            raise RemoteError(f"{self.host.alias}: could not start run: {detail}")
        return run

    def _launch_script(self, run: RemoteRun, dataset_arg: str,
                       env: Optional[dict]) -> str:
        exports = ""
        if env:
            exports = "".join(
                f"export {k}={shlex.quote(str(v))}; " for k, v in env.items()
            )
        cd = f"cd {shlex.quote(run.remote_dir)}"
        train = (
            f"{shlex.quote(self.host.python)} -m praisonai_train "
            f"llm{dataset_arg} --config config.yaml"
        )
        # Record status so `status` can tell how it ended; write the pid so
        # `stop` can signal the whole process group. `setsid`, where present,
        # makes the recorded process a group leader (pgid == pid) in its own
        # session, so its children -- dataloader workers, torchrun ranks -- are
        # in one group `stop` can take down together. `setsid` is not on macOS,
        # so fall back to plain `nohup`; `stop` resolves the real pgid on the
        # host at kill time, so the group is signalled either way. `</dev/null`
        # releases ssh's stdin so the launch returns immediately instead of
        # holding the connection open for the run's duration. The inner program
        # is quoted as one argument so a run dir with whitespace or shell
        # metacharacters can't break the command apart.
        inner = (
            f"nohup sh -c '{train} > train.log 2>&1; "
            f"echo $? > status' </dev/null >/dev/null 2>&1 & "
            f"echo $! > {shlex.quote(run.pid_path)}"
        )
        body = (
            f"{exports}{cd} && "
            f"if command -v setsid >/dev/null 2>&1; then "
            f"setsid sh -c {shlex.quote(inner)} </dev/null; "
            f"else {inner}; fi"
        )
        return body

    # -- tail ------------------------------------------------------------- #
    def tail(self, run: RemoteRun, on_line: Callable[[str], None],
             poll_seconds: float = 1.0) -> None:
        """Stream the run's log until the run ends, one line per callback.

        Follows the log with ``tail -F`` so it survives log rotation, and stops
        when the status file appears (the run has recorded its exit).
        """
        # `tail -n +1 -F` replays what's there, then follows. We stop once the
        # status file exists AND tail has caught up.
        argv = [
            "ssh", *_SSH_OPTS, run.host,
            f"touch {shlex.quote(run.log_path)}; "
            f"tail -n +1 -F {shlex.quote(run.log_path)} & "
            f"tp=$!; "
            f"while [ ! -f {shlex.quote(run.status_path)} ]; do sleep "
            f"{poll_seconds}; done; sleep {poll_seconds}; kill $tp 2>/dev/null",
        ]
        try:
            proc = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except FileNotFoundError as exc:
            raise RemoteError("ssh not found on this machine") from exc
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                on_line(line.rstrip("\n"))
        finally:
            proc.stdout.close()
            proc.wait()

    # -- status ----------------------------------------------------------- #
    def status(self, run: RemoteRun) -> str:
        """Whether a run is still going, and how it ended if not."""
        probe = self.host.run(
            f"if [ -f {shlex.quote(run.status_path)} ]; then "
            f"  code=$(cat {shlex.quote(run.status_path)}); "
            f"  [ \"$code\" = 0 ] && echo completed || echo \"failed (exit $code)\"; "
            f"elif [ -f {shlex.quote(run.pid_path)} ] && "
            f"     kill -0 $(cat {shlex.quote(run.pid_path)}) 2>/dev/null; then "
            f"  echo running; "
            f"else echo unknown; fi"
        )
        if not probe.ok:
            return "unknown"
        return probe.stdout.strip() or "unknown"

    # -- fetch ------------------------------------------------------------ #
    def fetch(self, run: RemoteRun, remote_rel: str, dest: Path) -> Path:
        """Bring an artifact back from the run directory to ``dest`` locally."""
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        remote_rel = validate_remote_rel(remote_rel)
        remote_abs = f"{run.remote_dir}/{remote_rel}"

        exists = self.host.run(f"test -e {shlex.quote(remote_abs)}")
        if not exists.ok:
            raise RemoteError(
                f"{run.host}: nothing to fetch at {remote_rel} "
                f"(run {run.run_id})"
            )

        argv = ["scp", *_SSH_OPTS, "-r",
                f"{run.host}:{remote_abs}", str(dest)]
        done = RemoteHost._exec(argv)
        if not done.ok:
            detail = (done.stderr or done.stdout or "").strip()
            raise RemoteError(f"{run.host}: fetch failed: {detail}")
        return dest / Path(remote_rel).name

    # -- stop ------------------------------------------------------------- #
    def stop(self, run: RemoteRun) -> bool:
        """Stop a run. Return True only if the run is actually gone.

        The recorded pid is the wrapper shell, not the trainer: its children
        (dataloader workers, torchrun ranks) share its process group and each
        hold the GPU. Signalling the pid alone leaves them running, reparented
        to init. So we resolve the group on the host and signal ``-$pgid``,
        then *re-probe the whole group* -- a wrapper can exit while a child
        survives SIGTERM, so checking only the recorded pid would report
        success while paid GPU work continues; reporting success for a ``kill``
        that was merely issued would likewise let a UI label a live run
        "cancelled".

        Refuses to signal our own group (a defensive guard against a corrupt
        pid file resolving to the ssh session's group), and raises if any
        process in the group survives the signal rather than lying about it.
        """
        result = self.host.run(
            f"if [ ! -f {shlex.quote(run.pid_path)} ]; then echo not-running; "
            f"else "
            f"  pid=$(cat {shlex.quote(run.pid_path)}); "
            f"  if ! kill -0 $pid 2>/dev/null; then echo not-running; "
            f"  else "
            f"    g=$(ps -o pgid= -p $pid 2>/dev/null | tr -d ' '); "
            f"    if [ -z \"$g\" ]; then echo not-running; "
            f"    elif [ \"$g\" = \"$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')\" ]; then "
            f"      echo refused; "
            f"    else "
            f"      kill -TERM -\"$g\" 2>/dev/null; "
            f"      sleep 2; "
            f"      alive=$(ps -o pgid= -o pid= -A 2>/dev/null "
            f"        | awk -v g=\"$g\" '$1==g{{print $2}}'); "
            f"      if [ -n \"$alive\" ]; then echo still-running; "
            f"      else echo stopped; fi; "
            f"    fi; "
            f"  fi; "
            f"fi"
        )
        if not result.ok:
            raise RemoteError(
                f"{run.host}: could not stop {run.run_id}: "
                f"{(result.stderr or '').strip()}"
            )
        verdict = result.stdout.strip()
        if verdict == "refused":
            raise RemoteError(
                f"{run.host}: refused to stop {run.run_id}: its pid resolves "
                f"to this session's own process group"
            )
        if verdict == "still-running":
            raise RemoteError(
                f"{run.host}: {run.run_id} did not stop: the process is still "
                f"running after SIGTERM"
            )
        return verdict == "stopped"

    # -- helpers ---------------------------------------------------------- #
    def _ship(self, local: Path, remote_abs: str) -> None:
        # The remote half of an scp target is expanded by a shell on the far
        # side, so it has to be quoted for that shell -- not just passed as one
        # argv element. Without this, --run-id 'x;touch /tmp/pwned' executed.
        argv = ["scp", *_SSH_OPTS, str(local),
                f"{self.host.alias}:{shlex.quote(remote_abs)}"]
        done = RemoteHost._exec(argv)
        if not done.ok:
            detail = (done.stderr or done.stdout or "").strip()
            raise RemoteError(
                f"{self.host.alias}: could not ship {local.name}: {detail}"
            )

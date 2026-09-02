"""Running a fine-tune from the desktop app, and reporting on it.

The engine had no job model at all. It is a ThreadingHTTPServer where every
request is a turn that starts, streams and ends -- fine for chat, wrong for
something that runs for hours, must survive the window closing, and has to be
resumable after a reconnect. So a training run is a *subsystem*, not a route.

Three decisions worth stating, each taken because the alternative was worse:

* **One run at a time.** Two fine-tunes on one GPU do not co-exist; they OOM.
  `start` refuses while a run is live rather than queueing, because a queue
  implies a scheduler nobody asked for.
* **Progress is a ring buffer, not a stream.** SSE with `Last-Event-ID` needs
  history to replay, and a closed laptop lid must not lose the run. Events are
  kept and replayed from a cursor, so reconnecting is reading, not subscribing.
* **The subprocess owns the truth.** Status is derived from the process and its
  log, never from what the client last heard, so a client that missed the
  ending still learns how it ended.

Everything here is pure or filesystem-only; the HTTP layer is in server.py.
"""

from __future__ import annotations

import json
import collections
import os
import re
import shlex
import signal
import subprocess
import threading
import time

# What a run can be. `stopping` exists because SIGTERM is not instant and a UI
# that shows "running" through a five-second teardown looks broken.
# How much of a run is kept in memory. The log file is the full record.
MAX_METRICS = 5000           # points in the loss series
MAX_HISTORY = 50             # finished runs listed in the history pane

PENDING, RUNNING, STOPPING, DONE, FAILED, CANCELLED = (
    "pending", "running", "stopping", "done", "failed", "cancelled")
TERMINAL = frozenset({DONE, FAILED, CANCELLED})

# trl/transformers print one dict per logging step. This is the only line shape
# worth parsing; everything else is noise the log view can show verbatim.
_METRIC = re.compile(
    r"\{'loss':\s*([0-9.eE+-]+).*?'learning_rate':\s*([0-9.eE+-]+)"
    r".*?'epoch':\s*([0-9.eE+-]+)")
_STEP = re.compile(r"(\d+)\s*/\s*(\d+)\s*\[")


def parse_metric(line):
    """Pull (loss, lr, epoch) out of a trainer log line, or None.

    Returns None rather than partial values: a chart plotting a loss with no
    step is worse than a chart with a gap.
    """
    m = _METRIC.search(line or "")
    if not m:
        return None
    try:
        return {"loss": float(m.group(1)), "learning_rate": float(m.group(2)),
                "epoch": float(m.group(3))}
    except (TypeError, ValueError):
        return None


def parse_progress(line):
    """Pull (step, total) out of a tqdm line, or None."""
    m = _STEP.search(line or "")
    if not m:
        return None
    step, total = int(m.group(1)), int(m.group(2))
    if total <= 0 or step > total:
        return None          # a malformed bar must not produce 400% progress
    return {"step": step, "total": total}


IS_WINDOWS = os.name == "nt"

# Reserved DOS device names. They are alphanumeric, so an allowlist cannot see
# them, and `os.makedirs("CON")` on Windows fails or resolves to a device.
_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)])

_SAFE_RUN_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def split_command(text, windows=None):
    """Split a command line the way the running platform's shell would.

    `shlex.split` defaults to POSIX rules, where a backslash escapes the next
    character -- so a Windows interpreter path is silently destroyed:

        C:\\Users\\me\\envs\\cuda\\Scripts\\python.exe
            -> C:Usersmeenvscudascriptspython.exe

    and the user sees only "could not start the trainer". Non-POSIX mode keeps
    the backslashes but leaves the quotes attached, so they are stripped here.
    """
    windows = IS_WINDOWS if windows is None else windows
    if not windows:
        return shlex.split(text)
    tokens = shlex.split(text, posix=False)
    return [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'" else t
            for t in tokens]


def validate_run_id(run_id):
    """A run id becomes a directory name, so it is checked, not trusted.

    The engine listens on loopback with no auth -- that is the app's existing
    design for every route -- which means any local process can POST here. An
    id like `../../../../Library/LaunchAgents/x` would have `makedirs` write
    outside the runs directory. An allowlist is used rather than stripping
    `..`, because stripping invites the next encoding that gets through.
    """
    run_id = str(run_id or "")
    stem = run_id.split(".", 1)[0].upper()
    if stem in _RESERVED:
        raise ValueError(
            f"{run_id!r} is a reserved device name on Windows; "
            "a directory cannot be created with it")
    if run_id.endswith("."):
        # Windows strips a trailing dot, so "run-1." and "run-1" would become
        # one directory and two runs would overwrite each other's logs.
        raise ValueError(f"a run id may not end in a dot; got {run_id!r}")
    if not _SAFE_RUN_ID.match(run_id) or run_id in {".", ".."}:
        raise ValueError(
            "run id must be 1-64 characters of letters, digits, dot, dash or "
            f"underscore, starting alphanumeric; got {run_id!r}")
    return run_id


class Run:
    """One training job. Owns its process, its log and its event history."""

    MAX_EVENTS = 4000        # ~a day of logging at one line every 20s

    def __init__(self, run_id, config_path, log_path):
        self.id = run_id
        self.config_path = str(config_path)
        self.log_path = str(log_path)
        self.state = PENDING
        self.started = time.time()
        self.ended = None
        self.error = None
        self.step = 0
        self.total = 0
        # A tail, not an archive. At 20k logging steps the full series is
        # several megabytes per run, held forever by a process that is meant
        # to stay open for days; the chart only ever draws the recent shape
        # and train.log keeps the complete record.
        self.metrics = collections.deque(maxlen=MAX_METRICS)
        self.events = []             # [(cursor, kind, payload)]
        self._next_cursor = 0        # never derived from len(events): see emit
        self._proc = None
        # The child's pid, recorded on disk so a *later* engine process can
        # find a run it never spawned: _proc is unpicklable and dies with us,
        # but the pid outlives the restart and is how stop() reaches an
        # adopted run.
        self.pid = None
        # A pid alone is ambiguous after a restart: the OS may have handed it to
        # an unrelated process. The start time pins which process the pid meant,
        # exactly as src-tauri/src/adopt.rs does for the engine.
        self.pid_start = None
        self._lock = threading.Lock()

    # -- event history --------------------------------------------------
    def emit(self, kind, payload=None):
        with self._lock:
            # A counter, not len(self.events). Deriving the cursor from the
            # list length looks equivalent and is not: once eviction starts,
            # the length stops growing, every later event is handed the same
            # cursor, and `since()` returns nothing forever -- a live run whose
            # UI silently stops updating. Its own test caught this.
            cursor = self._next_cursor
            self._next_cursor += 1
            self.events.append((cursor, kind, payload or {}))
            if len(self.events) > self.MAX_EVENTS:
                # Drop from the front, keeping cursors monotonic so a client
                # that reconnects with an evicted cursor is told to resync
                # rather than silently handed the wrong events.
                self.events = self.events[-self.MAX_EVENTS:]

    def since(self, cursor):
        """Events after `cursor`, and whether history was lost."""
        with self._lock:
            if not self.events:
                return [], False
            oldest = self.events[0][0]
            gap = cursor + 1 < oldest
            return [e for e in self.events if e[0] > cursor], gap

    # -- lifecycle -------------------------------------------------------
    def summary(self):
        return {
            "id": self.id, "state": self.state, "step": self.step,
            "total": self.total, "started": self.started, "ended": self.ended,
            "error": self.error,
            "elapsed": round((self.ended or time.time()) - self.started, 1),
            "last_loss": self.metrics[-1]["loss"] if self.metrics else None,
        }

    def finish(self, state, error=None):
        if self.state in TERMINAL:
            return               # first ending wins; a late reap cannot relabel
        self.state = state
        self.error = error
        self.ended = time.time()
        self.emit("end", self.summary())


class Trainer:
    """The one live run, if any, and the history of finished ones."""

    def __init__(self, home, python, command_builder=None):
        self.home = home
        self.python = python
        # Tests override the *command*, never the spawn. An earlier version let
        # tests supply a whole launcher, and every one of them re-implemented
        # `start_new_session=True` -- so deleting it from the real spawn broke
        # nothing, and the process-group guarantee was untested while looking
        # covered. Substituting argv keeps the mechanics under test.
        self.command_builder = command_builder
        self.dir = os.path.join(str(home), "runs")
        self.current = None
        # Finished runs are kept so the history list can show them, but not
        # without limit -- each retains its event ring and metric series.
        self.history = collections.deque(maxlen=MAX_HISTORY)
        self._lock = threading.Lock()
        # Rebuild what an earlier engine process left on disk. Without this a
        # restart during a run reports the run as never having happened: it
        # vanishes from history, stop() has nothing to stop, and start()
        # cheerfully launches a second trainer beside the live one -- the OOM
        # that "one GPU runs one job" exists to refuse.
        self._reload()

    # -- surviving a restart --------------------------------------------
    def _state_path(self, run_id):
        return os.path.join(self.dir, run_id, "run.json")

    def _persist(self, run):
        """Enough on disk to answer 'is a job on the GPU right now'.

        Only config.yaml and train.log were ever written; neither records the
        state or the pid, so a new process could not tell a live run from a
        finished one. Best-effort: a run that trains but cannot write its state
        file is still better than one that refuses to start.

        The write is atomic -- a temp file in the same directory, fsynced, then
        os.replace. A plain open("w") truncates first, so an engine killed mid
        json.dump leaves empty or half-written JSON; _reload then skips that
        record and the live run disappears from history, becomes unreachable
        through stop(), and no longer refuses a second trainer. os.replace is
        atomic on POSIX and Windows, so a reader only ever sees the old file or
        the whole new one.
        """
        path = self._state_path(run.id)
        tmp = f"{path}.{os.getpid()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({**run.summary(), "pid": run.pid,
                             "pid_start": run.pid_start}, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _existing_ids(self):
        """Run directories on disk, whether or not this process created them."""
        try:
            return [name for name in os.listdir(self.dir)
                    if os.path.isdir(os.path.join(self.dir, name))]
        except OSError:
            return []

    def _reload(self):
        """Rebuild history, adopting a run whose process is still alive.

        A run the new process cannot see is not 'missing' -- it is either still
        on the GPU (adopt it, so stop() can reach it) or it was interrupted
        (say so). Reporting neither is how a second fine-tune got started
        beside a live one.
        """
        for name in sorted(self._existing_ids()):
            try:
                with open(self._state_path(name), encoding="utf-8") as fh:
                    saved = json.load(fh)
            except (OSError, ValueError):
                continue
            run_dir = os.path.join(self.dir, name)
            run = Run(name, os.path.join(run_dir, "config.yaml"),
                      os.path.join(run_dir, "train.log"))
            run.state = saved.get("state", FAILED)
            run.step, run.total = saved.get("step", 0), saved.get("total", 0)
            run.started = saved.get("started", run.started)
            run.ended, run.error = saved.get("ended"), saved.get("error")
            run.pid = saved.get("pid")
            run.pid_start = saved.get("pid_start")
            if run.state not in TERMINAL:
                if run.pid and _same_process(run.pid, run.pid_start):
                    run.state = RUNNING
                    self.current = run          # stop() signals run.pid's group
                else:
                    run.finish(FAILED,
                               "the engine restarted while this run was live")
                    self._persist(run)
            self.history.appendleft(run)

    # -- starting --------------------------------------------------------
    def start(self, config, run_id=None):
        """Write the config, spawn the trainer, and stream its output.

        Refuses while a run is live. Two fine-tunes on one GPU do not co-exist
        -- they OOM -- and queueing would imply a scheduler nobody asked for,
        so the honest answer is no.
        """
        with self._lock:
            if self.current and self.current.state not in TERMINAL:
                raise RuntimeError(
                    f"run {self.current.id} is {self.current.state}. "
                    "Stop it before starting another; one GPU runs one job.")
            # Settle the id before creating anything.
            #
            # Two runs must never share a directory: they overwrite each
            # other's config.yaml and interleave into one train.log. Two ways
            # that happened -- an auto-generated id had one-second resolution,
            # so two runs started in the same second collided; and ids differing
            # only in case are the same directory on macOS and Windows, whose
            # filesystems are case-insensitive.
            if run_id:
                run_id = validate_run_id(run_id)
                if self._id_taken(run_id):
                    raise ValueError(
                        f"a run named {run_id!r} already exists (run ids are "
                        "compared case-insensitively, because directories are)")
            else:
                run_id = self._unused_id()

            run_dir = os.path.join(self.dir, run_id)
            os.makedirs(run_dir, exist_ok=True)
            config_path = os.path.join(run_dir, "config.yaml")
            _write_config(config_path, config)
            run = Run(run_id, config_path, os.path.join(run_dir, "train.log"))
            self.current = run
            # appendleft, not insert(0): insert on a *full* bounded deque
            # raises IndexError("deque already at its maximum size"), so the
            # 51st run would have failed to start. appendleft evicts from the
            # far end, which is the oldest run -- what the cap is for.
            self.history.appendleft(run)

        # Record the run as pending *before* the supervisor thread exists.
        # start() returns the moment the thread is created, so an engine that
        # exits between here and the first post-spawn _persist would otherwise
        # leave a child alive with no run.json: _reload skips it, stop() cannot
        # reach it, and start() launches a second trainer beside it. A pending
        # record with no pid is adopted as failed on the next boot, which is
        # the honest reading of "spawned, engine died, pid unknown".
        self._persist(run)
        run.emit("start", {"id": run.id, "config": config_path})
        threading.Thread(target=self._supervise, args=(run,), daemon=True).start()
        return run

    def _id_taken(self, run_id):
        """Whether this id would land on an existing run or directory."""
        folded = run_id.casefold()
        if any(other.id.casefold() == folded for other in self.history):
            return True
        try:
            existing = os.listdir(self.dir)
        except OSError:
            return False       # nothing has been created yet
        return any(name.casefold() == folded for name in existing)

    def _unused_id(self):
        """A generated id that is free, even for two runs in the same second."""
        stamp = int(time.time())
        candidate = f"run-{stamp}"
        suffix = 2
        while self._id_taken(candidate):
            candidate = f"run-{stamp}-{suffix}"
            suffix += 1
        return candidate

    def _command(self, run):
        """The argv that runs the fine-tune.

        `PRAISONAI_TRAIN_CMD` overrides the launcher because the trainer need
        not live in the engine's venv: praisonai-train pulls torch and unsloth,
        which a user may well keep in a separate CUDA-matched environment, and
        the desktop engine deliberately stays stdlib-only. `--config <path>` is
        always appended, so the override chooses the interpreter, not the
        contract.
        """
        if self.command_builder:
            return self.command_builder(run)
        override = os.environ.get("PRAISONAI_TRAIN_CMD", "").strip()
        base = (split_command(override) if override
                else [self.python, "-m", "praisonai_train", "llm"])
        return base + ["--config", run.config_path]

    def _spawn(self, run):
        return subprocess.Popen(
            self._command(run),
            cwd=os.path.dirname(run.config_path),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            # text=True alone decodes in the locale encoding -- cp1252 on a
            # default Windows box, ASCII under LC_ALL=C. unsloth's banner is
            # emoji, so the log becomes mojibake; worse, five cp1252 bytes are
            # undefined and raise *inside* the reader loop, freezing the log
            # and the loss chart while the run carries on to completion.
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            # Its own group, so stopping kills the trainer AND anything it
            # spawned. Signalling the pid alone leaves the real work running.
            **_new_process_group(),
        )

    @staticmethod
    def _process_group_kwargs():
        return _new_process_group()

    def _supervise(self, run):
        try:
            proc = self._spawn(run)
        except Exception as exc:                       # noqa: BLE001
            run.finish(FAILED, f"could not start the trainer: {exc}")
            # Persist the failure: start() left a pending record on disk, and
            # without this a restart would read that stale pending run (no pid)
            # as freshly interrupted rather than as the spawn failure it was.
            self._persist(run)
            return
        run._proc = proc
        run.pid = proc.pid
        # Read the fingerprint now, while the child is certainly still this
        # process: reading it at adoption time would fingerprint whoever holds
        # the pid then, which is the thing being guarded against.
        run.pid_start = _pid_start_time(proc.pid)
        # Written now, before the RUNNING transition, so a crash in the next
        # instruction still leaves a pid on disk for the next process to adopt
        # or reap rather than a run that looks like it never spawned.
        self._persist(run)
        # Honour a stop that arrived before the process existed.
        #
        # start() returns as soon as this thread is created, so there is a
        # window -- every millisecond between the HTTP reply and Popen
        # returning -- where stop() finds run._proc is None and has nothing to
        # signal. It recorded STOPPING and this line then overwrote it with
        # RUNNING: the user got {"ok": true} and a "stopping" pill, and the
        # fine-tune ran to completion and reported "done".
        with run._lock:
            stop_requested = run.state == STOPPING
            if not stop_requested:
                run.state = RUNNING
        if stop_requested:
            _terminate_group(proc)
        else:
            run.emit("state", {"state": RUNNING})
        self._persist(run)          # RUNNING (or STOPPING) is now on disk
        try:
            log = open(run.log_path, "a", encoding="utf-8")
        except OSError as exc:
            log = None
            run.emit("log", {"line": f"[log unavailable: {exc}]"})
        try:
            for line in proc.stdout:
                # The pipe is drained whatever happens to the log. Stopping the
                # loop leaves the child blocked on a full pipe and proc.wait()
                # blocked on the child, so the run never ends and every later
                # run is refused.
                if log is not None:
                    try:
                        log.write(line)
                        log.flush()   # the log is the full record only if it exists
                    except OSError as exc:
                        run.emit("log", {"line": f"[log stopped: {exc}]"})
                        log.close()
                        log = None
                try:
                    self._consume(run, line.rstrip("\n"))
                except Exception as exc:               # noqa: BLE001
                    run.emit("log", {"line": f"[reader error: {exc}]"})
        finally:
            if log is not None:
                # close() flushes, so a full disk or revoked directory can raise
                # here too. Swallow it: the pipe is already drained, and letting
                # it escape would skip proc.wait()/finish() and wedge the run --
                # the very failure this reader exists to prevent.
                try:
                    log.close()
                except OSError:
                    pass
        code = proc.wait()
        if run.state == STOPPING:
            run.finish(CANCELLED)
        elif code == 0:
            run.finish(DONE)
        else:
            run.finish(FAILED, _last_meaningful_line(run.log_path) or f"exit {code}")
        # Record the ending, so a restart after the run finishes reads it as
        # terminal rather than adopting a dead pid.
        self._persist(run)

    def _consume(self, run, line):
        run.emit("log", {"line": line})
        progress = parse_progress(line)
        if progress:
            run.step, run.total = progress["step"], progress["total"]
            run.emit("progress", progress)
        metric = parse_metric(line)
        if metric:
            metric["step"] = run.step
            run.metrics.append(metric)
            run.emit("metric", metric)

    # -- stopping --------------------------------------------------------
    def stop(self, run_id=None):
        run = self.current
        if not run or run.state in TERMINAL:
            return False
        if run_id and run_id != run.id:
            # Refuse to stop a different run than the one asked for: a stale
            # tab must not cancel the job someone started after it.
            raise RuntimeError(f"{run_id} is not the live run ({run.id})")
        with run._lock:
            if run.state in TERMINAL:
                return False        # it ended while we were deciding
            run.state = STOPPING
        run.emit("state", {"state": STOPPING})
        proc = run._proc
        if proc and proc.poll() is None:
            _terminate_group(proc)
            # _supervise is reading proc.stdout; it sees STOPPING, calls
            # finish(CANCELLED) and persists when the pipe closes.
        elif proc is None and run.pid:
            # An adopted run from a previous process: there is no _proc and no
            # supervisor reading its output, so this process owns the ending.
            # Signal the pid's group -- the group is what the original spawn
            # created -- then record the ending ourselves.
            _terminate_pid_group(run.pid)
            run.finish(CANCELLED)
            self._persist(run)
        # If proc is still None *and* there is no pid the run has not spawned
        # yet; _supervise sees STOPPING under the same lock and terminates it
        # on arrival.
        self._persist(run)
        return True

    def get(self, run_id):
        for run in self.history:
            if run.id == run_id:
                return run
        return None


# What each method needs beyond a model and a dataset.
#
# The trainer checks these too, but only inside train_model() -- which runs
# after prepare_model() has downloaded several gigabytes and loaded the model
# in 4-bit. Failing there means the user waits an hour to be told their config
# was never going to work. Everything checkable from the config alone is
# checked here, before anything is downloaded.
#
# Column requirements are NOT checked here: they depend on the dataset's
# contents, which we would have to fetch to know. They are named in the UI's
# per-method hint instead, and the trainer still enforces them.
METHOD_REQUIREMENTS = {
    "grpo": ("reward_funcs",),
}

# The columns each method expects, for the error message rather than a check.
METHOD_COLUMNS = {
    "cpt": ("text",),
    "dpo": ("prompt", "chosen", "rejected"),
    "orpo": ("prompt", "chosen", "rejected"),
    "cpo": ("prompt", "chosen", "rejected"),
    "kto": ("prompt", "completion", "label"),
    "reward": ("chosen", "rejected"),
}


def check_method_requirements(config):
    """Raise ValueError if this config cannot work, before anything is fetched."""
    method = (config.get("method") or "sft").lower()
    missing = [key for key in METHOD_REQUIREMENTS.get(method, ())
               if not config.get(key)]
    if missing:
        raise ValueError(
            f"{method} needs {', '.join(missing)}, which this form does not "
            f"collect -- run it from the command line instead")
    return method


def _new_process_group():
    """Popen kwargs that put the child in its own group, per platform.

    `start_new_session` is accepted and then *ignored* on Windows -- CPython's
    Windows `_execute_child` names the parameter `unused_start_new_session` and
    never reads it -- so relying on it there would silently lose the guarantee
    that stopping a run also stops what the run spawned.
    """
    if IS_WINDOWS:
        # getattr on both, so this branch can be exercised from a Mac test
        # rather than being the one path nobody runs until a user reports it.
        # CREATE_NO_WINDOW keeps a console from flashing: a Tauri app is a GUI
        # process with no console attached, so a bare Popen pops a black box.
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {"start_new_session": True}


def _taskkill_tree(pid):
    """Kill a process and everything it spawned, on Windows. True if it ran.

    Split out so the Windows path can be exercised from any platform: the
    branch that only ever runs on the one machine nobody tests on is exactly
    the branch that was wrong.
    """
    try:
        result = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _terminate_group(proc):
    """SIGTERM the child and everything it spawned -- and nothing else.

    The group is checked against our own before signalling. `_spawn` puts the
    child in a new session so they always differ, but if that ever regresses,
    `killpg` would deliver SIGTERM to the engine's own group and stopping a
    training run would kill the desktop app. Verified: removing the new-session
    flag makes this function shoot the test runner.
    """
    if IS_WINDOWS:
        # Windows has no process groups in the POSIX sense; os.getpgid and
        # os.killpg do not exist at all, and an AttributeError here would
        # escape stop() and wedge the run in "stopping" forever while the
        # trainer kept the GPU.
        #
        # This used to send CTRL_BREAK_EVENT, which was worse than useless.
        # That event is delivered through a console, and the trainer is spawned
        # with CREATE_NO_WINDOW precisely so it has none -- so send_signal
        # returned successfully, nothing died, and the fallback never ran. The
        # run reported "cancelled" while the fine-tune continued to completion
        # holding the GPU: the exact failure that stopping exists to prevent,
        # reported as a success. Every stop test failed on Windows and passed
        # on the two platforms anyone had run them on.
        #
        # taskkill /T walks the child tree, which is what killpg achieves on
        # POSIX; /F because a console-less child cannot be asked politely.
        if not _taskkill_tree(proc.pid) and proc.poll() is None:
            proc.kill()          # at least the trainer itself
        return
    try:
        group = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError, OSError):
        proc.terminate()
        return
    if group == os.getpgid(0):
        # Refuse rather than take the engine down with the job.
        proc.terminate()
        return
    try:
        os.killpg(group, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.terminate()


def _pid_alive(pid):
    """Whether `pid` is a live process, without touching it.

    Only asked at startup, to decide whether a run from a previous engine is
    still on the GPU (adopt it) or was interrupted (fail it). On POSIX,
    `os.kill(pid, 0)` is the liveness idiom -- signal 0 is not delivered, it
    only checks. On Windows signal 0 is *not* a query: CPython maps every
    signal but CTRL_C/CTRL_BREAK to TerminateProcess, so it would kill a live
    pid; Windows therefore gets an OpenProcess probe that only observes.

    Liveness alone is NOT sufficient to adopt a run -- pids are recycled. Call
    _same_process() for that. This function used to be the whole adoption test,
    and the cost of a wrong answer was not "one adopted-then-reaped run" as
    previously recorded here: an adopted run has no _proc and no supervisor, so
    nothing ever reaps it. It stayed RUNNING forever, start() refused every new
    run while it did, and stop() SIGTERMed the process group of whatever now
    held the pid.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if IS_WINDOWS:
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True             # exists, owned by someone else
    except OSError:
        return False
    return True


def _pid_alive_windows(pid):
    """Observe, never signal: open the process and read its exit code."""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _pid_start_time(pid):
    """A fingerprint distinguishing this process from a later reuse of its pid.

    src-tauri/src/adopt.rs already refuses to adopt on a live pid alone -- it
    compares `start_time`, and names the failure `PidReused`. The Rust shell
    guards the engine that way; the trainer did not guard the training job,
    so the same recycled pid that adopt.rs rejects was adopted here.

    POSIX `lstart` resolves to the second, so this cannot separate two
    processes that share a pid *and* started within the same second -- which
    requires the recycled process to be spawned in the same second as the one
    it replaced. The remaining ambiguity is far narrower than a bare pid.

    Returns None when the answer cannot be established (no such process, a
    platform that will not say, a probe that failed). None is not "matches" --
    callers must treat it as "cannot prove ownership".
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if IS_WINDOWS:
        return _pid_start_time_windows(pid)
    try:
        # lstart is the absolute start time; etime/etimes are relative to now
        # and so change between the write and the read. Portable across the
        # macOS and Linux ps implementations.
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    stamp = out.stdout.strip()
    return stamp or None


def _pid_start_time_windows(pid):
    """GetProcessTimes' creation time, via the observe-only handle."""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        rest = (wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME())
        ok = kernel32.GetProcessTimes(handle, ctypes.byref(creation),
                                      *[ctypes.byref(x) for x in rest])
        if not ok:
            return None
        return "%d:%d" % (creation.dwHighDateTime, creation.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


def _same_process(pid, recorded_start):
    """Whether `pid` is still the process that `recorded_start` came from.

    Both halves must hold and be knowable. A live pid with no recorded
    fingerprint is the pre-upgrade state file: it cannot be proven ours, and
    the penalty for guessing wrong is SIGTERM to an unrelated process group,
    so it is refused rather than adopted.
    """
    if not _pid_alive(pid):
        return False
    if not recorded_start:
        return False
    return _pid_start_time(pid) == recorded_start


def _terminate_pid_group(pid):
    """Stop an adopted run reached only by its pid, tree and all.

    The sibling of `_terminate_group`, for a run this process did not spawn and
    so has no Popen for. On POSIX the pid *is* its own group leader -- `_spawn`
    started it with a new session -- so killpg on the pid reaches the trainer
    and everything it spawned; on Windows taskkill /T walks the tree. The same
    self-preservation guard applies: never signal our own group.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    if IS_WINDOWS:
        _taskkill_tree(pid)
        return
    try:
        group = os.getpgid(pid)
    except (ProcessLookupError, PermissionError, OSError):
        return
    if group == os.getpgid(0):
        # The adopted pid is not in its own group -- refuse rather than take
        # the engine down with it.
        return
    try:
        os.killpg(group, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _write_config(path, config):
    """Write the config as YAML, falling back to JSON.

    A desktop engine that is stdlib-only cannot assume PyYAML, and a training
    config that fails to write is a run that never starts -- so JSON, which
    every YAML parser also reads, is the fallback rather than an error.
    """
    try:
        import yaml
        text = yaml.safe_dump(config, sort_keys=True, default_flow_style=False)
    except ImportError:
        text = json.dumps(config, indent=2, sort_keys=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _last_meaningful_line(log_path, limit=4000, window=65536):
    """The last non-blank line, for a failure message worth reading.

    Reads only the final `window` bytes. readlines() materialised the entire
    log to keep forty lines from the end -- and a tqdm bar writes a line per
    refresh, so a long run leaves tens of megabytes. This is called exactly
    when a run fails, which is the worst moment to allocate the whole file.
    """
    try:
        with open(log_path, "rb") as raw:
            raw.seek(0, os.SEEK_END)
            start = max(0, raw.tell() - window)
            raw.seek(start)
            chunk = raw.read()
        text = chunk.decode("utf-8", errors="replace")
        lines = text.splitlines()
        # A seek into the middle of the file almost certainly lands inside a
        # line, so the first one is a fragment. Drop it -- unless we started at
        # the beginning, where it is a whole line.
        if start and len(lines) > 1:
            lines = lines[1:]
        tail = lines[-40:]
    except OSError:
        return None
    for line in reversed(tail):
        text = line.strip()
        if text:
            return text[:limit]
    return None

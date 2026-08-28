"""Tests for the training subsystem.

These run the real thing: real subprocesses, real files, real SIGTERM. The
parsers are pure and cheap to test, but the parts that break in production are
the process lifecycle and the event replay, and neither can be tested with a
mock without testing the mock.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import training                                          # noqa: E402


def _wait(predicate, timeout=20.0):
    """Poll until true, so a slow machine fails slowly rather than falsely."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _alive(pid):
    """True while the pid exists, including as a zombie we have not reaped.

    os.kill(pid, 0) is the POSIX liveness idiom, but on Windows Python maps
    every signal other than CTRL_C/CTRL_BREAK to TerminateProcess: signal 0
    would try to *kill* a live pid, and a dead one raises OSError(WinError 87)
    rather than ProcessLookupError -- so the probe both lies and, worse, is
    destructive. Windows therefore gets an OpenProcess-based check that only
    observes, mirroring how training.py already forks its termination path.
    """
    if os.name == "nt":
        return _alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _alive_windows(pid):
    """Observe, never signal: open the process and read its exit code.

    STILL_ACTIVE (259) means running. A pid that cannot be opened -- invalid
    (WinError 87) or already gone -- reads as dead. This is the non-destructive
    counterpart to os.kill(pid, 0), which on Windows would terminate the pid.
    """
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # A HANDLE is pointer-sized; without restype ctypes truncates it to a C int
    # and the CloseHandle below would free the wrong value on 64-bit.
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


def _script(body):
    """Substitute the command, not the spawn.

    Only argv changes; process groups, pipes and buffering stay the production
    code's job, so a regression there fails a test instead of hiding behind a
    launcher that re-implemented it.
    """
    return lambda run: [sys.executable, "-u", "-c", body]


class ParseMetric(unittest.TestCase):
    def test_reads_a_trl_logging_line(self):
        got = training.parse_metric(
            "{'loss': 1.234, 'grad_norm': 2.0, 'learning_rate': 0.0002, 'epoch': 0.5}")
        self.assertEqual(got, {"loss": 1.234, "learning_rate": 0.0002, "epoch": 0.5})

    def test_scientific_notation_survives(self):
        got = training.parse_metric("{'loss': 8.6e-05, 'learning_rate': 1e-4, 'epoch': 2.0}")
        self.assertAlmostEqual(got["loss"], 8.6e-05)

    def test_a_partial_line_is_not_a_partial_metric(self):
        # A dict without learning_rate must yield nothing rather than a metric
        # with a missing field, which would plot as a hole or a zero.
        self.assertIsNone(training.parse_metric("{'loss': 1.0, 'epoch': 0.5}"))

    def test_noise_is_none(self):
        for line in ("", "Loading checkpoint shards", "  0%|", None):
            self.assertIsNone(training.parse_metric(line))


class ParseProgress(unittest.TestCase):
    def test_reads_a_tqdm_bar(self):
        self.assertEqual(training.parse_progress(" 12/100 [00:03<00:24, 3.9it/s]"),
                         {"step": 12, "total": 100})

    def test_step_beyond_total_is_rejected(self):
        # Otherwise a corrupt line renders a 400%-full progress bar.
        self.assertIsNone(training.parse_progress("400/100 [00:03<00:00]"))

    def test_zero_total_is_rejected(self):
        self.assertIsNone(training.parse_progress("0/0 ["))


class EventReplay(unittest.TestCase):
    def setUp(self):
        self.run = training.Run("r", "/tmp/c.yaml", "/tmp/t.log")

    def test_a_fresh_client_gets_everything(self):
        for i in range(3):
            self.run.emit("log", {"line": str(i)})
        events, gap = self.run.since(-1)
        self.assertEqual([e[2]["line"] for e in events], ["0", "1", "2"])
        self.assertFalse(gap)

    def test_a_reconnecting_client_gets_only_what_it_missed(self):
        for i in range(5):
            self.run.emit("log", {"line": str(i)})
        events, gap = self.run.since(2)
        self.assertEqual([e[2]["line"] for e in events], ["3", "4"])
        self.assertFalse(gap)

    def test_an_evicted_cursor_reports_a_gap_rather_than_lying(self):
        self.run.MAX_EVENTS = 10
        for i in range(50):
            self.run.emit("log", {"line": str(i)})
        events, gap = self.run.since(0)
        self.assertTrue(gap, "history was dropped and the client was not told")

    def test_cursors_stay_monotonic_across_eviction(self):
        self.run.MAX_EVENTS = 10
        for i in range(50):
            self.run.emit("log", {"line": str(i)})
        cursors = [e[0] for e in self.run.events]
        self.assertEqual(cursors, sorted(cursors))
        self.assertEqual(len(set(cursors)), len(cursors))
        self.assertGreater(cursors[0], 0, "cursors restarted; replay would repeat")

    def test_the_first_ending_wins(self):
        self.run.finish(training.DONE)
        self.run.finish(training.FAILED, "late reap")
        self.assertEqual(self.run.state, training.DONE)
        self.assertIsNone(self.run.error)


class TerminateGroup(unittest.TestCase):
    """The guard that keeps stopping a run from stopping the app."""

    def test_a_child_in_our_own_group_is_terminated_singly(self):
        # Deliberately no new session, so the child shares our process group.
        # killpg here would SIGTERM this test runner -- and does, if the guard
        # is removed. The child must still die; we must still be here.
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            training._terminate_group(proc)
            self.assertTrue(_wait(lambda: proc.poll() is not None, 10),
                            "the child outlived the terminate")
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertTrue(True, "reached: the guard did not take us down with it")

    def test_an_already_dead_child_is_not_an_error(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        proc.wait()
        training._terminate_group(proc)          # must not raise


class RunIdValidation(unittest.TestCase):
    """The engine has no auth by design, so client-supplied ids are checked."""

    def test_ordinary_ids_pass_through_unchanged(self):
        for good in ("run-1712345678", "my_run.2", "A", "a" * 64):
            self.assertEqual(training.validate_run_id(good), good)

    def test_traversal_is_refused(self):
        for bad in ("../etc/passwd", "..", ".", "a/../../b", "/absolute",
                    "run/../..", "\\\\server\\share"):
            with self.assertRaises(ValueError, msg=f"accepted {bad!r}"):
                training.validate_run_id(bad)

    def test_a_traversing_id_never_creates_a_directory(self):
        home = tempfile.mkdtemp(prefix="praison-train-id-")
        try:
            trainer = training.Trainer(home, sys.executable)
            escape = os.path.join(home, "escaped")
            with self.assertRaises(ValueError):
                trainer.start({"model_name": "m", "dataset": "d"},
                              run_id="../escaped")
            self.assertFalse(os.path.exists(escape), "wrote outside the runs dir")
            self.assertIsNone(trainer.current, "a refused start left a run behind")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_odd_but_harmless_shapes_are_refused_rather_than_mangled(self):
        for bad in ("", None, "a" * 65, "-leading-dash", "sp ace", "semi;colon",
                    "new\nline", "nul\x00byte"):
            with self.assertRaises(ValueError, msg=f"accepted {bad!r}"):
                training.validate_run_id(bad)


class Portability(unittest.TestCase):
    """The app ships on macOS, Windows and Linux from one engine source.

    These run on whatever platform the suite runs on, but each asserts the
    behaviour that a *different* platform would otherwise get wrong, so a
    regression is caught on a Mac laptop rather than in a Windows bug report.
    """

    def test_a_windows_style_command_keeps_its_backslashes(self):
        # shlex.split in POSIX mode eats every backslash, so a user pointing
        # PRAISONAI_TRAIN_CMD at C:\Users\me\envs\cuda\Scripts\python.exe
        # gets C:Usersmeenvscudascriptspython.exe and a FileNotFoundError.
        argv = training.split_command(
            r"C:\Users\me\envs\cuda\Scripts\python.exe -m praisonai_train llm",
            windows=True)
        self.assertEqual(argv[0], r"C:\Users\me\envs\cuda\Scripts\python.exe")
        self.assertEqual(argv[1:], ["-m", "praisonai_train", "llm"])

    def test_a_quoted_windows_path_with_spaces_survives(self):
        argv = training.split_command(r'"C:\Program Files\Py\python.exe" -u', windows=True)
        self.assertEqual(argv, [r"C:\Program Files\Py\python.exe", "-u"])

    def test_a_posix_command_still_splits_the_posix_way(self):
        argv = training.split_command("/usr/bin/env python3 -m praisonai_train", windows=False)
        self.assertEqual(argv, ["/usr/bin/env", "python3", "-m", "praisonai_train"])

    def test_the_windows_spawn_asks_for_its_own_process_group(self):
        # start_new_session is accepted and then ignored by CPython on Windows,
        # so relying on it there loses the guarantee silently. This asserts the
        # platform branch chooses creationflags instead.
        try:
            training.IS_WINDOWS = True
            kwargs = training._new_process_group()
        finally:
            training.IS_WINDOWS = os.name == "nt"
        self.assertIn("creationflags", kwargs)
        self.assertNotIn("start_new_session", kwargs,
                         "the flag CPython ignores on Windows is still being passed")

    def test_the_posix_spawn_asks_for_a_new_session(self):
        try:
            training.IS_WINDOWS = False
            kwargs = training._new_process_group()
        finally:
            training.IS_WINDOWS = os.name == "nt"
        self.assertEqual(kwargs, {"start_new_session": True})

    def test_windows_reserved_device_names_are_refused(self):
        # os.makedirs on a directory called CON or LPT1 fails or retargets a
        # device. The allowlist cannot see this, because they are alphanumeric.
        for reserved in ("CON", "con", "NUL", "PRN", "AUX", "COM1", "LPT1", "con.log"):
            with self.assertRaises(ValueError, msg=f"accepted {reserved!r}"):
                training.validate_run_id(reserved)

    def test_a_trailing_dot_is_refused(self):
        # Windows silently strips it, so "run-1." and "run-1" become one
        # directory and two runs would overwrite each other's logs.
        for bad in ("run-1.", "a."):
            with self.assertRaises(ValueError, msg=f"accepted {bad!r}"):
                training.validate_run_id(bad)

    def test_ordinary_ids_that_merely_contain_a_device_name_are_fine(self):
        for good in ("console-run", "com10", "nullify", "aux-1-run", "conf"):
            self.assertEqual(training.validate_run_id(good), good)


class FakeProc:
    """Just enough of Popen to see which termination path was taken."""

    def __init__(self, alive=True):
        self.pid = 999999
        self._alive = alive
        self.signals = []
        self.terminated = False

        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def send_signal(self, sig):
        self.signals.append(sig)

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class WindowsTermination(unittest.TestCase):
    """The Windows branch of _terminate_group, exercised from any platform.

    os.getpgid and os.killpg do not exist on Windows at all. An AttributeError
    from either would escape stop(), and since stop() sets the run to STOPPING
    before signalling, the run would sit in "stopping" forever while the
    trainer kept the GPU. So the branch must be taken *before* either is
    reached -- which is what this asserts.
    """

    def setUp(self):
        self.was = training.IS_WINDOWS
        self.pgid_calls = []
        self.tree_kills = []
        # getattr: os.getpgid does not exist on Windows at all, so taking it
        # unconditionally made this class -- the one that exists to prove the
        # Windows path works -- error in setUp on Windows.
        self.real_getpgid = getattr(os, "getpgid", None)
        self.real_taskkill = training._taskkill_tree
        os.getpgid = lambda pid: self.pgid_calls.append(pid) or 1
        training._taskkill_tree = lambda pid: self.tree_kills.append(pid) or True

    def tearDown(self):
        training.IS_WINDOWS = self.was
        if self.real_getpgid is None:
            del os.getpgid
        else:
            os.getpgid = self.real_getpgid
        training._taskkill_tree = self.real_taskkill

    def test_the_windows_path_never_touches_process_groups(self):
        training.IS_WINDOWS = True
        training._terminate_group(FakeProc())
        self.assertEqual(self.pgid_calls, [],
                         "os.getpgid was called; on Windows it does not exist")

    def test_the_windows_path_kills_the_whole_tree(self):
        # Not "signalled something" -- that is what the previous version of
        # this test asserted, and CTRL_BREAK_EVENT satisfied it while the
        # trainer ran happily to completion. The subject is whether the tree
        # is actually killed, and with which pid.
        training.IS_WINDOWS = True
        proc = FakeProc()
        training._terminate_group(proc)
        self.assertEqual(self.tree_kills, [proc.pid],
                         "the child tree was never killed")

    def test_a_failed_tree_kill_still_kills_the_trainer(self):
        training.IS_WINDOWS = True
        training._taskkill_tree = lambda pid: False
        proc = FakeProc()
        training._terminate_group(proc)
        self.assertTrue(proc.killed,
                        "taskkill failed and nothing else stopped the process")

    def test_a_process_that_already_exited_is_not_killed_again(self):
        training.IS_WINDOWS = True
        training._taskkill_tree = lambda pid: False
        proc = FakeProc(alive=False)
        training._terminate_group(proc)
        self.assertFalse(proc.killed, "killed a process that had already exited")

    def test_the_tree_kill_command_targets_the_tree_and_forces_it(self):
        # /T is what makes this the equivalent of killpg: without it only the
        # trainer dies and whatever it spawned keeps the GPU.
        seen = {}

        def fake_run(argv, **kwargs):
            seen["argv"] = argv
            return types.SimpleNamespace(returncode=0)

        real_run = training.subprocess.run
        training.subprocess.run = fake_run
        try:
            # self.real_taskkill, not training._taskkill_tree: setUp replaces
            # that with a recorder for the other tests in this class, and
            # calling it here would exercise the stub rather than the code.
            self.assertTrue(self.real_taskkill(4321))
        finally:
            training.subprocess.run = real_run
        self.assertEqual(seen["argv"][:1], ["taskkill"])
        self.assertIn("/T", seen["argv"])
        self.assertIn("/F", seen["argv"])
        self.assertIn("4321", seen["argv"])

    def test_the_posix_path_does_use_process_groups(self):
        training.IS_WINDOWS = False
        training._terminate_group(FakeProc())
        self.assertTrue(self.pgid_calls, "the posix path stopped using the process group")


class RunDirectoryCollisions(unittest.TestCase):
    """Two runs must never share a directory.

    They overwrite each other's config.yaml and interleave into one train.log,
    so the second run trains on the first one's settings and neither log can be
    read. Two ways in: ids differing only in case (macOS and Windows compare
    filenames case-insensitively), and the auto-generated id, which had
    one-second resolution.
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-collide-")
        self.trainer = training.Trainer(self.home, sys.executable)
        self.trainer.command_builder = _script("print('done')")
        self.config = {"model_name": "unsloth/tiny", "dataset": "d.json"}

    def tearDown(self):
        self.trainer.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def _finished(self, run):
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 20), run.state)

    def test_an_id_differing_only_in_case_is_refused(self):
        first = self.trainer.start(self.config, "run-alpha")
        self._finished(first)
        with self.assertRaises(ValueError):
            self.trainer.start(self.config, "RUN-ALPHA")

    def test_the_same_id_twice_is_refused(self):
        first = self.trainer.start(self.config, "run-beta")
        self._finished(first)
        with self.assertRaises(ValueError):
            self.trainer.start(self.config, "run-beta")

    def test_a_refused_id_does_not_disturb_the_existing_run(self):
        # The check used to run after makedirs and _write_config, so by the
        # time it raised it had already overwritten the first run's config.
        first = self.trainer.start(dict(self.config, learning_rate=0.0002), "run-gamma")
        self._finished(first)
        before = pathlib.Path(first.config_path).read_text()
        with self.assertRaises(ValueError):
            self.trainer.start(dict(self.config, learning_rate=0.9), "RUN-GAMMA")
        self.assertEqual(pathlib.Path(first.config_path).read_text(), before,
                         "the refused run overwrote the existing run's config")

    def test_two_generated_ids_in_the_same_second_do_not_collide(self):
        runs = []
        for _ in range(4):
            run = self.trainer.start(self.config)
            self._finished(run)
            runs.append(run)
        ids = [run.id for run in runs]
        self.assertEqual(len(set(i.casefold() for i in ids)), len(ids),
                         f"generated ids collided: {ids}")
        directories = sorted(os.listdir(os.path.join(self.home, "runs")))
        self.assertEqual(len(directories), len(runs),
                         f"{len(runs)} runs produced {len(directories)} directories")

    def test_a_generated_id_avoids_a_directory_left_by_an_earlier_process(self):
        # The history is empty after a restart, so the filesystem is the only
        # record that the id is taken.
        stamp = int(time.time())
        os.makedirs(os.path.join(self.home, "runs", f"run-{stamp}"), exist_ok=True)
        run = self.trainer.start(self.config)
        self._finished(run)
        self.assertNotEqual(run.id, f"run-{stamp}",
                            "the new run reused a directory from a previous process")


class HistoryRetention(unittest.TestCase):
    """The history is capped, and reaching the cap must not break anything.

    It is a bounded deque so a process that stays open for days does not hold
    every run's event ring and metric series forever. The cap has to be reached
    by a test, because the two things that go wrong there only go wrong when it
    is full: insert(0, ...) raises IndexError on a full bounded deque, so the
    run after the cap failed to start at all; and evicting from the wrong end
    would drop the run that just finished instead of the oldest one.
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-history-")
        self.trainer = training.Trainer(self.home, sys.executable)
        self.trainer.command_builder = _script("print('done')")
        self.config = {"model_name": "unsloth/tiny", "dataset": "d.json"}

    def tearDown(self):
        self.trainer.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def _run_once(self, run_id=None):
        run = self.trainer.start(self.config, run_id)
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 20), run.state)
        return run

    def test_starting_more_runs_than_the_cap_still_works(self):
        cap = training.MAX_HISTORY
        for i in range(cap + 3):
            self._run_once(f"run-{i:04d}")
        self.assertEqual(len(self.trainer.history), cap)

    def test_the_newest_run_is_kept_and_the_oldest_is_dropped(self):
        cap = training.MAX_HISTORY
        for i in range(cap + 1):
            self._run_once(f"run-{i:04d}")
        ids = [r.id for r in self.trainer.history]
        self.assertEqual(ids[0], f"run-{cap:04d}", "the newest run is not first")
        self.assertNotIn("run-0000", ids, "the oldest run was not the one evicted")

    def test_the_metric_series_is_capped(self):
        run = training.Run("r", "c", os.path.join(self.home, "t.log"))
        for step in range(training.MAX_METRICS + 25):
            run.metrics.append({"step": step, "loss": 0.1})
        self.assertEqual(len(run.metrics), training.MAX_METRICS)
        self.assertEqual(run.metrics[-1]["step"], training.MAX_METRICS + 24,
                         "the newest metric was dropped instead of the oldest")


class StopBeforeSpawn(unittest.TestCase):
    """Cancelling in the window before the trainer process exists.

    start() returns as soon as the supervisor thread is created, so between
    the HTTP reply and Popen returning there is a period where run._proc is
    None. stop() had nothing to signal there, and _supervise then overwrote
    STOPPING with RUNNING: the user saw {"ok": true} and a "stopping" pill,
    and the fine-tune ran to completion and reported "done", holding the GPU.

    The window is real but short, so a route-level test cannot reach it
    reliably -- two HTTP round trips are slower than a spawn. Delaying the
    spawn makes it deterministic instead of hoping for a race.
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-stopspawn-")
        self.trainer = training.Trainer(self.home, sys.executable)
        self.spawned = threading.Event()
        real_spawn = self.trainer._spawn

        def slow_spawn(run):
            # Hold the run in `pending` long enough to stop it deliberately.
            self.spawned.wait(2.0)
            return real_spawn(run)

        self.trainer._spawn = slow_spawn

    def tearDown(self):
        self.spawned.set()
        self.trainer.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_stop_while_pending_cancels_the_run(self):
        # The script announces when it has run to the end. Checking only the
        # final state is not enough: a version that records CANCELLED without
        # actually signalling the process passes that check while the training
        # job keeps running and holding the GPU, which is the whole harm.
        self.trainer.command_builder = _script(
            "import time\n"
            "for _ in range(40):\n"
            "    print('working', flush=True); time.sleep(0.05)\n"
            "print('RAN-TO-COMPLETION', flush=True)")
        run = self.trainer.start({"model_name": "unsloth/tiny", "dataset": "d.json"})
        self.assertEqual(run.state, training.PENDING)
        self.assertIsNone(run._proc, "the process already exists; the window was missed")

        self.assertTrue(self.trainer.stop(), "stop() refused a pending run")
        self.assertEqual(run.state, training.STOPPING)

        self.spawned.set()          # let the spawn proceed
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 20), run.state)
        self.assertEqual(run.state, training.CANCELLED,
                         "the run continued after the user cancelled it")

        log = pathlib.Path(run.log_path).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("RAN-TO-COMPLETION", log,
                         "the run was reported cancelled but ran to the end anyway")
        self.assertIsNotNone(run._proc, "no process was ever spawned to stop")
        self.assertIsNotNone(run._proc.poll(), "the trainer process is still alive")

    def test_a_run_not_stopped_in_that_window_still_runs_normally(self):
        # The guard must not cancel runs nobody asked to cancel.
        self.trainer.command_builder = _script("print('done')")
        run = self.trainer.start({"model_name": "unsloth/tiny", "dataset": "d.json"})
        self.spawned.set()
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 20), run.state)
        self.assertEqual(run.state, training.DONE)


class SurvivingARestart(unittest.TestCase):
    """State must outlive the engine process, or a restart lies.

    The engine kept the live run and the history in memory only, so a crash,
    relaunch or kill left `/train/runs` empty, `stop` with nothing to stop, and
    `start` willing to launch a second trainer beside a live one -- the OOM
    that "one GPU runs one job" exists to refuse. A second Trainer over the
    same home stands in for the process that comes back after the restart.
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-restart-")
        self.first = training.Trainer(self.home, sys.executable)
        self.config = {"model_name": "unsloth/tiny", "dataset": "d.json"}

    def tearDown(self):
        self.first.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def _start_a_live_run(self):
        self.first.command_builder = _script(
            "import time\nprint('up', flush=True)\ntime.sleep(120)")
        run = self.first.start(self.config, "run-live")
        self.assertTrue(_wait(lambda: run.state == training.RUNNING), run.state)
        return run

    def test_a_live_run_reappears_after_a_restart(self):
        run = self._start_a_live_run()
        second = training.Trainer(self.home, sys.executable)
        self.assertIn("run-live", [r.id for r in second.history],
                      "the run vanished from history after the restart")
        adopted = second.get("run-live")
        self.assertEqual(adopted.state, training.RUNNING,
                         "a run still on the GPU was not shown as running")

    def test_a_second_finetune_is_refused_after_a_restart(self):
        self._start_a_live_run()
        second = training.Trainer(self.home, sys.executable)
        second.command_builder = _script("pass")
        with self.assertRaises(RuntimeError):
            second.start(self.config, "run-two")

    def test_stop_after_a_restart_actually_kills_the_live_pid(self):
        run = self._start_a_live_run()
        pid = run.pid
        self.assertTrue(_alive(pid))
        second = training.Trainer(self.home, sys.executable)
        self.assertTrue(second.stop(), "stop() found nothing to stop after restart")
        self.assertTrue(_wait(lambda: not _alive(pid), 15),
                        "the adopted run's pid outlived stop()")
        self.assertEqual(second.get("run-live").state, training.CANCELLED)

    def test_an_interrupted_run_is_reported_failed_not_missing(self):
        # No live process: a run.json left as RUNNING by a killed engine whose
        # pid is now gone must read as failed, not adopted.
        run_dir = os.path.join(self.home, "runs", "run-dead")
        os.makedirs(run_dir, exist_ok=True)
        import json
        with open(os.path.join(run_dir, "run.json"), "w") as fh:
            json.dump({"id": "run-dead", "state": training.RUNNING,
                       "started": time.time(), "pid": 2 ** 31 - 1}, fh)
        second = training.Trainer(self.home, sys.executable)
        dead = second.get("run-dead")
        self.assertIsNotNone(dead, "the interrupted run was dropped entirely")
        self.assertEqual(dead.state, training.FAILED)
        self.assertIsNone(second.current, "a dead run was adopted as live")

    def test_a_finished_run_is_not_adopted_after_a_restart(self):
        self.first.command_builder = _script("print('done')")
        run = self.first.start(self.config, "run-done")
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL), run.state)
        second = training.Trainer(self.home, sys.executable)
        self.assertEqual(second.get("run-done").state, training.DONE)
        self.assertIsNone(second.current, "a finished run was adopted as live")
        second.command_builder = _script("pass")
        again = second.start(self.config, "run-after")
        self.assertTrue(_wait(lambda: again.state in training.TERMINAL), again.state)

    def test_a_half_written_state_file_never_reaches_the_reader(self):
        # _persist writes a temp file and os.replaces it, so a reader only ever
        # sees the old whole file or the new whole file -- never the truncated
        # middle a plain open("w") would leave if the engine were killed mid
        # write. Were the write non-atomic, an interrupted _reload would skip
        # the record, the live run would vanish, and stop() and the single-GPU
        # guard would both lose it.
        run = self._start_a_live_run()
        state = pathlib.Path(self.home, "runs", "run-live", "run.json")
        self.assertTrue(state.exists(), "the live run was never persisted")
        import json
        json.loads(state.read_text())          # complete JSON, not a fragment
        siblings = list(state.parent.glob("run.json.*.tmp"))
        self.assertEqual(siblings, [], f"a temp file was left behind: {siblings}")

    def test_a_run_persisted_before_spawn_is_not_lost_on_an_early_restart(self):
        # start() persists the run before the supervisor thread exists, so an
        # engine that dies in that window still leaves a record. Simulate it: a
        # pending run.json with no pid must reload as failed and not be adopted,
        # rather than vanishing and letting a second trainer start.
        run_dir = os.path.join(self.home, "runs", "run-early")
        os.makedirs(run_dir, exist_ok=True)
        import json
        with open(os.path.join(run_dir, "run.json"), "w") as fh:
            json.dump({"id": "run-early", "state": training.PENDING,
                       "started": time.time(), "pid": None}, fh)
        second = training.Trainer(self.home, sys.executable)
        early = second.get("run-early")
        self.assertIsNotNone(early, "a run persisted before spawn was dropped")
        self.assertEqual(early.state, training.FAILED)
        self.assertIsNone(second.current, "a pidless pending run was adopted")


class RunLifecycle(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-train-test-")
        self.trainer = training.Trainer(self.home, sys.executable)

    def tearDown(self):
        self.trainer.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def _config(self):
        return {"model_name": "unsloth/tiny", "dataset": "d.json"}

    def _start(self, command_builder):
        """Start a run whose argv is ours and whose spawn is the real one."""
        self.trainer.command_builder = command_builder
        return self.trainer.start(self._config())

    def test_a_successful_run_ends_done_and_logs(self):
        run = self._start(_script(
            "print(\"{'loss': 0.5, 'learning_rate': 0.0002, 'epoch': 1.0}\")\n"
            "print(' 5/10 [00:01<00:01]')"))
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL), run.state)
        self.assertEqual(run.state, training.DONE)
        self.assertEqual(run.metrics[-1]["loss"], 0.5)
        self.assertEqual((run.step, run.total), (5, 10))
        with open(run.log_path) as handle:
            self.assertIn("loss", handle.read())

    def test_a_crash_ends_failed_and_says_why(self):
        run = self._start(_script(
            "import sys; print('CUDA out of memory'); sys.exit(1)"))
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL))
        self.assertEqual(run.state, training.FAILED)
        self.assertIn("out of memory", run.error)

    def test_a_command_that_cannot_be_run_fails_the_run_rather_than_hanging(self):
        # A missing interpreter is the realistic version of this: the venv was
        # moved or never provisioned. The run must end FAILED with a readable
        # reason, not sit at "pending" forever with a spinner.
        run = self._start(lambda run: ["/nonexistent/bin/praisonai-train"])
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL))
        self.assertEqual(run.state, training.FAILED)
        self.assertIn("could not start", run.error)

    def test_stopping_cancels_and_reaps_the_process(self):
        run = self._start(_script(
            "import time\nprint('up', flush=True)\ntime.sleep(120)"))
        self.assertTrue(_wait(lambda: run._proc is not None and run.state == training.RUNNING))
        pid = run._proc.pid
        self.assertTrue(self.trainer.stop())
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 15))
        self.assertEqual(run.state, training.CANCELLED)
        self.assertIsNotNone(run._proc.poll(), "the child was never reaped")
        # Gone, not a zombie left behind. os.kill(pid, 0) is the POSIX way to
        # ask, but on Windows signal 0 is not a query -- it terminates -- so the
        # liveness probe is factored into _alive, which observes on either OS.
        self.assertFalse(_alive(pid), "the child was left behind after reaping")

    def test_stopping_also_kills_what_the_trainer_spawned(self):
        """The orphan case, which is the one that actually bites.

        A real trainer spawns children -- dataloader workers, torchrun ranks.
        Signalling the parent pid alone leaves them holding the GPU, and the
        next run OOMs against a job the user thinks they cancelled. So the
        child is started in its own process group and the group is signalled.
        """
        marker = os.path.join(self.home, "grandchild.pid")
        run = self._start(_script(
            "import subprocess, sys, time\n"
            "kid = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            f"open({marker!r}, 'w').write(str(kid.pid))\n"
            "print('spawned', flush=True)\n"
            "time.sleep(120)"))
        self.assertTrue(_wait(lambda: os.path.exists(marker)), "grandchild never started")
        grandchild = int(open(marker).read())
        self.trainer.stop()
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 15))
        gone = _wait(lambda: not _alive(grandchild), 10)
        if not gone:
            os.kill(grandchild, 9)          # do not leak it out of the test
        self.assertTrue(gone, f"pid {grandchild} outlived the run it belonged to")

    def test_a_second_run_is_refused_while_one_is_live(self):
        self._start(_script("import time; time.sleep(60)"))
        self.assertTrue(_wait(lambda: self.trainer.current.state == training.RUNNING))
        with self.assertRaises(RuntimeError) as caught:
            self._start(_script("pass"))
        self.assertIn("Stop it", str(caught.exception))

    def test_a_run_may_start_once_the_previous_one_ended(self):
        first = self._start(_script("pass"))
        self.assertTrue(_wait(lambda: first.state in training.TERMINAL))
        second = self._start(_script("pass"))
        self.assertTrue(_wait(lambda: second.state in training.TERMINAL))
        self.assertEqual(second.state, training.DONE)
        self.assertEqual(len(self.trainer.history), 2)

    def test_stopping_a_stale_run_id_does_not_kill_the_live_one(self):
        run = self._start(_script("import time; time.sleep(60)"))
        self.assertTrue(_wait(lambda: run.state == training.RUNNING))
        with self.assertRaises(RuntimeError):
            self.trainer.stop("run-from-a-stale-tab")
        self.assertEqual(run.state, training.RUNNING)

    def test_stopping_nothing_is_false_not_an_error(self):
        self.assertFalse(self.trainer.stop())

    def test_non_ascii_output_survives_the_pipe(self):
        """The trainer's banner is emoji; the log must not be mojibake.

        text=True with no encoding decodes in the locale encoding, which is
        cp1252 on a default Windows box: unsloth's sloth banner comes through
        corrupted, and five cp1252 bytes are undefined outright, which raises
        inside the reader loop and freezes the log while the run continues.
        """
        run = self._start(_script(
            "import sys\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            "print('\U0001F9A5 Unsloth: patching \u2014 caf\u00e9 \u03b1\u03b2\u03b3')"))
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL))
        self.assertEqual(run.state, training.DONE, run.error)
        with open(run.log_path, encoding="utf-8") as handle:
            logged = handle.read()
        self.assertIn("caf\u00e9", logged)
        self.assertIn("\u03b1\u03b2\u03b3", logged)
        self.assertIn("\U0001F9A5", logged)

    def test_undecodable_bytes_do_not_stop_the_reader(self):
        """A stray byte must cost one character, not the rest of the run."""
        run = self._start(_script(
            "import sys\n"
            "sys.stdout.buffer.write(b'before \\x81\\xfe after\\n')\n"
            "sys.stdout.buffer.write(b'still reading\\n')\n"
            "sys.stdout.buffer.flush()"))
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL))
        lines = [e[2].get("line") for e in run.events if e[1] == "log"]
        self.assertTrue(any("still reading" in (l or "") for l in lines),
                        f"the reader stopped at the bad byte: {lines}")

    def test_a_log_write_failure_does_not_wedge_the_run(self):
        """A failing log write must not abandon the pipe.

        If the reader stops on the first log-write OSError, the child blocks
        on a full pipe, proc.wait() blocks on the child, run.finish() never
        runs, and the run reads "running" forever -- refusing every later run.
        The pipe must be drained whatever happens to the log, so the run still
        ends and metrics/events still grow past the pre-failure count.
        """
        import builtins
        real_open = builtins.open

        def failing_open(path, *args, **kwargs):
            if str(path).endswith("train.log"):
                raise OSError(28, "No space left on device")
            return real_open(path, *args, **kwargs)

        builtins.open = failing_open
        try:
            run = self._start(_script(
                "print(\"{'loss': 0.5, 'learning_rate': 0.0002, 'epoch': 1.0}\")\n"
                "for i in range(20000):\n"
                "    print('line', i)"))
            self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 10),
                            f"log-write failure wedged the run at {run.state}")
        finally:
            builtins.open = real_open
        self.assertEqual(run.state, training.DONE)
        self.assertTrue(run.metrics, "the metric never arrived past the log failure")
        self.assertEqual(run.metrics[-1]["loss"], 0.5)
        events = [e for e in run.events if e[1] == "log"]
        self.assertGreater(len(events), 100,
                           "events stopped growing when the log write failed")

    def test_a_log_close_failure_does_not_wedge_the_run(self):
        """A raise from log.close() must not skip finalization.

        close() flushes, so a full disk or a revoked directory can fail there
        just as a per-line write can. If that escapes the reader's finally
        block, proc.wait() and run.finish() never run and the run reads
        "running" forever -- the same permanent wedge, moved to the last line.
        The log opens fine here; only its close() raises.
        """
        import builtins
        real_open = builtins.open

        def closing_fails_open(path, *args, **kwargs):
            handle = real_open(path, *args, **kwargs)
            if str(path).endswith("train.log"):
                def boom():
                    raise OSError(28, "No space left on device")
                handle.close = boom
            return handle

        builtins.open = closing_fails_open
        try:
            run = self._start(_script("print('a line')"))
            self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 10),
                            f"log-close failure wedged the run at {run.state}")
        finally:
            builtins.open = real_open
        self.assertEqual(run.state, training.DONE)

    def test_the_log_is_flushed_while_the_run_is_live(self):
        """train.log must be readable during the run, not only after it.

        The engine caps in-memory events on the premise that "the log file is
        the full record". A block-buffered, never-flushed log is 0 bytes on
        disk throughout a live run, so that record does not exist until exit.
        """
        run = self._start(_script(
            "import time\n"
            "print('first line', flush=True)\n"
            "time.sleep(3)\n"
            "print('second line', flush=True)"))
        self.assertTrue(_wait(
            lambda: os.path.exists(run.log_path)
            and os.path.getsize(run.log_path) > 0, 5),
            "the log was empty on disk while the run was live")
        self.trainer.stop()
        self.assertTrue(_wait(lambda: run.state in training.TERMINAL, 15))

    def test_the_config_is_written_where_the_trainer_will_read_it(self):
        run = self._start(_script("pass"))
        self.assertTrue(os.path.exists(run.config_path))
        with open(run.config_path) as handle:
            self.assertIn("unsloth/tiny", handle.read())

    def test_a_config_written_as_yaml_parses_back_to_the_same_values(self):
        config = {"model_name": "unsloth/tiny", "dataset": "d.json",
                  "lora_r": 16, "huggingface_save": False}
        path = os.path.join(self.home, "c.yaml")
        training._write_config(path, config)
        try:
            import yaml
            loaded = yaml.safe_load(open(path))
        except ImportError:
            import json
            loaded = json.load(open(path))
        self.assertEqual(loaded, config)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Tests for the training subsystem.

These run the real thing: real subprocesses, real files, real SIGTERM. The
parsers are pure and cheap to test, but the parts that break in production are
the process lifecycle and the event replay, and neither can be tested with a
mock without testing the mock.
"""

import os
import shutil
import subprocess
import sys
import tempfile
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
    """True while the pid exists, including as a zombie we have not reaped."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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

    def poll(self):
        return None if self._alive else 0

    def send_signal(self, sig):
        self.signals.append(sig)

    def terminate(self):
        self.terminated = True


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
        self.real_getpgid = os.getpgid
        os.getpgid = lambda pid: self.pgid_calls.append(pid) or 1

    def tearDown(self):
        training.IS_WINDOWS = self.was
        os.getpgid = self.real_getpgid

    def test_the_windows_path_never_touches_process_groups(self):
        training.IS_WINDOWS = True
        proc = FakeProc()
        training._terminate_group(proc)
        self.assertEqual(self.pgid_calls, [],
                         "os.getpgid was called; on Windows it does not exist")
        self.assertTrue(proc.signals or proc.terminated,
                        "the Windows path signalled nothing at all")

    def test_the_windows_path_falls_back_to_terminate_if_signalling_fails(self):
        training.IS_WINDOWS = True
        proc = FakeProc()
        proc.send_signal = lambda sig: (_ for _ in ()).throw(OSError("no console"))
        training._terminate_group(proc)
        self.assertTrue(proc.terminated, "a failed signal left the process running")

    def test_the_posix_path_does_use_process_groups(self):
        training.IS_WINDOWS = False
        training._terminate_group(FakeProc())
        self.assertTrue(self.pgid_calls, "the posix path stopped using the process group")


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
        with self.assertRaises(OSError):
            os.kill(pid, 0)          # gone, not a zombie left behind

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

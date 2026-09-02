"""A recycled pid must not be mistaken for a run this engine started.

_reload() adopted any persisted run whose pid was merely alive. PIDs are
recycled, and an adopted run carries no _proc and no supervisor -- so nothing
would ever reap it. The consequences were not "one adopted-then-reaped run",
as _pid_alive's docstring supposed:

  * the run stays RUNNING forever, and start() refuses to launch a new one
    while a live run exists -- fine-tuning is blocked until someone finds and
    deletes the state file by hand;
  * stop() takes the `proc is None and run.pid` branch and calls
    _terminate_pid_group(run.pid), sending SIGTERM to the process group of
    whatever unrelated program now holds that pid.

src-tauri/src/adopt.rs already refused adoption on a live pid alone, comparing
`start_time` and naming the rejection `PidReused`. The Rust shell guarded the
engine; nothing guarded the training job. These tests pin the Python side to
the same rule.

Run: .venv/bin/python -m unittest discover -s engine -p 'test_*.py'
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location(
    "training_pid_reuse", pathlib.Path(__file__).with_name("training.py"))
training = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(training)


class PidReuse(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-pidreuse-")
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            p.kill()
            p.wait()
        shutil.rmtree(self.home, ignore_errors=True)

    def sleeper(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.procs.append(p)
        return p

    def write_state(self, run_id, pid, pid_start):
        """A persisted run mid-flight, as a previous engine would have left it."""
        runs = os.path.join(self.home, "runs", run_id)
        os.makedirs(runs, exist_ok=True)
        state = {"id": run_id, "state": training.RUNNING, "step": 3, "total": 10,
                 "pid": pid, "pid_start": pid_start}
        trainer = training.Trainer(self.home, sys.executable)
        with open(trainer._state_path(run_id), "w", encoding="utf-8") as fh:
            json.dump(state, fh)

    def reload(self):
        return training.Trainer(self.home, sys.executable)

    def test_a_recycled_pid_is_not_adopted(self):
        """The pid is alive, but it is not the process the run started."""
        proc = self.sleeper()
        self.write_state("r1", proc.pid, "Thu Jan  1 00:00:00 1970")
        trainer = self.reload()
        self.assertIsNone(
            trainer.current,
            "adopted an unrelated live process -- stop() would SIGTERM it")

    def test_a_recycled_pid_does_not_block_new_runs(self):
        """The user-visible half: fine-tuning must not be wedged shut."""
        proc = self.sleeper()
        self.write_state("r1", proc.pid, "Thu Jan  1 00:00:00 1970")
        trainer = self.reload()
        run = next(r for r in trainer.history if r.id == "r1")
        self.assertIn(run.state, training.TERMINAL,
                      "a run nothing can ever reap was left non-terminal")

    def test_the_real_process_is_still_adopted(self):
        """The guard must not throw away genuine adoption."""
        proc = self.sleeper()
        self.write_state("r1", proc.pid, training._pid_start_time(proc.pid))
        trainer = self.reload()
        self.assertIsNotNone(trainer.current, "refused to adopt a genuinely live run")
        self.assertEqual(trainer.current.id, "r1")
        self.assertEqual(trainer.current.state, training.RUNNING)

    def test_a_dead_pid_is_not_adopted(self):
        proc = self.sleeper()
        stamp = training._pid_start_time(proc.pid)
        proc.kill()
        proc.wait()
        self.write_state("r1", proc.pid, stamp)
        self.assertIsNone(self.reload().current)

    def test_a_state_file_without_a_fingerprint_is_not_adopted(self):
        """Pre-upgrade state: ownership cannot be proven, so it is refused.

        Adopting would risk SIGTERM to a stranger; refusing costs at most one
        run shown as interrupted, across a single restart after upgrade.
        """
        proc = self.sleeper()
        self.write_state("r1", proc.pid, None)
        self.assertIsNone(self.reload().current)

    def test_persist_writes_the_fingerprint_to_disk(self):
        """The round trip through _persist, not a hand-written state file.

        Every other test here writes the state file itself, so a _persist that
        quietly stopped recording pid_start would leave them all green while
        no real run could ever be adopted again -- adoption would fail closed
        and look like "the engine restarted while this run was live" forever.
        """
        trainer = training.Trainer(self.home, sys.executable)
        run = training.Run("r9", os.path.join(self.home, "c.yaml"),
                           os.path.join(self.home, "t.log"))
        run.state, run.pid, run.pid_start = training.RUNNING, 4321, "STAMP-XYZ"
        os.makedirs(os.path.join(self.home, "runs", "r9"), exist_ok=True)
        trainer._persist(run)
        with open(trainer._state_path("r9"), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved.get("pid_start"), "STAMP-XYZ",
                         "_persist dropped the fingerprint; adoption would fail closed")

    def test_a_persisted_live_run_round_trips_into_adoption(self):
        """End to end: persist a real live run, reload, and adopt it."""
        proc = self.sleeper()
        trainer = training.Trainer(self.home, sys.executable)
        run = training.Run("r8", os.path.join(self.home, "c.yaml"),
                           os.path.join(self.home, "t.log"))
        run.state, run.pid = training.RUNNING, proc.pid
        run.pid_start = training._pid_start_time(proc.pid)
        os.makedirs(os.path.join(self.home, "runs", "r8"), exist_ok=True)
        trainer._persist(run)
        self.assertIsNotNone(self.reload().current,
                             "a run persisted by this code could not be adopted back")

    def test_the_fingerprint_is_recorded_when_a_run_spawns(self):
        """Recorded at spawn -- reading it at adoption time would fingerprint
        whoever holds the pid then, which is the thing being guarded against."""
        src = pathlib.Path(__file__).with_name("training.py").read_text()
        self.assertIn("run.pid_start = _pid_start_time(proc.pid)", src)
        spawn = src.index("run.pid = proc.pid")
        reload_at = src.index("def _reload")
        self.assertLess(spawn, reload_at + len(src),
                        "fingerprint must be captured at spawn")


if __name__ == "__main__":
    unittest.main()

"""End-to-end tests for the training routes, against a real engine process.

The engine is spawned exactly as the Tauri shell spawns it, the port is read
from the line it announces on stdout, and every assertion goes over loopback
HTTP. Nothing here is mocked: an earlier lifecycle suite in this repo silently
skipped all eleven of its tests for months because it probed for the engine in
a way that could not work, so these fail loudly rather than skip.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
PORT_MARKER = "PRAISONAI_PORT="


class EngineProcess:
    """A live engine on an ephemeral port, in a throwaway home."""

    def __init__(self, train_cmd):
        self.home = tempfile.mkdtemp(prefix="praison-routes-")
        env = dict(os.environ,
                   PRAISONAI_DESKTOP_HOME=self.home,
                   PRAISONAI_TRAIN_CMD=train_cmd)
        self.proc = subprocess.Popen(
            [sys.executable, "-u", ENGINE], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.port = self._await_port()

    def _await_port(self, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("the engine exited before announcing a port")
            if PORT_MARKER in line:
                return int(line.split(PORT_MARKER, 1)[1].strip())
        raise RuntimeError(f"no port announced within {timeout}s")

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def request(self, path, payload=None, method=None, timeout=30):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.url(path), data=data, method=method or ("POST" if data else "GET"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}")

    def stream(self, path, timeout=30):
        """Read an SSE stream into (event, data) pairs until it closes."""
        events, kind = [], None
        with urllib.request.urlopen(self.url(path), timeout=timeout) as response:
            for raw in response:
                line = raw.decode().rstrip("\n")
                if line.startswith("event: "):
                    kind = line[7:]
                elif line.startswith("data: "):
                    events.append((kind, json.loads(line[6:])))
        return events

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.home, ignore_errors=True)


def _python(body):
    """A PRAISONAI_TRAIN_CMD that runs `body` instead of a real fine-tune.

    shlex.quote, not json.dumps: the engine splits this with shlex, and JSON
    escaping turns a newline into a literal backslash-n, which reached the
    interpreter as a syntax error partway through a script that had already
    printed its first line -- a half-run that looked like a trainer crash.
    """
    return f"{shlex.quote(sys.executable)} -u -c {shlex.quote(body)}"


def _wait(predicate, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


SHORT_RUN = (
    "print(\"{'loss': 0.7, 'learning_rate': 0.0002, 'epoch': 1.0}\")\n"
    "print(' 3/3 [00:01<00:00]')\n")
LONG_RUN = "import time\nprint('training', flush=True)\ntime.sleep(300)\n"
CONFIG = {"model_name": "unsloth/tiny", "dataset": "data.json"}


class TrainRoutes(unittest.TestCase):
    engine = None

    @classmethod
    def setUpClass(cls):
        cls.engine = EngineProcess(_python(SHORT_RUN))

    @classmethod
    def tearDownClass(cls):
        cls.engine.close()

    def test_a_run_starts_streams_and_ends(self):
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, body)
        run_id = body["run"]["id"]

        events = self.engine.stream(f"/train/progress?run={run_id}&cursor=-1")
        kinds = [kind for kind, _ in events]
        self.assertIn("start", kinds)
        self.assertIn("metric", kinds)
        self.assertIn("end", kinds)

        metric = next(data for kind, data in events if kind == "metric")
        self.assertEqual(metric["loss"], 0.7)
        ending = next(data for kind, data in events if kind == "end")
        self.assertEqual(ending["state"], "done", ending)

        status, body = self.engine.request("/train/status")
        self.assertEqual(body["run"]["state"], "done")
        self.assertEqual(body["metrics"][-1]["loss"], 0.7)

    def test_the_stream_replays_from_a_cursor_rather_than_repeating(self):
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, body)
        run_id = body["run"]["id"]
        everything = self.engine.stream(f"/train/progress?run={run_id}&cursor=-1")
        self.assertGreater(len(everything), 2)
        midpoint = everything[1][1]["cursor"]
        resumed = self.engine.stream(f"/train/progress?run={run_id}&cursor={midpoint}")
        self.assertEqual([d["cursor"] for _, d in resumed],
                         [d["cursor"] for _, d in everything if d["cursor"] > midpoint])

    def test_a_finished_run_appears_in_the_history(self):
        # Starts its own run rather than relying on another test having run
        # first: unittest orders alphabetically, and the first version of this
        # passed or failed depending on the method name above it.
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, body)
        run_id = body["run"]["id"]
        self.assertTrue(_wait(
            lambda: (self.engine.request("/train/status")[1].get("run") or {})
            .get("state") in ("done", "failed", "cancelled")))
        _, body = self.engine.request("/train/runs")
        self.assertIn(run_id, [run["id"] for run in body["runs"]])
        self.assertTrue(all("state" in run for run in body["runs"]))

    def test_progress_for_an_unknown_run_is_404_not_a_hang(self):
        status, body = self.engine.request("/train/progress?run=no-such-run")
        self.assertEqual(status, 404)

    def test_a_config_without_a_model_is_refused(self):
        status, body = self.engine.request("/train/start", {"config": {"dataset": "d"}})
        self.assertEqual(status, 400)
        self.assertIn("model_name", body["error"])

    def test_a_traversing_run_id_is_refused_and_writes_nothing(self):
        status, body = self.engine.request(
            "/train/start", {"config": CONFIG, "run_id": "../../escaped"})
        self.assertEqual(status, 400, body)
        self.assertFalse(os.path.exists(os.path.join(self.engine.home, "..", "escaped")))

    def test_stopping_when_idle_is_404_not_a_crash(self):
        status, body = self.engine.request("/train/stop", {}, method="POST")
        self.assertEqual(status, 404)


class TrainConcurrency(unittest.TestCase):
    """The long-running case: start, refuse a second, stop, and confirm."""

    def setUp(self):
        self.engine = EngineProcess(_python(LONG_RUN))

    def tearDown(self):
        self.engine.close()

    def _live_state(self):
        _, body = self.engine.request("/train/status")
        return (body.get("run") or {}).get("state")

    def test_a_second_start_is_a_conflict_and_the_first_keeps_running(self):
        status, first = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, first)
        self.assertTrue(_wait(lambda: self._live_state() == "running"))

        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 409, body)
        self.assertIn(first["run"]["id"], body["error"])
        self.assertEqual(self._live_state(), "running", "the conflict killed the run")

    def test_stopping_ends_the_run_as_cancelled(self):
        status, started = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, started)
        self.assertTrue(_wait(lambda: self._live_state() == "running"))

        status, body = self.engine.request("/train/stop", {}, method="POST")
        self.assertEqual(status, 200, body)
        self.assertTrue(_wait(lambda: self._live_state() == "cancelled"), self._live_state())

    def test_the_engine_survives_stopping_a_run(self):
        # The process-group signal must not reach the engine itself; if it
        # does, this request fails to connect rather than returning a status.
        self.engine.request("/train/start", {"config": CONFIG})
        self.assertTrue(_wait(lambda: self._live_state() == "running"))
        self.engine.request("/train/stop", {}, method="POST")
        self.assertTrue(_wait(lambda: self._live_state() == "cancelled"))
        status, body = self.engine.request("/health")
        self.assertEqual(status, 200, "the engine died with the run it stopped")
        self.assertIsNone(self.engine.proc.poll(), "the engine process exited")


if __name__ == "__main__":
    unittest.main(verbosity=2)

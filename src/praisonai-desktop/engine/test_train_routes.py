"""End-to-end tests for the training routes, against a real engine process.

The engine is spawned exactly as the Tauri shell spawns it, the port is read
from the line it announces on stdout, and every assertion goes over loopback
HTTP. Nothing here is mocked: an earlier lifecycle suite in this repo silently
skipped all eleven of its tests for months because it probed for the engine in
a way that could not work, so these fail loudly rather than skip.
"""

import atexit
import hashlib
import json
import os
import pathlib
import shlex
import shutil
import signal
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
            # An unrouted path gets BaseHTTPRequestHandler's own HTML error
            # page, which is a perfectly good 404 but is not JSON. The status
            # is the thing under test there.
            raw = err.read()
            try:
                return err.code, json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return err.code, {}

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


_SCRIPTS = tempfile.mkdtemp(prefix="praison-train-scripts-")
atexit.register(shutil.rmtree, _SCRIPTS, True)


def _python(body):
    """A PRAISONAI_TRAIN_CMD that runs `body` instead of a real fine-tune.

    The body goes into a file rather than `-c`. The engine splits this command
    with POSIX rules on Unix and Windows rules on Windows, and the two disagree
    about a string containing a quote: shlex.quote escapes an inner `'` as the
    concatenation `'"'"'`, which POSIX reassembles into one token and Windows
    splits into seven. Every script here prints something, so every one of them
    contains a quote, and the whole training suite failed on Windows for that
    reason alone.

    A path has no newlines and no quotes, so both rule sets agree about it.
    """
    # A content hash, not hash(): the built-in is salted per process, and two
    # different bodies landing on one filename would have the second silently
    # overwrite the first.
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    script = pathlib.Path(_SCRIPTS) / f"case-{digest}.py"
    script.write_text(body, encoding="utf-8")
    return f"{shlex.quote(sys.executable)} -u {shlex.quote(str(script))}"


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


class LongRunReplay(unittest.TestCase):
    """Opening the view on a run that has outlived its event buffer.

    A tqdm refresh emits both a log and a progress event, so a real fine-tune
    passes 4000 events in about twenty minutes. Every fresh tab opens the
    stream at cursor=-1, which is exactly the case that has to work.
    """

    def setUp(self):
        # A run that emits far more than the ring can hold, then ends.
        self.engine = EngineProcess(_python(
            "import sys\n"
            "for i in range(4500):\n"
            "    print(f'{i}/4500 [00:01<00:02]')\n"
            "sys.stdout.flush()\n"))

    def tearDown(self):
        self.engine.close()

    def test_a_client_that_missed_the_start_still_receives_the_log(self):
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, body)
        run_id = body["run"]["id"]
        self.assertTrue(_wait(
            lambda: (self.engine.request("/train/status")[1].get("run") or {})
            .get("state") in ("done", "failed", "cancelled"), 60))

        events = self.engine.stream(f"/train/progress?run={run_id}&cursor=-1", timeout=30)
        kinds = [kind for kind, _ in events]
        resyncs = kinds.count("resync")
        self.assertLessEqual(resyncs, 2,
                             f"the stream resynced {resyncs} times instead of catching up")
        self.assertTrue(any(k == "log" for k in kinds),
                        "a client that missed the beginning received no output at all")
        self.assertIn("end", kinds, "the stream never delivered the ending")

    def test_the_stream_closes_when_the_run_is_over(self):
        # The whole test would hang rather than fail if this regressed, so it
        # is bounded by the stream timeout.
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        run_id = body["run"]["id"]
        self.assertTrue(_wait(
            lambda: (self.engine.request("/train/status")[1].get("run") or {})
            .get("state") in ("done", "failed", "cancelled"), 60))
        events = self.engine.stream(f"/train/progress?run={run_id}&cursor=-1", timeout=30)
        self.assertIn("end", [k for k, _ in events])


class StopRouting(unittest.TestCase):
    """Which run a stop request actually stops."""

    def setUp(self):
        self.engine = EngineProcess(_python(LONG_RUN))

    def tearDown(self):
        self.engine.close()

    def _start(self):
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, body)
        self.assertTrue(_wait(
            lambda: (self.engine.request("/train/status")[1].get("run") or {})
            .get("state") == "running"))
        return body["run"]["id"]

    def _state(self):
        return (self.engine.request("/train/status")[1].get("run") or {}).get("state")

    def test_stopping_by_the_live_id_works(self):
        run_id = self._start()
        status, _ = self.engine.request(f"/train/stop/{run_id}", {}, method="POST")
        self.assertEqual(status, 200)
        self.assertTrue(_wait(lambda: self._state() == "cancelled"))

    def test_a_stale_id_is_refused(self):
        self._start()
        status, _ = self.engine.request("/train/stop/run-from-a-stale-tab", {}, method="POST")
        self.assertEqual(status, 409)
        self.assertEqual(self._state(), "running")

    def test_a_stale_id_with_a_trailing_slash_is_still_refused(self):
        # rsplit("/") on ".../stale/" yields "", which is falsy -- so the guard
        # was skipped entirely and the live run was killed by a stale tab.
        self._start()
        status, _ = self.engine.request("/train/stop/run-from-a-stale-tab/", {}, method="POST")
        self.assertEqual(status, 409, "a trailing slash bypassed the stale-tab guard")
        self.assertEqual(self._state(), "running")

    def test_a_path_that_merely_starts_with_the_route_is_not_the_route(self):
        self._start()
        status, _ = self.engine.request("/train/stopXXXX", {}, method="POST")
        self.assertEqual(status, 404, "/train/stopXXXX was treated as /train/stop")
        self.assertEqual(self._state(), "running")

    def test_a_query_string_does_not_hide_the_run_id(self):
        run_id = self._start()
        status, _ = self.engine.request(f"/train/stop/{run_id}?force=1", {}, method="POST")
        self.assertEqual(status, 200, "a legitimate stop was refused because of a query string")
        self.assertTrue(_wait(lambda: self._state() == "cancelled"))

    def test_stopping_a_run_that_has_not_spawned_yet_still_stops_it(self):
        # start() returns as soon as the supervisor thread is created, so there
        # is a window where the process does not exist. A stop in that window
        # was recorded and then overwritten by "running", and the fine-tune ran
        # to completion after the user cancelled it.
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, body)
        status, _ = self.engine.request("/train/stop", {}, method="POST")
        self.assertEqual(status, 200)
        self.assertTrue(_wait(lambda: self._state() in ("cancelled", "done", "failed"), 30))
        self.assertEqual(self._state(), "cancelled",
                         "the run continued after the user stopped it")

    def test_a_malformed_cursor_is_refused_rather_than_crashing(self):
        run_id = self._start()
        status, _ = self.engine.request(f"/train/progress?run={run_id}&cursor=abc")
        self.assertEqual(status, 400)


class MethodPreflight(unittest.TestCase):
    """A config that cannot work must fail now, not after the download.

    The trainer validates method requirements inside train_model(), which runs
    after several gigabytes have been fetched and the model loaded in 4-bit.
    Anything decidable from the config alone belongs before that.
    """

    def setUp(self):
        self.engine = EngineProcess(_python("print('ok')"))

    def tearDown(self):
        self.engine.close()

    def test_grpo_without_reward_functions_is_refused_immediately(self):
        status, body = self.engine.request(
            "/train/start", {"config": dict(CONFIG, method="grpo")})
        self.assertEqual(status, 400, body)
        self.assertIn("reward_funcs", body.get("error", ""))

    def test_grpo_with_reward_functions_is_accepted(self):
        status, body = self.engine.request(
            "/train/start", {"config": dict(CONFIG, method="grpo",
                                            reward_funcs=["mod:fn"])})
        self.assertEqual(status, 200, body)

    def test_the_default_method_still_starts(self):
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, body)

    def test_a_preference_method_is_not_blocked_by_the_preflight(self):
        # Its columns depend on the dataset, which we cannot inspect without
        # fetching it -- so the preflight must not guess and refuse.
        status, body = self.engine.request(
            "/train/start", {"config": dict(CONFIG, method="dpo")})
        self.assertEqual(status, 200, body)


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


class ChatsListing(unittest.TestCase):
    """A stray file in chats/ must not drop the connection.

    list_chats() catches (OSError, ValueError) and reports the file as a
    corrupt row -- but valid JSON that is not an object (the app's own Export
    emits an array) reached c.get(...) and raised AttributeError, which
    escaped the handler and closed the connection with no status. The front
    end then blamed the engine for being down.
    """

    def setUp(self):
        self.engine = EngineProcess(_python("print('ok')"))
        self.chats = pathlib.Path(self.engine.home) / "chats"
        self.chats.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.engine.close()

    def test_a_json_array_in_chats_is_a_corrupt_row_not_a_dropped_connection(self):
        (self.chats / "backup.json").write_text(json.dumps([{"id": "good1"}]))
        status, body = self.engine.request("/chats")
        self.assertEqual(status, 200, body)
        rows = body["chats"]
        corrupt = [r for r in rows if r.get("corrupt")]
        self.assertTrue(corrupt, "the array file was not surfaced as corrupt")
        self.assertIn("backup", [r["id"] for r in corrupt])

    def test_a_json_array_does_not_drop_projects_or_search(self):
        # /projects and /search call load_chat() on every file list_chats()
        # walks -- including the array. Hardening only list_chats() left those
        # two routes crashing on load_chat().get(...) with the same file.
        (self.chats / "backup.json").write_text(json.dumps([{"id": "good1"}]))
        status, body = self.engine.request("/projects")
        self.assertEqual(status, 200, body)
        status, body = self.engine.request("/search?q=hello")
        self.assertEqual(status, 200, body)


@unittest.skipIf(os.name == "nt", "POSIX orphaning; Windows uses taskkill /T")
class QuitStopsTheTrainer(unittest.TestCase):
    """Quitting the engine must take the fine-tune down with it.

    The trainer is spawned in its own session, so a signal aimed at the
    engine's process group never reaches it. If the engine exits without
    calling Trainer.stop(), the run is reparented to init (ppid 1) and keeps
    the GPU with nothing left that can find it -- the exact failure this
    guards against.
    """

    def setUp(self):
        # A stub trainer that records its pid, then sleeps well past the test.
        self.pidfile = os.path.join(
            tempfile.mkdtemp(prefix="praison-trainer-pid-"), "pid")
        body = (
            "import os, time\n"
            f"open({self.pidfile!r}, 'w').write(str(os.getpid()))\n"
            "print('training', flush=True)\n"
            "time.sleep(300)\n")
        self.engine = EngineProcess(_python(body))

    def tearDown(self):
        self.engine.close()
        shutil.rmtree(os.path.dirname(self.pidfile), ignore_errors=True)

    def _trainer_pid(self):
        if not os.path.exists(self.pidfile):
            return None
        text = pathlib.Path(self.pidfile).read_text().strip()
        return int(text) if text else None

    def _alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def test_quitting_the_engine_kills_the_running_trainer(self):
        status, body = self.engine.request("/train/start", {"config": CONFIG})
        self.assertEqual(status, 200, body)
        self.assertTrue(_wait(
            lambda: (self.engine.request("/train/status")[1].get("run") or {})
            .get("state") == "running"))
        self.assertTrue(_wait(lambda: self._trainer_pid() is not None),
                        "the stub trainer never recorded its pid")
        pid = self._trainer_pid()

        # Quit exactly as the Tauri shell does: one SIGTERM to the engine.
        self.engine.proc.send_signal(signal.SIGTERM)
        self.engine.proc.wait(timeout=15)

        self.assertTrue(_wait(lambda: not self._alive(pid), 10),
                        f"the trainer (pid {pid}) outlived the engine quit")


if __name__ == "__main__":
    unittest.main(verbosity=2)

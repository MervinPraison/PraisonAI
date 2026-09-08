import asyncio
import unittest


class _FakeStateStore:
    def __init__(self, data):
        self._data = dict(data)

    def scan_prefix(self, prefix):
        return [k for k in self._data if k.startswith(prefix)]

    def get(self, key):
        return self._data.get(key)


class _AsyncStateStore:
    """State store whose ``get``/``set`` are coroutines.

    Mirrors an async backend so a sync completion hook reaching ``get`` from
    inside a running event loop exercises the ``_call_store`` read path.
    """

    def __init__(self, data=None):
        self._data = dict(data or {})

    async def get(self, key):
        return self._data.get(key)

    async def set(self, key, value):
        self._data[key] = value


class TestPraisonAIDBRunsAndTraces(unittest.TestCase):
    def _make_db(self, state_data):
        from praisonai.db.adapter import PraisonAIDB

        db = PraisonAIDB()
        db._state_store = _FakeStateStore(state_data)
        db._initialized = True
        return db

    def test_get_runs_returns_sorted_and_limited_results(self):
        db = self._make_db(
            {
                "run:s1:r1": {"run_id": "r1", "started_at": 10},
                "run:s1:r2": {"run_id": "r2", "started_at": 20},
                "run:s2:r3": {"run_id": "r3", "started_at": 30},
            }
        )

        runs = db.get_runs("s1", limit=1)
        self.assertEqual([r["run_id"] for r in runs], ["r2"])

    def test_get_runs_limit_zero_returns_empty_list(self):
        db = self._make_db({"run:s1:r1": {"run_id": "r1", "started_at": 10}})
        self.assertEqual(db.get_runs("s1", limit=0), [])

    def test_get_traces_filters_by_session_and_user_then_sorts(self):
        db = self._make_db(
            {
                "trace:t1": {"trace_id": "t1", "session_id": "s1", "user_id": "u1", "started_at": 10},
                "trace:t2": {"trace_id": "t2", "session_id": "s2", "user_id": "u1", "started_at": 40},
                "trace:t3": {"trace_id": "t3", "session_id": "s1", "user_id": "u2", "started_at": 30},
            }
        )

        traces = db.get_traces(session_id="s1", user_id="u2", limit=1)
        self.assertEqual([t["trace_id"] for t in traces], ["t3"])

    def test_get_traces_limit_zero_returns_empty_list(self):
        db = self._make_db({"trace:t1": {"trace_id": "t1", "started_at": 10}})
        self.assertEqual(db.get_traces(limit=0), [])

    def test_state_get_is_a_read_op(self):
        """State ``get`` must be classified as a read so the run/trace/span
        completion hooks (get-then-set) never fire-and-forget the read-back and
        overwrite the persisted record with a partial dict."""
        from praisonai.db.adapter import PraisonAIDB

        self.assertIn("get", PraisonAIDB._READ_OPS)

    def test_on_run_end_merges_and_persists_in_running_loop(self):
        """Regression (#4945): a sync completion hook reached from inside a
        running loop must NOT be silently dropped. Previously ``get`` (a read
        op) raised ``RuntimeError`` inside the loop, the core caller swallowed
        it, and the ``set`` never ran — leaving the run stuck ``status="running"``
        forever. The fix runs the whole get+merge+set as one coroutine on the
        bridge, so the completion actually persists while preserving the
        pre-existing run_id/started_at/input_content fields."""
        from praisonai.db.adapter import PraisonAIDB

        db = PraisonAIDB()
        db._state_store = _AsyncStateStore(
            {"run:s1:r1": {"run_id": "r1", "started_at": 10, "input_content": "hi"}}
        )
        db._initialized = True

        async def _main():
            # Must not raise inside a running loop.
            db.on_run_end("s1", "r1", output_content="done", status="completed")
            # The write is a tracked fire-and-forget on the bridge; flush it.
            await asyncio.to_thread(db.flush_pending_writes)

        asyncio.run(_main())

        record = db._state_store._data["run:s1:r1"]
        # Pre-existing fields preserved; completion fields merged in.
        self.assertEqual(record["run_id"], "r1")
        self.assertEqual(record["started_at"], 10)
        self.assertEqual(record["input_content"], "hi")
        self.assertEqual(record["output_content"], "done")
        self.assertEqual(record["status"], "completed")
        self.assertIn("ended_at", record)

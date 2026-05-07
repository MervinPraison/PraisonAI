import unittest


class _FakeStateStore:
    def __init__(self, data):
        self._data = dict(data)

    def scan_prefix(self, prefix):
        return [k for k in self._data if k.startswith(prefix)]

    def get(self, key):
        return self._data.get(key)


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

"""
Unit tests for job-to-job output chaining (``context_from``).

Tests:
- ScheduleJob model fields + serialisation round-trip (list, bare string,
  defaults omitted from payload).
- ScheduleRunner.resolve_context() resolving upstream output by id and by name.
- Bounded truncation via context_max_chars.
- Missing-upstream reporting for the on_missing_context policy.
"""

import tempfile


def _fresh_store():
    from praisonaiagents.scheduler.store import FileScheduleStore

    tmp = tempfile.mkdtemp()
    return FileScheduleStore(store_dir=tmp)


class TestContextFromModel:
    def test_defaults_are_stateless(self):
        from praisonaiagents.scheduler.models import ScheduleJob

        job = ScheduleJob(name="j")
        assert job.context_from is None
        assert job.context_max_chars == 4000
        assert job.on_missing_context == "run"
        # Stateless jobs stay byte-for-byte unchanged.
        assert "context_from" not in job.to_dict()
        assert "context_max_chars" not in job.to_dict()
        assert "on_missing_context" not in job.to_dict()

    def test_roundtrip_list(self):
        from praisonaiagents.scheduler.models import ScheduleJob

        job = ScheduleJob(
            name="brief",
            context_from=["fetch_inputs"],
            context_max_chars=1000,
            on_missing_context="skip",
        )
        d = job.to_dict()
        assert d["context_from"] == ["fetch_inputs"]
        assert d["context_max_chars"] == 1000
        assert d["on_missing_context"] == "skip"
        back = ScheduleJob.from_dict(d)
        assert back.context_from == ["fetch_inputs"]
        assert back.context_max_chars == 1000
        assert back.on_missing_context == "skip"

    def test_bare_string_coerced_to_list(self):
        from praisonaiagents.scheduler.models import ScheduleJob

        job = ScheduleJob.from_dict({"name": "brief", "context_from": "fetch_inputs"})
        assert job.context_from == ["fetch_inputs"]

    def test_empty_refs_normalise_to_none(self):
        from praisonaiagents.scheduler.models import ScheduleJob

        job = ScheduleJob.from_dict({"name": "brief", "context_from": ["", "  "]})
        assert job.context_from is None

    def test_defaults_omitted_when_only_context_from_set(self):
        from praisonaiagents.scheduler.models import ScheduleJob

        job = ScheduleJob(name="brief", context_from=["a"])
        d = job.to_dict()
        assert d["context_from"] == ["a"]
        assert "context_max_chars" not in d
        assert "on_missing_context" not in d


class TestResolveContext:
    def test_no_context_from_returns_empty(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        runner = ScheduleRunner(store)
        ctx, missing = runner.resolve_context(ScheduleJob(name="solo"))
        assert ctx == ""
        assert missing == []

    def test_resolves_by_name(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        upstream = ScheduleJob(name="fetch_inputs")
        store.add(upstream)
        store.log_run(
            job_id=upstream.id,
            status="succeeded",
            result="calendar + unread email summary",
            job_name=upstream.name,
        )
        runner = ScheduleRunner(store)
        brief = ScheduleJob(name="brief", context_from=["fetch_inputs"])
        ctx, missing = runner.resolve_context(brief)
        assert missing == []
        assert "### Context from 'fetch_inputs'" in ctx
        assert "calendar + unread email summary" in ctx

    def test_resolves_by_id(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        upstream = ScheduleJob(name="fetch_inputs")
        store.add(upstream)
        store.log_run(job_id=upstream.id, status="succeeded", result="data")
        runner = ScheduleRunner(store)
        brief = ScheduleJob(name="brief", context_from=[upstream.id])
        ctx, missing = runner.resolve_context(brief)
        assert missing == []
        assert "data" in ctx

    def test_picks_most_recent_successful(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        up = ScheduleJob(name="fetch")
        store.add(up)
        store.log_run(job_id=up.id, status="succeeded", result="old")
        store.log_run(job_id=up.id, status="failed", error="boom")
        store.log_run(job_id=up.id, status="succeeded", result="new")
        runner = ScheduleRunner(store)
        ctx, _ = runner.resolve_context(ScheduleJob(name="d", context_from=["fetch"]))
        assert "new" in ctx
        assert "old" not in ctx

    def test_truncates_to_budget(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        up = ScheduleJob(name="fetch")
        store.add(up)
        store.log_run(job_id=up.id, status="succeeded", result="x" * 500)
        runner = ScheduleRunner(store)
        job = ScheduleJob(name="d", context_from=["fetch"], context_max_chars=100)
        ctx, _ = runner.resolve_context(job)
        body = ctx.split("\n", 1)[1]
        assert body == "x" * 100

    def test_non_positive_budget_truncates_to_empty(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        up = ScheduleJob(name="fetch")
        store.add(up)
        store.log_run(job_id=up.id, status="succeeded", result="y" * 500)
        runner = ScheduleRunner(store)
        for bad in (0, -100):
            job = ScheduleJob(name="d", context_from=["fetch"], context_max_chars=bad)
            ctx, _ = runner.resolve_context(job)
            body = ctx.split("\n", 1)[1]
            assert body == "", f"budget={bad} should truncate to empty, got {body!r}"

    def test_missing_upstream_reported(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        runner = ScheduleRunner(store)
        job = ScheduleJob(name="d", context_from=["never_ran"])
        ctx, missing = runner.resolve_context(job)
        assert ctx == ""
        assert missing == ["never_ran"]

    def test_only_failed_run_is_missing(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        up = ScheduleJob(name="fetch")
        store.add(up)
        store.log_run(job_id=up.id, status="failed", error="boom")
        runner = ScheduleRunner(store)
        _, missing = runner.resolve_context(ScheduleJob(name="d", context_from=["fetch"]))
        assert missing == ["fetch"]

    def test_multiple_upstreams(self):
        from praisonaiagents.scheduler.models import ScheduleJob
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = _fresh_store()
        a = ScheduleJob(name="a")
        b = ScheduleJob(name="b")
        store.add(a)
        store.add(b)
        store.log_run(job_id=a.id, status="succeeded", result="AAA")
        store.log_run(job_id=b.id, status="succeeded", result="BBB")
        runner = ScheduleRunner(store)
        job = ScheduleJob(name="d", context_from=["a", "b"])
        ctx, missing = runner.resolve_context(job)
        assert missing == []
        assert "AAA" in ctx and "BBB" in ctx
        assert ctx.index("AAA") < ctx.index("BBB")

"""
Unit tests for per-identity (principal) scoping of automations & suggestions.

Covers the multi-user isolation added to the core scheduler data model:
- ``Suggestion.principal`` + ``SuggestionStore`` list/accept/dismiss filters
- ``ScheduleJob.principal`` + ``FileScheduleStore``/``ConfigYamlScheduleStore``
  ``list(principal=...)`` filters
- Backward compatibility: ``principal=None`` preserves global behaviour and
  round-trips through serialisation.
"""

import os
import tempfile


class TestSuggestionPrincipal:
    """Per-identity scoping for the suggestion store."""

    def _store(self):
        from praisonaiagents.scheduler.suggestion_store import SuggestionStore

        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        return SuggestionStore(path=tmp.name)

    def _sug(self, sid, principal=None):
        from praisonaiagents.scheduler.suggestion_store import Suggestion

        return Suggestion(id=sid, blueprint_name="bp-" + sid, principal=principal)

    def test_list_pending_isolates_by_principal(self):
        store = self._store()
        store.add(self._sug("a", principal="alice"))
        store.add(self._sug("b", principal="bob"))

        alice = [s.id for s in store.list_pending(principal="alice")]
        bob = [s.id for s in store.list_pending(principal="bob")]

        assert alice == ["a"]
        assert bob == ["b"]

    def test_list_pending_none_is_global(self):
        store = self._store()
        store.add(self._sug("a", principal="alice"))
        store.add(self._sug("b", principal="bob"))

        ids = sorted(s.id for s in store.list_pending())
        assert ids == ["a", "b"]

    def test_accept_rejects_cross_owner(self):
        store = self._store()
        store.add(self._sug("a", principal="alice"))

        assert store.accept("a", principal="bob") is False
        assert store.get("a").accepted is False
        assert store.accept("a", principal="alice") is True
        assert store.get("a").accepted is True

    def test_dismiss_rejects_cross_owner(self):
        store = self._store()
        store.add(self._sug("a", principal="alice"))

        assert store.dismiss("a", principal="bob") is False
        assert store.get("a").dismissed is False
        assert store.dismiss("a", principal="alice") is True
        assert store.get("a").dismissed is True

    def test_accept_none_principal_backward_compatible(self):
        store = self._store()
        store.add(self._sug("a", principal="alice"))
        assert store.accept("a") is True

    def test_principal_round_trips_through_disk(self):
        from praisonaiagents.scheduler.suggestion_store import SuggestionStore

        store = self._store()
        store.add(self._sug("a", principal="alice"))
        reloaded = SuggestionStore(path=store._path)
        assert reloaded.get("a").principal == "alice"


class TestScheduleJobPrincipal:
    """Per-identity scoping for the schedule stores."""

    def _job(self, name, principal=None):
        from praisonaiagents.scheduler.models import ScheduleJob, Schedule

        return ScheduleJob(
            name=name,
            schedule=Schedule(kind="every", every_seconds=60),
            message="hi",
            principal=principal,
        )

    def test_model_round_trip(self):
        from praisonaiagents.scheduler.models import ScheduleJob

        job = self._job("j", principal="alice")
        d = job.to_dict()
        assert d["principal"] == "alice"
        assert ScheduleJob.from_dict(d).principal == "alice"

    def test_model_omits_none_principal(self):
        job = self._job("j")
        assert "principal" not in job.to_dict()

    def test_file_store_list_isolates(self):
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            store.add(self._job("ja", principal="alice"))
            store.add(self._job("jb", principal="bob"))

            alice = [j.name for j in store.list(principal="alice")]
            assert alice == ["ja"]
            assert len(store.list()) == 2

    def test_config_store_list_isolates(self):
        from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.yaml")
            store = ConfigYamlScheduleStore(config_path=path)
            store.add(self._job("ja", principal="alice"))
            store.add(self._job("jb", principal="bob"))

            bob = [j.name for j in store.list(principal="bob")]
            assert bob == ["jb"]
            assert len(store.list()) == 2

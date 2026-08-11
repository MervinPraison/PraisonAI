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

    def test_pending_cap_is_per_principal(self):
        """One tenant filling the cap must not block another tenant's add."""
        from praisonaiagents.scheduler.suggestion_store import (
            MAX_PENDING_CAP,
            Suggestion,
        )

        store = self._store()
        for i in range(MAX_PENDING_CAP):
            assert store.add(
                Suggestion(id=f"a{i}", blueprint_name=f"bp{i}", principal="alice")
            ) is True
        # Alice is now at the cap → her next add is rejected …
        assert store.add(
            Suggestion(id="a_over", blueprint_name="bp-over", principal="alice")
        ) is False
        # … but Bob (a different principal) is unaffected.
        assert store.add(
            Suggestion(id="b0", blueprint_name="bp-b", principal="bob")
        ) is True

    def test_dedup_window_is_per_principal(self):
        """Identical blueprint+slots from different owners are not deduped."""
        from praisonaiagents.scheduler.suggestion_store import Suggestion

        store = self._store()
        assert store.add(
            Suggestion(id="a", blueprint_name="brief", slots={"hour": 8}, principal="alice")
        ) is True
        # Same blueprint+slots, same owner → deduped.
        assert store.add(
            Suggestion(id="a2", blueprint_name="brief", slots={"hour": 8}, principal="alice")
        ) is False
        # Same blueprint+slots, different owner → allowed.
        assert store.add(
            Suggestion(id="b", blueprint_name="brief", slots={"hour": 8}, principal="bob")
        ) is True


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

    def test_file_store_remove_by_name_scoped(self):
        """A user cannot delete another user's job by guessing its name."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            store.add(self._job("shared-name", principal="alice"))

            # Cross-owner removal is refused and leaves the job intact.
            assert store.remove_by_name("shared-name", principal="bob") is False
            assert store.get_by_name("shared-name") is not None
            # Owner removal succeeds.
            assert store.remove_by_name("shared-name", principal="alice") is True
            assert store.get_by_name("shared-name") is None

    def test_file_store_get_by_name_scoped(self):
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            store.add(self._job("j", principal="alice"))

            assert store.get_by_name("j", principal="bob") is None
            assert store.get_by_name("j", principal="alice") is not None
            # None (global) still finds it — backward compatible.
            assert store.get_by_name("j") is not None

    def test_config_store_remove_by_name_scoped(self):
        from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.yaml")
            store = ConfigYamlScheduleStore(config_path=path)
            store.add(self._job("shared-name", principal="alice"))

            assert store.remove_by_name("shared-name", principal="bob") is False
            assert store.get_by_name("shared-name") is not None
            assert store.remove_by_name("shared-name", principal="alice") is True
            assert store.get_by_name("shared-name") is None

    def test_remove_by_name_none_is_backward_compatible(self):
        """Default (principal=None) removal is unscoped as before."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        with tempfile.TemporaryDirectory() as d:
            store = FileScheduleStore(store_dir=d)
            store.add(self._job("j", principal="alice"))
            assert store.remove_by_name("j") is True

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


class TestScheduleToolsDefaultPrincipal:
    """The agent-callable tools default ``principal`` from the session context.

    This is the surface-level fix for issue #3785: ``schedule_add`` /
    ``schedule_list`` / ``schedule_remove`` must isolate per gateway user by
    reading ``SessionContext.unified_user_id`` when no explicit principal is
    passed, while staying globally-scoped for CLI / single-user (no identity).
    """

    def setup_method(self):
        """Snapshot the global schedule stores so each test is isolated."""
        from praisonaiagents.tools import schedule_tools
        from praisonaiagents import scheduler as _scheduler

        self._saved_tool_store = schedule_tools._store_instance
        try:
            self._saved_default_store = _scheduler.get_default_store()
        except Exception:
            self._saved_default_store = None

    def teardown_method(self):
        """Restore both global stores so later tests never see a temp-dir store."""
        from praisonaiagents.tools import schedule_tools
        from praisonaiagents import scheduler as _scheduler

        schedule_tools._store_instance = self._saved_tool_store
        try:
            _scheduler.set_default_store(self._saved_default_store)
        except Exception:
            pass

    def _fresh_store(self, tmp_dir):
        from praisonaiagents.scheduler.store import FileScheduleStore
        from praisonaiagents.tools import schedule_tools

        store = FileScheduleStore(store_dir=tmp_dir)
        schedule_tools.set_store(store)
        return store

    def test_tools_isolate_by_session_context(self):
        from praisonaiagents.session.context import (
            set_session_context,
            clear_session_context,
        )
        from praisonaiagents.tools.schedule_tools import (
            schedule_add,
            schedule_list,
            schedule_remove,
        )

        with tempfile.TemporaryDirectory() as d:
            store = self._fresh_store(d)

            tok = set_session_context(unified_user_id="alice")
            try:
                schedule_add("brief", "daily", message="Alice brief")
            finally:
                clear_session_context(tok)

            tok = set_session_context(unified_user_id="bob")
            try:
                # Bob only sees his own (empty) list …
                assert "No schedules found" in schedule_list()
                # … cannot remove Alice's job by name …
                assert "not found" in schedule_remove("brief")
                # … and can add his own under the same name (isolated).
                assert "added" in schedule_add("brief", "daily", message="Bob brief")
                listed = schedule_list()
                assert "Bob brief" in listed and "Alice brief" not in listed
            finally:
                clear_session_context(tok)

            # The underlying store still holds both, tagged per owner.
            assert {j.principal for j in store.list()} == {"alice", "bob"}

    def test_tools_global_without_identity(self):
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_list

        with tempfile.TemporaryDirectory() as d:
            self._fresh_store(d)
            # No session context → no identity → global pool (CLI behaviour).
            schedule_add("cli-job", "daily", message="cli")
            listed = schedule_list()
            assert "cli-job" in listed

    def test_session_identity_cannot_be_impersonated(self):
        """A tool ``principal`` argument must NOT override an authenticated
        session identity (issue #3785 security review).

        An agent (or prompt-injected content) that passes ``principal=<victim>``
        while a session identity is installed must be pinned to the session
        owner — never the caller-selected value.
        """
        from praisonaiagents.session.context import (
            set_session_context,
            clear_session_context,
        )
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_list

        with tempfile.TemporaryDirectory() as d:
            store = self._fresh_store(d)
            tok = set_session_context(unified_user_id="alice")
            try:
                # Alice's turn attempts to impersonate Carol via the tool arg.
                schedule_add("j", "daily", principal="carol")
                # Alice (the authenticated session) sees the job she created …
                assert "j" in schedule_list()
                # … and the explicit principal arg cannot re-scope the read to
                # another tenant while a session is installed.
                assert "j" in schedule_list(principal="carol")
            finally:
                clear_session_context(tok)
            # The job is owned by the authenticated session (alice), NOT carol.
            assert store.get_by_name("j").principal == "alice"
            # Carol's own store view is empty — she was never impersonated.
            assert store.list(principal="carol") == []

    def test_explicit_principal_used_without_session(self):
        """With no session installed, an explicit principal is honoured.

        This is the trusted path (CLI / gateway bridge) — no ambient identity
        exists to protect, so the caller-provided value scopes ownership.
        """
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_list

        with tempfile.TemporaryDirectory() as d:
            store = self._fresh_store(d)
            schedule_add("j", "daily", principal="carol")
            assert store.get_by_name("j").principal == "carol"
            assert "j" in schedule_list(principal="carol")

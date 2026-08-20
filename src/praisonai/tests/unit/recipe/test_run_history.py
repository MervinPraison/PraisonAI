"""
Unit tests for recipe run history persistence.

Tests:
- run() persists a RecipeResult to history (success and failure)
- PRAISONAI_RECIPE_HISTORY=false disables persistence
- History write failure never fails the run (warning logged)
- list_runs filters by recipe/status and is independent of the registry
- The legacy praison_ai recipe branch imports cleanly
"""

import os
from unittest.mock import patch


def _make_result(status="success", recipe="demo-recipe", run_id="run-test-0001"):
    from praisonai.recipe.models import RecipeResult

    return RecipeResult(
        run_id=run_id,
        recipe=recipe,
        version="1.2.3",
        status=status,
        output={"reply": "hi"} if status == "success" else None,
        error=None if status == "success" else "boom",
        metrics={"duration_sec": 0.01},
        trace={"run_id": run_id, "trace_id": "abc", "session_id": "session-xyz"},
    )


class TestRunPersistsHistory:
    """run() should persist history on every run."""

    def test_success_run_is_recorded(self, tmp_path, monkeypatch):
        from praisonai.recipe import core
        from praisonai.recipe.history import RunHistory

        history = RunHistory(path=tmp_path / "runs")
        result = _make_result(status="success")

        with patch.object(core, "_run_impl", return_value=result), \
             patch("praisonai.recipe.history.get_history", return_value=history):
            out = core.run("demo-recipe", input={"topic": "AI"})

        assert out.status == "success"
        runs = history.list_runs(recipe="demo-recipe")
        assert len(runs) == 1
        assert runs[0]["status"] == "success"
        assert runs[0]["version"] == "1.2.3"
        assert runs[0]["session_id"] == "session-xyz"
        assert runs[0]["run_id"] == "run-test-0001"

    def test_failed_run_is_recorded(self, tmp_path):
        from praisonai.recipe import core
        from praisonai.recipe.history import RunHistory

        history = RunHistory(path=tmp_path / "runs")
        result = _make_result(status="failed", run_id="run-test-fail")

        with patch.object(core, "_run_impl", return_value=result), \
             patch("praisonai.recipe.history.get_history", return_value=history):
            core.run("demo-recipe")

        failed = history.list_runs(status="failed")
        assert len(failed) == 1
        assert failed[0]["run_id"] == "run-test-fail"
        # status filter excludes it
        assert history.list_runs(status="success") == []

    def test_status_filter(self, tmp_path):
        from praisonai.recipe import core
        from praisonai.recipe.history import RunHistory

        history = RunHistory(path=tmp_path / "runs")

        with patch("praisonai.recipe.history.get_history", return_value=history):
            with patch.object(core, "_run_impl", return_value=_make_result("success", run_id="run-ok")):
                core.run("demo-recipe")
            with patch.object(core, "_run_impl", return_value=_make_result("failed", run_id="run-bad")):
                core.run("demo-recipe")

        assert len(history.list_runs()) == 2
        assert len(history.list_runs(status="failed")) == 1
        assert len(history.list_runs(status="success")) == 1


class TestHistoryDisabled:
    """PRAISONAI_RECIPE_HISTORY=false disables persistence."""

    def test_env_flag_disables_persistence(self, tmp_path, monkeypatch):
        from praisonai.recipe import core
        from praisonai.recipe.history import RunHistory

        history = RunHistory(path=tmp_path / "runs")
        monkeypatch.setenv("PRAISONAI_RECIPE_HISTORY", "false")

        with patch.object(core, "_run_impl", return_value=_make_result()), \
             patch("praisonai.recipe.history.get_history", return_value=history):
            core.run("demo-recipe")

        assert history.list_runs() == []

    def test_default_is_enabled(self, monkeypatch):
        from praisonai.recipe import core

        monkeypatch.delenv("PRAISONAI_RECIPE_HISTORY", raising=False)
        assert core._history_enabled() is True


class TestHistoryWriteFailureIsSafe:
    """History write failure must never fail the run."""

    def test_unwritable_store_does_not_raise(self, monkeypatch):
        from praisonai.recipe import core

        result = _make_result()

        def _boom(*args, **kwargs):
            raise OSError("read-only file system")

        with patch.object(core, "_run_impl", return_value=result), \
             patch("praisonai.recipe.history.store_run", side_effect=_boom):
            out = core.run("demo-recipe")

        # Run still succeeds despite history write failure
        assert out.status == "success"


class TestRunsIndependentOfRegistry:
    """recipe runs for a deleted recipe still lists past runs."""

    def test_history_survives_missing_registry(self, tmp_path):
        from praisonai.recipe.history import RunHistory

        history = RunHistory(path=tmp_path / "runs")
        history.store(_make_result(recipe="gone-recipe", run_id="run-gone"))

        # No registry lookup involved; history is self-contained.
        runs = history.list_runs(recipe="gone-recipe")
        assert len(runs) == 1
        assert runs[0]["recipe"] == "gone-recipe"


class TestStreamPersistsHistory:
    """run_stream() should also persist a terminal RecipeResult."""

    def test_stream_success_is_recorded(self, tmp_path):
        from praisonai.recipe import core
        from praisonai.recipe.history import RunHistory

        history = RunHistory(path=tmp_path / "runs")

        class _Cfg:
            name = "stream-recipe"
            version = "2.0.0"
            defaults = {}

        with patch("praisonai.recipe.history.get_history", return_value=history), \
             patch.object(core, "_load_recipe", return_value=_Cfg()), \
             patch.object(core, "_check_dependencies", return_value={"all_satisfied": True}), \
             patch.object(core, "_check_tool_policy", return_value=None), \
             patch.object(core, "_execute_recipe", return_value={"reply": "ok"}):
            events = list(core.run_stream("stream-recipe", input={"topic": "AI"}))

        assert any(e.event_type == "completed" for e in events)
        runs = history.list_runs(recipe="stream-recipe")
        assert len(runs) == 1
        assert runs[0]["status"] == "success"
        assert runs[0]["version"] == "2.0.0"


class TestLegacyImportClean:
    """The legacy praison_ai recipe branch resolves its handler cleanly."""

    def test_wrapper_bridge_resolves_recipe_handler(self):
        # Exercise the exact bridge path the legacy recipe branch uses to
        # resolve the real handler in the wrapper package (see
        # praisonai_code/cli/legacy/praison_ai.py recipe branch).
        from praisonai_code._wrapper_bridge import import_wrapper_module

        recipe_mod = import_wrapper_module("praisonai.cli.features.recipe")
        assert callable(recipe_mod.handle_recipe_command)

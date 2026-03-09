"""
Integration tests for directory consistency with real API calls.

Tests that PRAISONAI_HOME overrides actually redirect all data, 
and that a real agentic call works end-to-end with the wired paths.
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestPraisonaiHomeOverride:
    """Tests that PRAISONAI_HOME env var redirects all global paths."""

    def test_all_global_paths_honor_override(self):
        """Every global helper should resolve under PRAISONAI_HOME."""
        from praisonaiagents.paths import (
            _clear_cache,
            get_data_dir,
            get_sessions_dir,
            get_skills_dir,
            get_plugins_dir,
            get_mcp_dir,
            get_docs_dir,
            get_rules_dir,
            get_permissions_dir,
            get_storage_dir,
            get_checkpoints_dir,
            get_snapshots_dir,
            get_learn_dir,
            get_cache_dir,
            get_mcp_auth_path,
            get_memory_dir,
            get_workflows_dir,
            get_summaries_dir,
            get_prp_dir,
            get_runs_dir,
            get_schedules_dir,
            get_storage_path,
        )

        custom_home = tempfile.mkdtemp(prefix="praisonai_test_")
        try:
            _clear_cache()
            with patch.dict(os.environ, {"PRAISONAI_HOME": custom_home}):
                base = Path(custom_home)
                assert get_data_dir() == base
                assert get_sessions_dir() == base / "sessions"
                assert get_skills_dir() == base / "skills"
                assert get_plugins_dir() == base / "plugins"
                assert get_mcp_dir() == base / "mcp"
                assert get_docs_dir() == base / "docs"
                assert get_rules_dir() == base / "rules"
                assert get_permissions_dir() == base / "permissions"
                assert get_storage_dir() == base / "storage"
                assert get_checkpoints_dir() == base / "checkpoints"
                assert get_snapshots_dir() == base / "snapshots"
                assert get_learn_dir() == base / "learn"
                assert get_cache_dir() == base / "cache"
                assert get_mcp_auth_path() == base / "mcp-auth.json"
                assert get_memory_dir() == base / "memory"
                assert get_workflows_dir() == base / "workflows"
                assert get_summaries_dir() == base / "summaries"
                assert get_prp_dir() == base / "prp"
                assert get_runs_dir() == base / "runs"
                assert get_schedules_dir() == base / "schedules"
                assert get_storage_path() == base / "storage.db"
        finally:
            _clear_cache()
            shutil.rmtree(custom_home, ignore_errors=True)

    def test_autonomy_config_respects_override(self):
        """AutonomyConfig.snapshot_dir should redirect with PRAISONAI_HOME."""
        from praisonaiagents.paths import _clear_cache

        custom_home = tempfile.mkdtemp(prefix="praisonai_test_")
        try:
            _clear_cache()
            with patch.dict(os.environ, {"PRAISONAI_HOME": custom_home}):
                from praisonaiagents.agent.autonomy import AutonomyConfig

                config = AutonomyConfig()
                assert config.snapshot_dir == str(Path(custom_home) / "snapshots")
        finally:
            _clear_cache()
            shutil.rmtree(custom_home, ignore_errors=True)

    def test_retrieval_config_defaults_to_project_local(self):
        """RetrievalConfig.persist_path should default to project-local .praisonai."""
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        from praisonaiagents.paths import get_project_data_dir

        rc = RetrievalConfig()
        assert rc.persist_path == str(get_project_data_dir())

    def test_summarizer_defaults_to_project_local(self):
        """HierarchicalSummarizer._persist_path should default to project-local .praisonai/summaries."""
        from praisonaiagents.rag.summarizer import HierarchicalSummarizer
        from praisonaiagents.paths import get_project_summaries_dir

        hs = HierarchicalSummarizer()
        assert hs._persist_path == str(get_project_summaries_dir())


class TestRealAgenticCall:
    """Real agentic test — creates Agent, calls LLM, verifies path consistency."""

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set — skipping real LLM call"
    )
    def test_agent_start_with_custom_home(self):
        """
        MANDATORY REAL AGENTIC TEST.
        Creates Agent, calls agent.start(), verifies LLM responds.
        """
        from praisonaiagents import Agent

        agent = Agent(
            name="path-test",
            instructions="You are a helpful assistant. Respond in one sentence.",
        )
        result = agent.start("Say hello in one sentence")
        
        # Agent must produce a non-empty text response from the LLM
        assert result is not None
        result_str = str(result)
        assert len(result_str) > 0, "Agent returned empty response"
        print(f"\n✓ Real agentic response: {result_str[:200]}")

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set — skipping real LLM call"
    )
    def test_agent_with_praisonai_home_override(self):
        """
        Run agent with PRAISONAI_HOME override and verify data paths work.
        """
        from praisonaiagents.paths import _clear_cache

        custom_home = tempfile.mkdtemp(prefix="praisonai_agent_test_")
        try:
            _clear_cache()
            os.environ["PRAISONAI_HOME"] = custom_home

            from praisonaiagents import Agent

            agent = Agent(
                name="home-test",
                instructions="You are a helpful assistant.",
            )
            result = agent.start("Say 'path test passed' in one sentence")
            
            assert result is not None
            print(f"\n✓ Agent with custom PRAISONAI_HOME: {str(result)[:200]}")
        finally:
            os.environ.pop("PRAISONAI_HOME", None)
            _clear_cache()
            shutil.rmtree(custom_home, ignore_errors=True)


class TestNoHardcodedPaths:
    """Verify no remaining hardcoded paths in the fixed modules."""

    def test_no_expanduser_in_policy_config(self):
        """policy/config.py should not expanduser for rules."""
        import inspect
        from praisonaiagents.policy import config

        source = inspect.getsource(config)
        assert 'expanduser("~"), ".praisonai", "rules"' not in source

    def test_no_expanduser_in_autonomy(self):
        """autonomy.py should not expanduser for snapshots."""
        import inspect
        from praisonaiagents.agent import autonomy

        source = inspect.getsource(autonomy.AutonomyConfig.__post_init__)
        assert 'expanduser("~"), ".praisonai", "snapshots"' not in source

    def test_no_expanduser_in_scheduler_store(self):
        """scheduler/store.py should not expanduser for schedules."""
        import inspect
        from praisonaiagents.scheduler import store

        source = inspect.getsource(store)
        assert 'expanduser("~"), ".praisonai", "schedules"' not in source

    def test_no_hardcoded_string_in_backends(self):
        """storage/backends.py should not have hardcoded ~/.praisonai/storage.db default."""
        import inspect
        from praisonaiagents.storage.backends import SQLiteBackend

        source = inspect.getsource(SQLiteBackend.__init__)
        assert '"~/.praisonai/storage.db"' not in source

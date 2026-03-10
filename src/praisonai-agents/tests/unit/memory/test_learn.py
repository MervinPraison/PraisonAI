"""Tests for the learn module - continuous learning within memory system."""

import os
import tempfile
import shutil
from pathlib import Path

from praisonaiagents.config.feature_configs import LearnConfig, LearnScope, MemoryConfig
from praisonaiagents.memory.learn.stores import (
    PersonaStore,
    InsightStore,
    ThreadStore,
    PatternStore,
    DecisionStore,
    FeedbackStore,
    ImprovementStore,
    LearnEntry,
)
from praisonaiagents.memory.learn.manager import LearnManager


class TestLearnConfig:
    """Test LearnConfig dataclass."""
    
    def test_default_values(self):
        """Test default LearnConfig values."""
        config = LearnConfig()
        assert config.persona is True
        assert config.insights is True
        assert config.thread is True
        assert config.patterns is False
        assert config.decisions is False
        assert config.feedback is False
        assert config.improvements is False
        assert config.scope == LearnScope.PRIVATE
    
    def test_custom_values(self):
        """Test LearnConfig with custom values."""
        config = LearnConfig(
            persona=False,
            insights=True,
            patterns=True,
            scope=LearnScope.SHARED,
        )
        assert config.persona is False
        assert config.patterns is True
        assert config.scope == LearnScope.SHARED
    
    def test_to_dict(self):
        """Test LearnConfig to_dict method."""
        config = LearnConfig(persona=True, insights=True)
        d = config.to_dict()
        assert d["persona"] is True
        assert d["insights"] is True
        assert d["scope"] == "private"


class TestMemoryConfigWithLearn:
    """Test MemoryConfig with learn field."""
    
    def test_learn_none_by_default(self):
        """Test that learn is None by default."""
        config = MemoryConfig()
        assert config.learn is None
    
    def test_learn_bool_true(self):
        """Test learn=True."""
        config = MemoryConfig(learn=True)
        assert config.learn is True
        d = config.to_dict()
        assert d["learn"] is not None
        assert d["learn"]["persona"] is True
    
    def test_learn_config_instance(self):
        """Test learn=LearnConfig(...)."""
        learn_config = LearnConfig(persona=True, patterns=True)
        config = MemoryConfig(learn=learn_config)
        assert config.learn is learn_config
        d = config.to_dict()
        assert d["learn"]["patterns"] is True


class TestLearnEntry:
    """Test LearnEntry dataclass."""
    
    def test_create_entry(self):
        """Test creating a LearnEntry."""
        entry = LearnEntry(
            id="test_1",
            content="Test content",
            metadata={"key": "value"},
        )
        assert entry.id == "test_1"
        assert entry.content == "Test content"
        assert entry.metadata["key"] == "value"
    
    def test_to_dict(self):
        """Test LearnEntry to_dict."""
        entry = LearnEntry(id="test_1", content="Test")
        d = entry.to_dict()
        assert d["id"] == "test_1"
        assert d["content"] == "Test"
        assert "created_at" in d
    
    def test_from_dict(self):
        """Test LearnEntry from_dict."""
        data = {
            "id": "test_1",
            "content": "Test content",
            "metadata": {"key": "value"},
        }
        entry = LearnEntry.from_dict(data)
        assert entry.id == "test_1"
        assert entry.content == "Test content"


class TestPersonaStore:
    """Test PersonaStore."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.temp_dir, "persona.json")
    
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_preference(self):
        """Test adding a preference."""
        store = PersonaStore(store_path=self.store_path, user_id="test_user")
        entry = store.add_preference("User prefers concise responses", "communication")
        assert entry is not None
        assert "concise" in entry.content
        assert entry.metadata["category"] == "communication"
    
    def test_search(self):
        """Test searching entries."""
        store = PersonaStore(store_path=self.store_path, user_id="test_user")
        store.add_preference("User likes Python", "programming")
        store.add_preference("User prefers dark mode", "ui")
        
        results = store.search("Python")
        assert len(results) == 1
        assert "Python" in results[0].content


class TestInsightStore:
    """Test InsightStore."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.temp_dir, "insights.json")
    
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_insight(self):
        """Test adding an insight."""
        store = InsightStore(store_path=self.store_path, user_id="test_user")
        entry = store.add_insight("User works in data science", "conversation")
        assert entry is not None
        assert "data science" in entry.content


class TestLearnManager:
    """Test LearnManager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_manager_with_defaults(self):
        """Test creating LearnManager with default config."""
        config = LearnConfig()
        manager = LearnManager(config=config, user_id="test_user", store_path=self.temp_dir)
        
        assert "persona" in manager._stores
        assert "insights" in manager._stores
        assert "threads" in manager._stores
    
    def test_capture_persona(self):
        """Test capturing persona."""
        config = LearnConfig(persona=True)
        manager = LearnManager(config=config, user_id="test_user", store_path=self.temp_dir)
        
        entry = manager.capture_persona("User prefers detailed explanations")
        assert entry is not None
        assert "detailed" in entry.content
    
    def test_capture_insight(self):
        """Test capturing insight."""
        config = LearnConfig(insights=True)
        manager = LearnManager(config=config, user_id="test_user", store_path=self.temp_dir)
        
        entry = manager.capture_insight("User is experienced with Python")
        assert entry is not None
    
    def test_get_learning_context(self):
        """Test getting learning context."""
        config = LearnConfig(persona=True, insights=True)
        manager = LearnManager(config=config, user_id="test_user", store_path=self.temp_dir)
        
        manager.capture_persona("User likes concise code")
        manager.capture_insight("User knows Python")
        
        context = manager.get_learning_context()
        assert "persona" in context
        assert "insights" in context
        assert len(context["persona"]) == 1
        assert len(context["insights"]) == 1
    
    def test_search(self):
        """Test searching across stores."""
        config = LearnConfig(persona=True, insights=True)
        manager = LearnManager(config=config, user_id="test_user", store_path=self.temp_dir)
        
        manager.capture_persona("User prefers Python")
        manager.capture_insight("User knows Python well")
        
        results = manager.search("Python")
        assert "persona" in results or "insights" in results
    
    def test_clear_all(self):
        """Test clearing all stores."""
        config = LearnConfig(persona=True, insights=True)
        manager = LearnManager(config=config, user_id="test_user", store_path=self.temp_dir)
        
        manager.capture_persona("Test 1")
        manager.capture_insight("Test 2")
        
        cleared = manager.clear_all()
        assert cleared["persona"] == 1
        assert cleared["insights"] == 1
    
    def test_get_stats(self):
        """Test getting stats."""
        config = LearnConfig(persona=True, insights=True)
        manager = LearnManager(config=config, user_id="test_user", store_path=self.temp_dir)
        
        manager.capture_persona("Test 1")
        manager.capture_persona("Test 2")
        manager.capture_insight("Test 3")
        
        stats = manager.get_stats()
        assert stats["persona"] == 2
        assert stats["insights"] == 1
    
    def test_to_system_prompt_context(self):
        """Test generating system prompt context."""
        config = LearnConfig(persona=True, insights=True)
        manager = LearnManager(config=config, user_id="test_user", store_path=self.temp_dir)
        
        manager.capture_persona("User prefers concise responses")
        manager.capture_insight("User is a Python developer")
        
        context = manager.to_system_prompt_context()
        assert "User Preferences" in context
        assert "concise" in context
        assert "Learned Insights" in context
        assert "Python" in context


class TestBackendWiring:
    """P3-A: Test LearnBackend wiring — SQLite, Redis, FILE."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sqlite_backend_round_trip(self):
        """SQLite backend stores and retrieves learnings."""
        from praisonaiagents.config.feature_configs import LearnBackend
        config = LearnConfig(
            persona=True, insights=True, patterns=False,
            backend=LearnBackend.SQLITE,
        )
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)

        # Store
        entry = manager.capture_persona("Prefers dark mode")
        assert entry is not None
        assert "dark mode" in entry.content

        # Retrieve
        context = manager.get_persona_context()
        assert any("dark mode" in c for c in context)

    def test_file_backend_unchanged(self):
        """FILE backend works as before (default)."""
        config = LearnConfig(persona=True)
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)
        entry = manager.capture_persona("Prefers light mode")
        assert entry is not None

        # Verify JSON file exists
        store_files = list(Path(self.temp_dir).rglob("*.json"))
        assert len(store_files) > 0

    def test_redis_fallback_when_unavailable(self):
        """Redis backend falls back to FILE when Redis not running."""
        import warnings
        from praisonaiagents.config.feature_configs import LearnBackend
        config = LearnConfig(
            persona=True,
            backend=LearnBackend.REDIS,
            db_url="redis://localhost:59999",  # unlikely port
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)

        # Should still work with FILE fallback
        entry = manager.capture_persona("Redis fallback test")
        assert entry is not None

    def test_mongodb_warns_and_falls_back(self):
        """MongoDB warns and falls back to FILE."""
        from praisonaiagents.config.feature_configs import LearnBackend
        config = LearnConfig(
            persona=True,
            backend=LearnBackend.MONGODB,
        )
        # Should not crash, falls back to FILE
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)
        entry = manager.capture_persona("Mongo fallback test")
        assert entry is not None


class TestWasUpdated:
    """P3-B: Test was_updated tracking on BaseStore."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_was_updated_false_initially(self):
        """New store starts with was_updated=False."""
        store = PersonaStore(store_path=os.path.join(self.temp_dir, "persona.json"))
        assert store.was_updated is False

    def test_was_updated_true_after_add(self):
        """was_updated becomes True after add()."""
        store = PersonaStore(store_path=os.path.join(self.temp_dir, "persona.json"))
        store.add("test preference")
        assert store.was_updated is True

    def test_was_updated_true_after_update(self):
        """was_updated becomes True after update()."""
        store = PersonaStore(store_path=os.path.join(self.temp_dir, "persona.json"))
        entry = store.add("preference")
        store.reset_updated()
        store.update(entry.id, "updated preference")
        assert store.was_updated is True

    def test_was_updated_true_after_delete(self):
        """was_updated becomes True after delete()."""
        store = PersonaStore(store_path=os.path.join(self.temp_dir, "persona.json"))
        entry = store.add("to delete")
        store.reset_updated()
        store.delete(entry.id)
        assert store.was_updated is True

    def test_was_updated_true_after_clear(self):
        """was_updated becomes True after clear()."""
        store = PersonaStore(store_path=os.path.join(self.temp_dir, "persona.json"))
        store.add("something")
        store.reset_updated()
        store.clear()
        assert store.was_updated is True

    def test_reset_updated(self):
        """reset_updated() sets flag back to False."""
        store = PersonaStore(store_path=os.path.join(self.temp_dir, "persona.json"))
        store.add("test")
        assert store.was_updated is True
        store.reset_updated()
        assert store.was_updated is False


class TestProposeMode:
    """P3-C: Test PROPOSE mode — extract but don't auto-store."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pending_learnings_initially_empty(self):
        """Pending learnings list starts empty."""
        config = LearnConfig(persona=True, mode="propose")
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)
        assert manager.pending_learnings == []

    def test_add_pending_learning(self):
        """Can add a pending learning manually."""
        config = LearnConfig(persona=True, mode="propose")
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)
        manager.add_pending("User prefers Python", category="persona")
        assert len(manager.pending_learnings) == 1
        assert "Python" in manager.pending_learnings[0].content

    def test_approve_learning_moves_to_store(self):
        """Approving a pending learning moves it to the main store."""
        config = LearnConfig(persona=True, mode="propose")
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)
        manager.add_pending("User likes concise answers", category="persona")
        pending_id = manager.pending_learnings[0].id

        result = manager.approve_learning(pending_id)
        assert result is True
        assert len(manager.pending_learnings) == 0
        # Should now be in persona store
        personas = manager.get_persona_context()
        assert any("concise" in p for p in personas)

    def test_reject_learning_discards(self):
        """Rejecting a pending learning discards it."""
        config = LearnConfig(persona=True, mode="propose")
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)
        manager.add_pending("Bad learning", category="persona")
        pending_id = manager.pending_learnings[0].id

        result = manager.reject_learning(pending_id)
        assert result is True
        assert len(manager.pending_learnings) == 0
        # Should NOT be in any store
        personas = manager.get_persona_context()
        assert not any("Bad learning" in p for p in personas)

    def test_approve_all_learnings(self):
        """Bulk approve all pending learnings."""
        config = LearnConfig(persona=True, insights=True, mode="propose")
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)
        manager.add_pending("Preference A", category="persona")
        manager.add_pending("Insight B", category="insights")
        assert len(manager.pending_learnings) == 2

        count = manager.approve_all_learnings()
        assert count == 2
        assert len(manager.pending_learnings) == 0

    def test_reject_nonexistent_learning(self):
        """Rejecting a nonexistent ID returns False."""
        config = LearnConfig(persona=True, mode="propose")
        manager = LearnManager(config=config, user_id="test", store_path=self.temp_dir)
        result = manager.reject_learning("nonexistent_id")
        assert result is False


class TestNoCortexParam:
    """Test that cortex parameter does not exist."""
    
    def test_agent_has_no_cortex_param(self):
        """Agent.__init__ should not have cortex parameter."""
        import inspect
        from praisonaiagents import Agent
        
        sig = inspect.signature(Agent.__init__)
        param_names = list(sig.parameters.keys())
        
        assert "cortex" not in param_names, "cortex param should be removed from Agent"
    
    def test_no_cortex_module_in_agents(self):
        """praisonaiagents should not have cortex module."""
        import importlib.util
        
        spec = importlib.util.find_spec("praisonaiagents.cortex")
        assert spec is None, "praisonaiagents.cortex module should not exist"

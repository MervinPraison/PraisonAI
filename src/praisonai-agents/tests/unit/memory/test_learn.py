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
        assert config.auto_consolidate is True
        assert config.retention_days is None
    
    def test_custom_values(self):
        """Test LearnConfig with custom values."""
        config = LearnConfig(
            persona=False,
            insights=True,
            patterns=True,
            scope=LearnScope.SHARED,
            retention_days=30,
        )
        assert config.persona is False
        assert config.patterns is True
        assert config.scope == LearnScope.SHARED
        assert config.retention_days == 30
    
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

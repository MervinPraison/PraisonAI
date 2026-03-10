"""
TDD Tests for Learn Module Gap Fixes.

Tests for:
- Gap 1: process_conversation() auto-learning
- Gap 2: LearnProtocol for extensibility
- Gap 3: Learning modes (AGENTIC, PROPOSE)
- Gap 4: Async in learn module
- Gap 5: DB backend support in LearnConfig
"""

# Tests for Learn Module Gap Fixes


class TestLearnProtocols:
    """Test LearnProtocol and related protocols."""

    def test_learn_protocol_exported(self):
        """LearnProtocol should be exported from top-level."""
        from praisonaiagents import LearnProtocol
        assert LearnProtocol is not None

    def test_async_learn_protocol_exported(self):
        """AsyncLearnProtocol should be exported from top-level."""
        from praisonaiagents import AsyncLearnProtocol
        assert AsyncLearnProtocol is not None

    def test_learn_manager_protocol_exported(self):
        """LearnManagerProtocol should be exported from top-level."""
        from praisonaiagents import LearnManagerProtocol
        assert LearnManagerProtocol is not None

    def test_learn_manager_exported(self):
        """LearnManager should be exported from top-level."""
        from praisonaiagents import LearnManager
        assert LearnManager is not None

    def test_custom_store_satisfies_protocol(self):
        """Custom store should satisfy LearnProtocol."""
        from praisonaiagents import LearnProtocol
        
        class CustomLearnStore:
            def add(self, content, metadata=None):
                return {"id": "test", "content": content}
            
            def search(self, query, limit=10):
                return []
            
            def list_all(self, limit=100):
                return []
            
            def get(self, entry_id):
                return None
            
            def update(self, entry_id, content, metadata=None):
                return None
            
            def delete(self, entry_id):
                return True
            
            def clear(self):
                return 0
        
        store = CustomLearnStore()
        assert isinstance(store, LearnProtocol)


class TestLearnModes:
    """Test LearnMode enum and configuration."""

    def test_learn_mode_exported(self):
        """LearnMode should be exported from top-level."""
        from praisonaiagents import LearnMode
        assert LearnMode is not None

    def test_learn_mode_values(self):
        """LearnMode should have DISABLED, AGENTIC, PROPOSE values."""
        from praisonaiagents import LearnMode
        
        assert LearnMode.DISABLED.value == "disabled"
        assert LearnMode.AGENTIC.value == "agentic"
        assert LearnMode.PROPOSE.value == "propose"

    def test_learn_config_has_mode(self):
        """LearnConfig should have mode parameter."""
        from praisonaiagents import LearnConfig, LearnMode
        
        config = LearnConfig(mode=LearnMode.AGENTIC)
        assert config.mode == LearnMode.AGENTIC

    def test_learn_config_mode_default_disabled(self):
        """LearnConfig mode should default to DISABLED."""
        from praisonaiagents import LearnConfig, LearnMode
        
        config = LearnConfig()
        assert config.mode == LearnMode.DISABLED

    def test_learn_config_mode_string(self):
        """LearnConfig should accept mode as string."""
        from praisonaiagents import LearnConfig
        
        config = LearnConfig(mode="agentic")
        assert config.mode == "agentic"


class TestLearnBackend:
    """Test LearnBackend enum and configuration."""

    def test_learn_backend_exported(self):
        """LearnBackend should be exported from top-level."""
        from praisonaiagents import LearnBackend
        assert LearnBackend is not None

    def test_learn_backend_values(self):
        """LearnBackend should have FILE, SQLITE, REDIS, MONGODB values."""
        from praisonaiagents import LearnBackend
        
        assert LearnBackend.FILE.value == "file"
        assert LearnBackend.SQLITE.value == "sqlite"
        assert LearnBackend.REDIS.value == "redis"
        assert LearnBackend.MONGODB.value == "mongodb"

    def test_learn_config_has_backend(self):
        """LearnConfig should have backend parameter."""
        from praisonaiagents import LearnConfig, LearnBackend
        
        config = LearnConfig(backend=LearnBackend.SQLITE)
        assert config.backend == LearnBackend.SQLITE

    def test_learn_config_has_db_url(self):
        """LearnConfig should have db_url parameter."""
        from praisonaiagents import LearnConfig
        
        config = LearnConfig(
            backend="sqlite",
            db_url="sqlite:///learn.db"
        )
        assert config.db_url == "sqlite:///learn.db"

    def test_learn_config_has_llm(self):
        """LearnConfig should have llm parameter for extraction."""
        from praisonaiagents import LearnConfig
        
        config = LearnConfig(llm="gpt-4o")
        assert config.llm == "gpt-4o"


class TestProcessConversation:
    """Test process_conversation() auto-learning method."""

    def test_learn_manager_has_process_conversation(self):
        """LearnManager should have process_conversation method."""
        from praisonaiagents.memory.learn import LearnManager
        
        manager = LearnManager()
        assert hasattr(manager, 'process_conversation')
        assert callable(manager.process_conversation)

    def test_learn_manager_has_aprocess_conversation(self):
        """LearnManager should have async aprocess_conversation method."""
        from praisonaiagents.memory.learn import LearnManager
        
        manager = LearnManager()
        assert hasattr(manager, 'aprocess_conversation')
        assert callable(manager.aprocess_conversation)

    def test_process_conversation_empty_messages(self):
        """process_conversation should handle empty messages."""
        from praisonaiagents.memory.learn import LearnManager
        
        manager = LearnManager()
        result = manager.process_conversation([])
        
        assert result == {"persona": [], "insights": [], "patterns": [], "stored": {}}

    def test_process_conversation_signature(self):
        """process_conversation should have correct signature."""
        from praisonaiagents.memory.learn import LearnManager
        import inspect
        
        manager = LearnManager()
        sig = inspect.signature(manager.process_conversation)
        params = list(sig.parameters.keys())
        
        assert "messages" in params
        assert "llm" in params


class TestLearnConfigToDict:
    """Test LearnConfig.to_dict() includes new fields."""

    def test_to_dict_includes_mode(self):
        """to_dict should include mode."""
        from praisonaiagents import LearnConfig, LearnMode
        
        config = LearnConfig(mode=LearnMode.AGENTIC)
        d = config.to_dict()
        
        assert "mode" in d
        assert d["mode"] == "agentic"

    def test_to_dict_includes_backend(self):
        """to_dict should include backend."""
        from praisonaiagents import LearnConfig, LearnBackend
        
        config = LearnConfig(backend=LearnBackend.SQLITE)
        d = config.to_dict()
        
        assert "backend" in d
        assert d["backend"] == "sqlite"

    def test_to_dict_includes_db_url(self):
        """to_dict should include db_url."""
        from praisonaiagents import LearnConfig
        
        config = LearnConfig(db_url="sqlite:///test.db")
        d = config.to_dict()
        
        assert "db_url" in d
        assert d["db_url"] == "sqlite:///test.db"

    def test_to_dict_includes_llm(self):
        """to_dict should include llm."""
        from praisonaiagents import LearnConfig
        
        config = LearnConfig(llm="gpt-4o")
        d = config.to_dict()
        
        assert "llm" in d
        assert d["llm"] == "gpt-4o"


class TestAgentWithLearnMode:
    """Test Agent with learn mode configuration."""

    def test_agent_accepts_learn_config_with_mode(self):
        """Agent should accept LearnConfig with mode."""
        from praisonaiagents import Agent, LearnConfig, LearnMode
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            learn=LearnConfig(
                mode=LearnMode.AGENTIC,
                persona=True,
                insights=True,
            ),
        )
        
        assert agent._learn_config is not None
        assert agent._learn_config.mode == LearnMode.AGENTIC

    def test_agent_accepts_learn_config_with_backend(self):
        """Agent should accept LearnConfig with backend."""
        from praisonaiagents import Agent, LearnConfig, LearnBackend
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            learn=LearnConfig(
                backend=LearnBackend.SQLITE,
                db_url="sqlite:///test.db",
            ),
        )
        
        assert agent._learn_config is not None
        assert agent._learn_config.backend == LearnBackend.SQLITE

    def test_agent_has_process_auto_learning_method(self):
        """Agent should have _process_auto_learning method."""
        from praisonaiagents import Agent
        
        agent = Agent(name="test", instructions="Test agent")
        assert hasattr(agent, '_process_auto_learning')
        assert callable(agent._process_auto_learning)


class TestCustomStores:
    """Test custom_stores support in LearnManager."""

    def test_learn_manager_accepts_custom_stores(self):
        """LearnManager should accept custom_stores parameter."""
        from praisonaiagents import LearnManager, LearnConfig
        
        class MyCustomStore:
            def __init__(self):
                self.data = []
            def add(self, content, metadata=None):
                self.data.append(content)
                return {"id": "1", "content": content}
            def search(self, query, limit=10):
                return []
            def list_all(self, limit=100):
                return self.data
            def get(self, entry_id):
                return None
            def update(self, entry_id, content, metadata=None):
                return None
            def delete(self, entry_id):
                return True
            def clear(self):
                return 0
        
        custom_store = MyCustomStore()
        manager = LearnManager(
            config=LearnConfig(persona=True),
            custom_stores={"domain": custom_store}
        )
        
        assert "domain" in manager._stores
        assert manager._stores["domain"] is custom_store

    def test_custom_stores_can_override_builtin(self):
        """Custom stores can override built-in stores."""
        from praisonaiagents import LearnManager, LearnConfig
        
        class MyPersonaStore:
            def add(self, content, metadata=None):
                return {"id": "custom", "content": content}
            def search(self, query, limit=10):
                return []
            def list_all(self, limit=100):
                return []
            def get(self, entry_id):
                return None
            def update(self, entry_id, content, metadata=None):
                return None
            def delete(self, entry_id):
                return True
            def clear(self):
                return 0
        
        custom_persona = MyPersonaStore()
        manager = LearnManager(
            config=LearnConfig(persona=True),
            custom_stores={"persona": custom_persona}
        )
        
        # Custom stores should override built-in stores
        assert "persona" in manager._stores
        assert manager._stores["persona"] is custom_persona

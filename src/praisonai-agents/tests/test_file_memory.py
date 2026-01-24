"""
Tests for FileMemory - Zero-dependency file-based memory system.
"""

import tempfile
import pytest


class TestFileMemoryBasics:
    """Tests for FileMemory basic functionality."""
    
    def test_import(self):
        """Test that FileMemory can be imported."""
        from praisonaiagents.memory.file_memory import FileMemory
        assert FileMemory is not None
    
    def test_init_default(self):
        """Test default initialization."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            assert memory.user_id == "default"
            assert memory.user_path.exists()
    
    def test_init_with_user_id(self):
        """Test initialization with custom user_id."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir, user_id="test_user")
            assert memory.user_id == "test_user"
            assert "test_user" in str(memory.user_path)
    
    def test_config_persistence(self):
        """Test that config is saved and loaded."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create with custom config
            memory1 = FileMemory(
                base_path=tmpdir,
                config={"short_term_limit": 50}
            )
            assert memory1.config["short_term_limit"] == 50
            
            # Create new instance - should load saved config
            memory2 = FileMemory(base_path=tmpdir)
            assert memory2.config["short_term_limit"] == 50


class TestShortTermMemory:
    """Tests for short-term memory functionality."""
    
    def test_add_short_term(self):
        """Test adding short-term memory."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            mem_id = memory.add_short_term("User prefers dark mode")
            assert mem_id is not None
            assert len(memory._short_term) == 1
    
    def test_get_short_term(self):
        """Test retrieving short-term memories."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_short_term("Memory 1")
            memory.add_short_term("Memory 2")
            memory.add_short_term("Memory 3")
            
            # Get all
            items = memory.get_short_term()
            assert len(items) == 3
            # Most recent first
            assert items[0].content == "Memory 3"
            
            # Get limited
            items = memory.get_short_term(limit=2)
            assert len(items) == 2
    
    def test_short_term_rolling_buffer(self):
        """Test that short-term memory enforces limit."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(
                base_path=tmpdir,
                config={"short_term_limit": 5, "auto_promote": False}
            )
            
            # Add more than limit
            for i in range(10):
                memory.add_short_term(f"Memory {i}")
            
            # Should only have last 5
            assert len(memory._short_term) == 5
            items = memory.get_short_term()
            assert items[0].content == "Memory 9"
    
    def test_short_term_persistence(self):
        """Test that short-term memory persists to file."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Add memory
            memory1 = FileMemory(base_path=tmpdir)
            memory1.add_short_term("Persistent memory")
            
            # Create new instance - should load from file
            memory2 = FileMemory(base_path=tmpdir)
            items = memory2.get_short_term()
            assert len(items) == 1
            assert items[0].content == "Persistent memory"


class TestLongTermMemory:
    """Tests for long-term memory functionality."""
    
    def test_add_long_term(self):
        """Test adding long-term memory."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            mem_id = memory.add_long_term("User's name is John", importance=0.9)
            assert mem_id is not None
            assert len(memory._long_term) == 1
    
    def test_get_long_term_sorted_by_importance(self):
        """Test that long-term memories are sorted by importance."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_long_term("Low importance", importance=0.3)
            memory.add_long_term("High importance", importance=0.9)
            memory.add_long_term("Medium importance", importance=0.6)
            
            items = memory.get_long_term()
            assert items[0].content == "High importance"
            assert items[1].content == "Medium importance"
            assert items[2].content == "Low importance"
    
    def test_auto_promote_to_long_term(self):
        """Test auto-promotion of high-importance short-term to long-term."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(
                base_path=tmpdir,
                config={
                    "short_term_limit": 3,
                    "auto_promote": True,
                    "importance_threshold": 0.7
                }
            )
            
            # Add high importance items
            memory.add_short_term("Important 1", importance=0.8)
            memory.add_short_term("Important 2", importance=0.9)
            memory.add_short_term("Low importance", importance=0.3)
            
            # Trigger promotion by exceeding limit
            memory.add_short_term("New item", importance=0.5)
            
            # High importance items should be in long-term
            long_term = memory.get_long_term()
            assert len(long_term) >= 2


class TestEntityMemory:
    """Tests for entity memory functionality."""
    
    def test_add_entity(self):
        """Test adding an entity."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            entity_id = memory.add_entity(
                name="John",
                entity_type="person",
                attributes={"role": "developer", "company": "Acme"}
            )
            
            assert entity_id is not None
            assert len(memory._entities) == 1
    
    def test_get_entity(self):
        """Test retrieving an entity."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_entity("John", "person", {"role": "developer"})
            
            entity = memory.get_entity("John")
            assert entity is not None
            assert entity.name == "John"
            assert entity.entity_type == "person"
            assert entity.attributes["role"] == "developer"
    
    def test_update_entity(self):
        """Test updating an existing entity."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_entity("John", "person", {"role": "developer"})
            memory.add_entity("John", "person", {"company": "Acme"})
            
            entity = memory.get_entity("John")
            assert entity.attributes["role"] == "developer"
            assert entity.attributes["company"] == "Acme"
    
    def test_get_all_entities(self):
        """Test getting all entities."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_entity("John", "person", {})
            memory.add_entity("Acme", "organization", {})
            memory.add_entity("New York", "place", {})
            
            # All entities
            all_entities = memory.get_all_entities()
            assert len(all_entities) == 3
            
            # Filter by type
            people = memory.get_all_entities(entity_type="person")
            assert len(people) == 1
            assert people[0].name == "John"


class TestEpisodicMemory:
    """Tests for episodic memory functionality."""
    
    def test_add_episodic(self):
        """Test adding episodic memory."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            mem_id = memory.add_episodic("Had a meeting about project X")
            assert mem_id is not None
    
    def test_get_episodic_by_date(self):
        """Test retrieving episodic memories by date."""
        from praisonaiagents.memory.file_memory import FileMemory
        from datetime import datetime
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            today = datetime.now().strftime("%Y-%m-%d")
            memory.add_episodic("Today's event", date=today)
            
            episodes = memory.get_episodic(date=today)
            assert len(episodes) == 1
            assert episodes[0].content == "Today's event"
    
    def test_get_recent_episodic(self):
        """Test retrieving recent episodic memories."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_episodic("Event 1")
            memory.add_episodic("Event 2")
            
            episodes = memory.get_episodic(days_back=7)
            assert len(episodes) == 2


class TestSearch:
    """Tests for search functionality."""
    
    def test_search_short_term(self):
        """Test searching short-term memory."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_short_term("User prefers dark mode")
            memory.add_short_term("User likes Python programming")
            memory.add_short_term("Weather is sunny today")
            
            results = memory.search("user", memory_types=["short_term"])
            assert len(results) == 2
    
    def test_search_all_types(self):
        """Test searching across all memory types."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_short_term("John mentioned Python")
            memory.add_long_term("John is a developer")
            memory.add_entity("John", "person", {"skill": "Python"})
            
            results = memory.search("John")
            assert len(results) >= 3
    
    def test_search_relevance_scoring(self):
        """Test that search results are scored by relevance."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_short_term("Python is great", importance=0.5)
            memory.add_short_term("I love Python programming", importance=0.8)
            
            results = memory.search("Python")
            assert len(results) == 2
            # Higher importance should score higher
            assert results[0]["score"] >= results[1]["score"]


class TestContext:
    """Tests for context building."""
    
    def test_get_context_empty(self):
        """Test getting context with no memories."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            context = memory.get_context()
            assert context == ""
    
    def test_get_context_with_memories(self):
        """Test getting context with memories."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_long_term("User's name is John", importance=0.9)
            memory.add_short_term("User asked about Python")
            memory.add_entity("John", "person", {"role": "developer"})
            
            context = memory.get_context()
            assert "John" in context
            assert "Important Facts" in context or "Known Entities" in context
    
    def test_get_context_with_query(self):
        """Test getting focused context with query."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_long_term("User's name is John")
            memory.add_long_term("User likes Python")
            memory.add_long_term("Weather is sunny")
            
            context = memory.get_context(query="John")
            assert "John" in context


class TestUtilities:
    """Tests for utility methods."""
    
    def test_clear_short_term(self):
        """Test clearing short-term memory."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_short_term("Memory 1")
            memory.add_short_term("Memory 2")
            
            memory.clear_short_term()
            
            assert len(memory._short_term) == 0
    
    def test_clear_all(self):
        """Test clearing all memory."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir)
            
            memory.add_short_term("Short term")
            memory.add_long_term("Long term")
            memory.add_entity("John", "person", {})
            memory.add_episodic("Episode")
            
            memory.clear_all()
            
            assert len(memory._short_term) == 0
            assert len(memory._long_term) == 0
            assert len(memory._entities) == 0
    
    def test_get_stats(self):
        """Test getting memory statistics."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(base_path=tmpdir, user_id="test_user")
            
            memory.add_short_term("Short term")
            memory.add_long_term("Long term")
            memory.add_entity("John", "person", {})
            
            stats = memory.get_stats()
            
            assert stats["user_id"] == "test_user"
            assert stats["short_term_count"] == 1
            assert stats["long_term_count"] == 1
            assert stats["entity_count"] == 1
    
    def test_export_import(self):
        """Test exporting and importing memory data."""
        from praisonaiagents.memory.file_memory import FileMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and populate memory
            memory1 = FileMemory(base_path=tmpdir, user_id="user1")
            memory1.add_short_term("Short term memory")
            memory1.add_long_term("Long term memory")
            memory1.add_entity("John", "person", {"role": "dev"})
            
            # Export
            exported = memory1.export()
            
            # Import to new memory
            memory2 = FileMemory(base_path=tmpdir, user_id="user2")
            memory2.import_data(exported)
            
            assert len(memory2._short_term) == 1
            assert len(memory2._long_term) == 1
            assert len(memory2._entities) == 1


class TestAgentIntegration:
    """Tests for Agent class integration with FileMemory."""
    
    def test_agent_memory_true(self):
        """Test Agent with memory=True uses FileMemory."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test Agent",
            memory=True
        )
        
        assert agent.memory is True
        assert agent._memory_instance is not None
    
    def test_agent_memory_false(self):
        """Test Agent with memory=False has no memory."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test Agent",
            memory=False
        )
        
        assert agent._memory_instance is None
    
    def test_agent_memory_file(self):
        """Test Agent with memory='file' uses FileMemory."""
        from praisonaiagents import Agent
        from praisonaiagents.memory.file_memory import FileMemory
        
        agent = Agent(
            name="Test Agent",
            memory="file"
        )
        
        assert isinstance(agent._memory_instance, FileMemory)
    
    def test_agent_store_memory(self):
        """Test Agent store_memory method."""
        import uuid
        from praisonaiagents import Agent
        
        # Use unique user_id to avoid stale data from previous test runs
        unique_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        
        agent = Agent(
            name="Test Agent",
            memory={"user_id": unique_user_id}
        )
        
        agent.store_memory("User prefers dark mode", memory_type="short_term")
        
        items = agent._memory_instance.get_short_term()
        assert len(items) == 1, f"Expected 1 item, got {len(items)} items"
        assert items[0].content == "User prefers dark mode"
    
    def test_agent_get_memory_context(self):
        """Test Agent get_memory_context method."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test Agent",
            memory=True
        )
        
        agent.store_memory("User's name is John", memory_type="long_term", importance=0.9)
        
        context = agent.get_memory_context()
        assert "John" in context


class TestCreateMemoryFunction:
    """Tests for create_memory convenience function."""
    
    def test_create_memory(self):
        """Test create_memory function."""
        from praisonaiagents.memory import create_memory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = create_memory(user_id="test", base_path=tmpdir)
            
            assert memory.user_id == "test"
            memory.add_short_term("Test memory")
            assert len(memory._short_term) == 1


class TestMemoryIntegrationWithOpenAI:
    """Integration tests for memory with OpenAI API (requires OPENAI_API_KEY)."""
    
    def test_memory_injection_into_system_prompt(self):
        """Test that memory context is injected into system prompt and agent recalls it."""
        import os
        import shutil
        
        # Skip if no API key
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        from praisonaiagents import Agent
        
        test_user_id = "integration_test_user"
        
        try:
            # Create agent with memory enabled
            from praisonaiagents.config import MemoryConfig
            agent = Agent(
                name="Memory Test Agent",
                role="Assistant",
                goal="Help users and remember their information",
                backstory="You are a helpful assistant with memory capabilities.",
                # Uses default model (gpt-4o-mini via OPENAI_MODEL_NAME or fallback)
                memory=MemoryConfig(user_id=test_user_id),
                output="silent"
            )
            
            # Store memories BEFORE the chat
            agent.store_memory("User's favorite color is blue", memory_type="short_term")
            agent.store_memory("User's name is Alice", memory_type="long_term", importance=0.95)
            agent.store_memory("User works as a software engineer", memory_type="long_term", importance=0.9)
            
            # Add entity
            agent._memory_instance.add_entity("Alice", "person", {
                "occupation": "software engineer",
                "favorite_color": "blue"
            })
            
            # Ask agent about the user - should recall from memory
            result = agent.start("What is my name and what do I do for work? Answer in one sentence.")
            
            # Verify the response contains the remembered information
            assert result is not None
            result_lower = result.lower()
            assert "alice" in result_lower, f"Expected 'alice' in response: {result}"
            assert "software" in result_lower or "engineer" in result_lower, f"Expected occupation in response: {result}"
            
            print(f"✅ Memory injection test passed! Response: {result}")
            
        finally:
            # Cleanup
            memory_path = f".praison/memory/{test_user_id}"
            if os.path.exists(memory_path):
                shutil.rmtree(memory_path)
    
    def test_memory_persistence_across_agent_instances(self):
        """Test that memory persists when creating new agent instances."""
        import os
        import shutil
        
        # Skip if no API key
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        from praisonaiagents import Agent
        
        test_user_id = "persistence_test_user"
        
        try:
            from praisonaiagents.config import MemoryConfig
            # First agent - store memories
            agent1 = Agent(
                name="Agent 1",
                # Uses default model (gpt-4o-mini via OPENAI_MODEL_NAME or fallback)
                memory=MemoryConfig(user_id=test_user_id),
                output="silent"
            )
            
            agent1.store_memory("User prefers Python over JavaScript", memory_type="long_term", importance=0.9)
            agent1.store_memory("User is learning machine learning", memory_type="short_term")
            
            # Verify memories stored
            stats1 = agent1._memory_instance.get_stats()
            assert stats1["long_term_count"] == 1
            assert stats1["short_term_count"] == 1
            
            # Second agent - same user_id, should load memories
            agent2 = Agent(
                name="Agent 2",
                # Uses default model (gpt-4o-mini via OPENAI_MODEL_NAME or fallback)
                memory=MemoryConfig(user_id=test_user_id),
                output="silent"
            )
            
            # Verify memories loaded
            stats2 = agent2._memory_instance.get_stats()
            assert stats2["long_term_count"] == 1, f"Expected 1 long-term memory, got {stats2}"
            assert stats2["short_term_count"] == 1, f"Expected 1 short-term memory, got {stats2}"
            
            # Ask about preferences - should recall from loaded memory
            result = agent2.start("What programming language do I prefer? Answer in one word.")
            
            assert result is not None
            assert "python" in result.lower(), f"Expected 'python' in response: {result}"
            
            print(f"✅ Memory persistence test passed! Response: {result}")
            
        finally:
            # Cleanup
            memory_path = f".praison/memory/{test_user_id}"
            if os.path.exists(memory_path):
                shutil.rmtree(memory_path)


class TestMultiAgentMemorySharing:
    """Tests for memory sharing between multiple agents."""
    
    def test_agents_share_memory_with_same_user_id(self):
        """Test that agents with same user_id share memory."""
        import uuid
        from praisonaiagents import Agent
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use unique user_id to avoid stale data from previous test runs
            user_id = f"shared_user_{uuid.uuid4().hex[:8]}"
            base_path = f"{tmpdir}/memory"
            
            from praisonaiagents.config import MemoryConfig
            # Agent 1 stores memories
            agent1 = Agent(
                name="Agent1",
                memory=MemoryConfig(backend="file", user_id=user_id),
                output="silent"
            )
            
            agent1.store_memory("User prefers Python", memory_type="short_term")
            agent1.store_memory("User name is Alice", memory_type="long_term", importance=0.9)
            agent1._memory_instance.add_entity("Alice", "person", {"role": "developer"})
            
            # Verify Agent1 stored memories
            assert len(agent1._memory_instance.get_short_term()) == 1, f"Expected 1 short_term, got {len(agent1._memory_instance.get_short_term())}"
            assert len(agent1._memory_instance.get_long_term()) == 1, f"Expected 1 long_term, got {len(agent1._memory_instance.get_long_term())}"
            assert len(agent1._memory_instance.get_all_entities()) == 1, f"Expected 1 entity, got {len(agent1._memory_instance.get_all_entities())}"
            
            # Agent 2 with same user_id should load memories
            agent2 = Agent(
                name="Agent2",
                memory=MemoryConfig(backend="file", user_id=user_id),
                output="silent"
            )
            
            # Verify Agent2 loaded the same memories
            assert len(agent2._memory_instance.get_short_term()) == 1
            assert len(agent2._memory_instance.get_long_term()) == 1
            assert len(agent2._memory_instance.get_all_entities()) == 1
            
            # Verify content matches
            assert agent2._memory_instance.get_short_term()[0].content == "User prefers Python"
            assert agent2._memory_instance.get_long_term()[0].content == "User name is Alice"
            assert agent2._memory_instance.get_entity("Alice") is not None
    
    def test_agents_isolated_with_different_user_id(self):
        """Test that agents with different user_id have isolated memory."""
        from praisonaiagents import Agent
        
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = f"{tmpdir}/memory"
            
            from praisonaiagents.config import MemoryConfig
            # Agent 1 with user_id "user1"
            agent1 = Agent(
                name="Agent1",
                memory=MemoryConfig(backend="file", user_id="user1"),
                output="silent"
            )
            agent1.store_memory("User1 data", memory_type="long_term", importance=0.9)
            
            # Agent 2 with different user_id "user2"
            agent2 = Agent(
                name="Agent2",
                memory=MemoryConfig(backend="file", user_id="user2"),
                output="silent"
            )
            
            # Agent2 should have no memories (different user_id)
            assert len(agent2._memory_instance.get_long_term()) == 0
            assert len(agent2._memory_instance.get_short_term()) == 0
            
            # Verify paths are different
            assert agent1._memory_instance.user_path != agent2._memory_instance.user_path
    
    def test_memory_context_injected_into_system_prompt(self):
        """Test that memory context is injected into system prompt."""
        from praisonaiagents import Agent
        
        with tempfile.TemporaryDirectory() as tmpdir:
            from praisonaiagents.config import MemoryConfig
            agent = Agent(
                name="TestAgent",
                memory=MemoryConfig(backend="file", user_id="test"),
                output="silent"
            )
            
            # Store memories
            agent.store_memory("User prefers dark mode", memory_type="short_term")
            agent.store_memory("User name is John", memory_type="long_term", importance=0.9)
            
            # Get memory context
            context = agent.get_memory_context()
            
            # Verify context contains the memories
            assert "John" in context
            assert "dark mode" in context
            assert "Important Facts" in context or "Recent Context" in context
    
    def test_memory_display_info(self):
        """Test that memory display info shows correct counts."""
        from praisonaiagents import Agent
        from praisonaiagents.config import MemoryConfig
        
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = Agent(
                name="TestAgent",
                memory=MemoryConfig(backend="file", user_id="test"),
                output="verbose"
            )
            
            # Store various memories
            agent.store_memory("Short term 1", memory_type="short_term")
            agent.store_memory("Short term 2", memory_type="short_term")
            agent.store_memory("Long term 1", memory_type="long_term", importance=0.9)
            agent._memory_instance.add_entity("Entity1", "person", {})
            
            # Get stats
            stats = agent._memory_instance.get_stats()
            
            # Verify counts are as expected (at least the ones we added)
            assert stats["short_term_count"] >= 2
            assert stats["long_term_count"] >= 1
            assert stats["entity_count"] >= 1


class TestMultiAgentMemoryIntegration:
    """Integration tests for multi-agent memory with OpenAI API."""
    
    def test_multi_agent_memory_sharing_with_llm(self):
        """Test that multiple agents share memory and use it in LLM calls."""
        import os
        import shutil
        
        # Skip if no API key
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        from praisonaiagents import Agent
        
        test_user_id = "multi_agent_llm_test"
        
        try:
            from praisonaiagents.config import MemoryConfig
            # Agent 1 stores memories
            agent1 = Agent(
                name="Agent1",
                memory=MemoryConfig(user_id=test_user_id),
                output="silent"
            )
            
            agent1.store_memory("User's favorite color is blue", memory_type="long_term", importance=0.9)
            agent1.store_memory("User works as a teacher", memory_type="long_term", importance=0.85)
            
            # Agent 2 with same user_id should recall memories
            agent2 = Agent(
                name="Agent2",
                memory=MemoryConfig(user_id=test_user_id),
                output="silent"
            )
            
            # Verify memories loaded
            stats = agent2._memory_instance.get_stats()
            assert stats["long_term_count"] == 2
            
            # Ask Agent2 about the user - should use loaded memories
            result = agent2.start("What is my favorite color? Answer in one word.")
            
            assert result is not None
            assert "blue" in result.lower(), f"Expected 'blue' in response: {result}"
            
            print(f"✅ Multi-agent memory sharing test passed! Response: {result}")
            
        finally:
            memory_path = f".praison/memory/{test_user_id}"
            if os.path.exists(memory_path):
                shutil.rmtree(memory_path)

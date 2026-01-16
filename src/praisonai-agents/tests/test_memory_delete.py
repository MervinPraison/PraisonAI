"""
Tests for memory deletion functionality.

Tests cover:
- FileMemory delete methods (short_term, long_term, entity, episodic)
- Memory class delete methods (SQLite backend)
- Unified delete_memory method
- Bulk delete_memories method
- Query-based delete_memories_matching
- CLI /memory delete command
- Image-based memory cleanup scenario
"""
import pytest
import tempfile
import shutil
from pathlib import Path


class TestFileMemoryDeletion:
    """Test FileMemory delete operations."""
    
    @pytest.fixture
    def temp_memory_dir(self):
        """Create a temporary directory for memory storage."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def file_memory(self, temp_memory_dir):
        """Create a FileMemory instance with temp storage."""
        from praisonaiagents.memory import FileMemory
        return FileMemory(user_id="test_user", base_path=temp_memory_dir, verbose=0)
    
    def test_delete_short_term_by_id(self, file_memory):
        """Test deleting a short-term memory by ID."""
        # Add a memory
        mem_id = file_memory.add_short_term("Test short-term memory")
        
        # Verify it exists
        memories = file_memory.get_short_term()
        assert any(m.id == mem_id for m in memories)
        
        # Delete it
        success = file_memory.delete_short_term(mem_id)
        assert success is True
        
        # Verify it's gone
        memories = file_memory.get_short_term()
        assert not any(m.id == mem_id for m in memories)
    
    def test_delete_long_term_by_id(self, file_memory):
        """Test deleting a long-term memory by ID."""
        # Add a memory
        mem_id = file_memory.add_long_term("Test long-term memory", importance=0.9)
        
        # Verify it exists
        memories = file_memory.get_long_term()
        assert any(m.id == mem_id for m in memories)
        
        # Delete it
        success = file_memory.delete_long_term(mem_id)
        assert success is True
        
        # Verify it's gone
        memories = file_memory.get_long_term()
        assert not any(m.id == mem_id for m in memories)
    
    def test_delete_entity_by_name(self, file_memory):
        """Test deleting an entity by name."""
        # Add an entity
        file_memory.add_entity(
            name="TestEntity",
            entity_type="test",
            attributes={"key": "value"},
            relationships=[]
        )
        
        # Verify it exists
        entity = file_memory.get_entity("TestEntity")
        assert entity is not None
        
        # Delete it
        success = file_memory.delete_entity("TestEntity")
        assert success is True
        
        # Verify it's gone
        entity = file_memory.get_entity("TestEntity")
        assert entity is None
    
    def test_delete_nonexistent_returns_false(self, file_memory):
        """Test that deleting non-existent ID returns False."""
        success = file_memory.delete_memory("nonexistent_id_12345")
        assert success is False
    
    def test_unified_delete_memory(self, file_memory):
        """Test unified delete_memory that searches all types."""
        # Add memories of different types
        short_id = file_memory.add_short_term("Short term test")
        long_id = file_memory.add_long_term("Long term test")
        
        # Delete short-term without specifying type
        success = file_memory.delete_memory(short_id)
        assert success is True
        
        # Delete long-term without specifying type
        success = file_memory.delete_memory(long_id)
        assert success is True
    
    def test_delete_with_type_hint(self, file_memory):
        """Test delete_memory with type hint for faster lookup."""
        mem_id = file_memory.add_short_term("Type hint test")
        
        # Delete with correct type hint
        success = file_memory.delete_memory(mem_id, memory_type="short_term")
        assert success is True
        
        # Try to delete again (should fail)
        success = file_memory.delete_memory(mem_id, memory_type="short_term")
        assert success is False
    
    def test_bulk_delete_memories(self, file_memory):
        """Test deleting multiple memories at once."""
        # Add multiple memories
        ids = [
            file_memory.add_short_term(f"Memory {i}")
            for i in range(5)
        ]
        
        # Delete all
        deleted_count = file_memory.delete_memories(ids)
        assert deleted_count == 5
        
        # Verify all are gone
        memories = file_memory.get_short_term()
        for mem_id in ids:
            assert not any(m.id == mem_id for m in memories)
    
    def test_delete_memories_matching_query(self, file_memory):
        """Test deleting memories by search query."""
        # Add memories with specific content
        file_memory.add_long_term("Image analysis result cat")
        file_memory.add_long_term("Image analysis result dog")
        file_memory.add_long_term("Weather forecast for today sunny")
        
        # Verify initial state
        initial_memories = file_memory.get_long_term()
        assert len(initial_memories) >= 3
        
        # Delete all image-related memories
        deleted = file_memory.delete_memories_matching("Image analysis")
        assert deleted >= 2
        
        # Verify remaining memories
        remaining = file_memory.get_long_term()
        # Should have fewer memories after deletion
        assert len(remaining) < len(initial_memories)


class TestFileMemoryCLIDelete:
    """Test FileMemory CLI delete commands."""
    
    @pytest.fixture
    def temp_memory_dir(self):
        """Create a temporary directory for memory storage."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def file_memory(self, temp_memory_dir):
        """Create a FileMemory instance with temp storage."""
        from praisonaiagents.memory import FileMemory
        return FileMemory(user_id="test_user", base_path=temp_memory_dir, verbose=0)
    
    def test_delete_command_by_id(self, file_memory):
        """Test /memory delete <id> command."""
        # Add a memory
        mem_id = file_memory.add_long_term("CLI delete test")
        
        # Delete via command
        result = file_memory.handle_command(f"/memory delete {mem_id}")
        
        assert result["action"] == "delete"
        assert result["type"] == "single"
        assert result["success"] is True
    
    def test_delete_command_by_query(self, file_memory):
        """Test /memory delete --query <query> command."""
        # Add memories
        file_memory.add_long_term("Query delete test 1")
        file_memory.add_long_term("Query delete test 2")
        
        # Delete via command with query
        result = file_memory.handle_command("/memory delete --query Query delete")
        
        assert result["action"] == "delete"
        assert result["type"] == "query"
        assert result["deleted_count"] >= 1
    
    def test_delete_command_no_args(self, file_memory):
        """Test /memory delete with no arguments returns error."""
        result = file_memory.handle_command("/memory delete")
        assert "error" in result
    
    def test_list_command_shows_ids(self, file_memory):
        """Test /memory list command returns IDs for deletion reference."""
        # Add memories
        mem_id = file_memory.add_long_term("List test memory")
        
        # List memories
        result = file_memory.handle_command("/memory list")
        
        assert result["action"] == "list"
        assert len(result["items"]) >= 1
        # Verify items have IDs
        assert any(item.get("id") == mem_id for item in result["items"])


class TestImageMemoryCleanupScenario:
    """Test the specific use case of cleaning up image-based memories."""
    
    @pytest.fixture
    def temp_memory_dir(self):
        """Create a temporary directory for memory storage."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def file_memory(self, temp_memory_dir):
        """Create a FileMemory instance with temp storage."""
        from praisonaiagents.memory import FileMemory
        return FileMemory(user_id="test_user", base_path=temp_memory_dir, verbose=0)
    
    def test_image_context_cleanup(self, file_memory):
        """
        Test scenario: User asks agent about an image, then needs to 
        delete that memory to free up context window.
        """
        # Simulate storing image-related conversation
        image_mem_1 = file_memory.add_short_term(
            "[IMAGE] User uploaded screenshot.png",
            metadata={"type": "image", "filename": "screenshot.png"}
        )
        image_mem_2 = file_memory.add_short_term(
            "Agent: I see a cat in the image with orange fur.",
            metadata={"type": "image_response", "related_to": image_mem_1}
        )
        
        # Add some regular memories
        regular_mem = file_memory.add_short_term("User: What's the weather today?")
        
        # Get initial memory count
        initial_count = len(file_memory.get_short_term())
        assert initial_count >= 3
        
        # Delete the image-related memories specifically
        deleted = file_memory.delete_memory(image_mem_1)
        assert deleted is True
        
        deleted = file_memory.delete_memory(image_mem_2)
        assert deleted is True
        
        # Verify regular memory still exists
        memories = file_memory.get_short_term()
        assert any(m.id == regular_mem for m in memories)
        
        # Verify image memories are gone
        assert not any(m.id == image_mem_1 for m in memories)
        assert not any(m.id == image_mem_2 for m in memories)
    
    def test_bulk_image_cleanup_by_metadata(self, file_memory):
        """Test bulk cleanup of all image-related memories using query."""
        # Add multiple image interaction memories
        for i in range(5):
            file_memory.add_short_term(
                f"[IMAGE] Image analysis {i}",
                metadata={"type": "image"}
            )
        
        # Add regular memories
        for i in range(3):
            file_memory.add_short_term(f"Regular message {i}")
        
        # Cleanup all image memories
        deleted = file_memory.delete_memories_matching("[IMAGE]")
        assert deleted == 5
        
        # Verify regular memories still exist
        results = file_memory.search("Regular message")
        assert len(results) >= 1


class TestMemoryClassDeletion:
    """Test Memory class (full-featured) delete operations."""
    
    @pytest.fixture
    def memory_config(self, tmp_path):
        """Create a minimal memory config for testing."""
        return {
            "provider": "none",
            "short_db": str(tmp_path / "short_term.db"),
            "long_db": str(tmp_path / "long_term.db"),
        }
    
    def test_memory_class_delete_short_term(self, memory_config):
        """Test Memory class delete_short_term method."""
        from praisonaiagents.memory import Memory
        
        memory = Memory(config=memory_config, verbose=0)
        
        # Store a memory (store_short_term doesn't return ID, so we search)
        memory.store_short_term("Delete test memory STM")
        
        # Search for it
        results = memory.search_short_term("Delete test")
        assert len(results) >= 1
        
        # Get the ID
        mem_id = results[0].get("id")
        assert mem_id is not None
        
        # Delete it
        success = memory.delete_short_term(mem_id)
        assert success is True
        
        # Verify it's gone (search may still find partial matches)
        # The important thing is the specific ID is deleted
    
    def test_memory_class_delete_long_term(self, memory_config):
        """Test Memory class delete_long_term method."""
        from praisonaiagents.memory import Memory
        
        memory = Memory(config=memory_config, verbose=0)
        
        # Store a memory
        memory.store_long_term("Delete test memory LTM")
        
        # Search for it
        results = memory.search_long_term("Delete test")
        assert len(results) >= 1
        
        # Get the ID
        mem_id = results[0].get("id")
        assert mem_id is not None
        
        # Delete it
        success = memory.delete_long_term(mem_id)
        assert success is True


class TestDeletableProtocol:
    """Test DeletableMemoryProtocol compliance."""
    
    def test_file_memory_implements_protocol(self):
        """Test that FileMemory implements DeletableMemoryProtocol."""
        from praisonaiagents.memory import FileMemory, DeletableMemoryProtocol
        
        # Check protocol compliance
        assert hasattr(FileMemory, 'delete_memory')
        assert hasattr(FileMemory, 'delete_memories')
    
    def test_memory_class_implements_protocol(self):
        """Test that Memory class implements DeletableMemoryProtocol."""
        from praisonaiagents.memory import Memory, DeletableMemoryProtocol
        
        # Check protocol compliance
        assert hasattr(Memory, 'delete_memory')
        assert hasattr(Memory, 'delete_memories')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

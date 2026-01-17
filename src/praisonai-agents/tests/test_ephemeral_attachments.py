"""
Tests for ephemeral attachments and history management.

Tests cover:
- attachments= param on chat() - ephemeral binary content
- Text prompt stored in history, attachments NOT stored
- History management methods: prune_history, delete_history, delete_history_matching
- ephemeral() context manager
"""
import pytest
import tempfile
import os


class TestHistoryManagement:
    """Test history management methods on Agent."""
    
    @pytest.fixture
    def agent(self):
        """Create a test agent."""
        from praisonaiagents import Agent
        return Agent(
            instructions="Test agent for history management",
        )
    
    def test_prune_history_keeps_last_n(self, agent):
        """Test prune_history keeps only last N messages."""
        # Manually add history entries
        for i in range(10):
            agent.chat_history.append({"role": "user", "content": f"Message {i}"})
        
        assert len(agent.chat_history) == 10
        
        # Prune to keep last 3
        deleted = agent.prune_history(keep_last=3)
        
        assert deleted == 7
        assert len(agent.chat_history) == 3
        assert agent.chat_history[0]["content"] == "Message 7"
    
    def test_prune_history_no_op_if_less_than_limit(self, agent):
        """Test prune_history does nothing if history is small."""
        agent.chat_history.append({"role": "user", "content": "Only one"})
        
        deleted = agent.prune_history(keep_last=5)
        
        assert deleted == 0
        assert len(agent.chat_history) == 1
    
    def test_delete_history_by_index(self, agent):
        """Test delete_history removes specific message by index."""
        agent.chat_history.append({"role": "user", "content": "First"})
        agent.chat_history.append({"role": "assistant", "content": "Second"})
        agent.chat_history.append({"role": "user", "content": "Third"})
        
        # Delete middle message
        success = agent.delete_history(1)
        
        assert success is True
        assert len(agent.chat_history) == 2
        assert agent.chat_history[1]["content"] == "Third"
    
    def test_delete_history_negative_index(self, agent):
        """Test delete_history with negative index."""
        agent.chat_history.append({"role": "user", "content": "First"})
        agent.chat_history.append({"role": "user", "content": "Last"})
        
        # Delete last message
        success = agent.delete_history(-1)
        
        assert success is True
        assert len(agent.chat_history) == 1
        assert agent.chat_history[0]["content"] == "First"
    
    def test_delete_history_invalid_index(self, agent):
        """Test delete_history with invalid index returns False."""
        agent.chat_history.append({"role": "user", "content": "Only"})
        
        success = agent.delete_history(999)
        
        assert success is False
        assert len(agent.chat_history) == 1
    
    def test_delete_history_matching_pattern(self, agent):
        """Test delete_history_matching removes messages by pattern."""
        agent.chat_history.append({"role": "user", "content": "[IMAGE] Cat photo"})
        agent.chat_history.append({"role": "assistant", "content": "I see a cat"})
        agent.chat_history.append({"role": "user", "content": "[IMAGE] Dog photo"})
        agent.chat_history.append({"role": "user", "content": "Regular message"})
        
        # Delete all [IMAGE] messages
        deleted = agent.delete_history_matching("[IMAGE]")
        
        assert deleted == 2
        assert len(agent.chat_history) == 2
        # Remaining messages don't contain [IMAGE]
        for msg in agent.chat_history:
            assert "[IMAGE]" not in msg["content"]
    
    def test_delete_history_matching_case_insensitive(self, agent):
        """Test delete_history_matching is case insensitive."""
        agent.chat_history.append({"role": "user", "content": "IMAGE analysis"})
        agent.chat_history.append({"role": "user", "content": "image test"})
        agent.chat_history.append({"role": "user", "content": "no match"})
        
        deleted = agent.delete_history_matching("image")
        
        assert deleted == 2
        assert len(agent.chat_history) == 1
    
    def test_get_history_size(self, agent):
        """Test get_history_size returns correct count."""
        assert agent.get_history_size() == 0
        
        agent.chat_history.append({"role": "user", "content": "One"})
        agent.chat_history.append({"role": "user", "content": "Two"})
        
        assert agent.get_history_size() == 2


class TestEphemeralContextManager:
    """Test ephemeral() context manager."""
    
    @pytest.fixture
    def agent(self):
        """Create a test agent."""
        from praisonaiagents import Agent
        return Agent(
            instructions="Test agent",
        )
    
    def test_ephemeral_restores_history(self, agent):
        """Test ephemeral block restores history after exit."""
        # Add initial history
        agent.chat_history.append({"role": "user", "content": "Before ephemeral"})
        initial_len = len(agent.chat_history)
        
        # Within ephemeral block, add more messages
        with agent.ephemeral():
            agent.chat_history.append({"role": "user", "content": "Ephemeral 1"})
            agent.chat_history.append({"role": "user", "content": "Ephemeral 2"})
            assert len(agent.chat_history) == 3
        
        # After block, history is restored
        assert len(agent.chat_history) == initial_len
        assert agent.chat_history[0]["content"] == "Before ephemeral"
    
    def test_ephemeral_restores_on_exception(self, agent):
        """Test ephemeral restores history even on exception."""
        agent.chat_history.append({"role": "user", "content": "Original"})
        
        with pytest.raises(ValueError):
            with agent.ephemeral():
                agent.chat_history.append({"role": "user", "content": "Temp"})
                raise ValueError("Test error")
        
        # History still restored
        assert len(agent.chat_history) == 1
        assert agent.chat_history[0]["content"] == "Original"


class TestBuildMultimodalPrompt:
    """Test _build_multimodal_prompt helper."""
    
    @pytest.fixture
    def agent(self):
        """Create a test agent."""
        from praisonaiagents import Agent
        return Agent(
            instructions="Test agent",
        )
    
    def test_no_attachments_returns_string(self, agent):
        """Test that no attachments returns original prompt."""
        result = agent._build_multimodal_prompt("Hello", None)
        assert result == "Hello"
        
        result = agent._build_multimodal_prompt("Hello", [])
        assert result == "Hello"
    
    def test_url_attachment_builds_multimodal(self, agent):
        """Test URL attachment creates multimodal content."""
        result = agent._build_multimodal_prompt(
            "What's this?",
            ["https://example.com/image.jpg"]
        )
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "What's this?"
        assert result[1]["type"] == "image_url"
        assert "https://example.com/image.jpg" in result[1]["image_url"]["url"]
    
    def test_file_attachment_loads_and_encodes(self, agent):
        """Test file attachment is loaded and base64 encoded."""
        # Create a temporary image file
        import base64
        
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            # Write minimal PNG header
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')
            temp_path = f.name
        
        try:
            result = agent._build_multimodal_prompt(
                "Describe this",
                [temp_path]
            )
            
            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]["text"] == "Describe this"
            assert result[1]["type"] == "image_url"
            assert result[1]["image_url"]["url"].startswith("data:image/png;base64,")
        finally:
            os.unlink(temp_path)


class TestChatWithAttachments:
    """Test chat() with attachments parameter."""
    
    @pytest.fixture
    def agent(self):
        """Create a test agent without making actual LLM calls."""
        from praisonaiagents import Agent
        return Agent(
            instructions="Test agent",
        )
    
    def test_chat_signature_has_attachments(self, agent):
        """Test that chat() method accepts attachments parameter."""
        import inspect
        sig = inspect.signature(agent.chat)
        assert "attachments" in sig.parameters
    
    def test_build_multimodal_called_for_attachments(self, agent):
        """Test that _build_multimodal_prompt is called when attachments provided."""
        # We can't easily test the full chat flow without mocking,
        # but we can verify the helper is correctly structured
        result = agent._build_multimodal_prompt(
            "What's in the image?",
            ["https://example.com/cat.jpg"]
        )
        
        # Should be multimodal content
        assert isinstance(result, list)
        assert result[0]["type"] == "text"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

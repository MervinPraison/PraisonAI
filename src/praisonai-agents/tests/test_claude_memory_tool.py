"""
Tests for Claude Memory Tool.

Claude Memory Tool enables Claude to store and retrieve information across
conversations through a memory file directory.

Reference: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/memory-tool

NOTE: These tests are skipped because the ClaudeMemoryTool module has not been
implemented yet. The module is planned for future development.
"""

import os
import shutil
import tempfile
import pytest
from pathlib import Path

# Skip all tests in this module - ClaudeMemoryTool is not yet implemented
pytestmark = pytest.mark.skip(reason="ClaudeMemoryTool module not yet implemented")


class TestClaudeMemoryToolBasics:
    """Tests for ClaudeMemoryTool basic functionality."""
    
    def test_import(self):
        """Test that ClaudeMemoryTool can be imported."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        assert ClaudeMemoryTool is not None
    
    def test_init_default(self):
        """Test default initialization."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            assert tool.memory_root.exists()
            assert tool.user_id == "default"
    
    def test_init_with_user_id(self):
        """Test initialization with custom user_id."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir, user_id="test_user")
            assert tool.user_id == "test_user"
    
    def test_get_tool_definition(self):
        """Test tool definition for API."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            definition = tool.get_tool_definition()
            
            assert definition["type"] == "memory_20250818"
            assert definition["name"] == "memory"
    
    def test_get_beta_header(self):
        """Test beta header value."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            header = tool.get_beta_header()
            
            assert header == "context-management-2025-06-27"


class TestClaudeMemoryToolPathValidation:
    """Tests for path validation and security."""
    
    def test_valid_path(self):
        """Test valid path validation."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            path = tool._validate_path("/memories")
            assert path == tool.memory_root
    
    def test_valid_subpath(self):
        """Test valid subpath validation."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            path = tool._validate_path("/memories/notes.txt")
            assert path == tool.memory_root / "notes.txt"
    
    def test_invalid_path_no_memories_prefix(self):
        """Test that paths without /memories prefix are rejected."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            with pytest.raises(ValueError, match="must start with /memories"):
                tool._validate_path("/etc/passwd")
    
    def test_directory_traversal_blocked(self):
        """Test that directory traversal is blocked."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            with pytest.raises(ValueError):
                tool._validate_path("/memories/../../../etc/passwd")


class TestClaudeMemoryToolCommands:
    """Tests for memory tool commands."""
    
    def test_view_empty_directory(self):
        """Test viewing empty directory."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            result = tool.view(path="/memories")
            
            assert "Directory: /memories" in result
            assert "(empty directory)" in result
    
    def test_create_and_view_file(self):
        """Test creating and viewing a file."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            # Create file
            result = tool.create(path="/memories/notes.txt", file_text="Hello, World!")
            assert "created successfully" in result
            
            # View file
            result = tool.view(path="/memories/notes.txt")
            assert "Hello, World!" in result
    
    def test_view_directory_with_files(self):
        """Test viewing directory with files."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            # Create files
            tool.create(path="/memories/file1.txt", file_text="Content 1")
            tool.create(path="/memories/file2.txt", file_text="Content 2")
            
            # View directory
            result = tool.view(path="/memories")
            assert "file1.txt" in result
            assert "file2.txt" in result
    
    def test_str_replace(self):
        """Test string replacement in file."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            # Create file
            tool.create(path="/memories/notes.txt", file_text="Hello, World!")
            
            # Replace text
            result = tool.str_replace(
                path="/memories/notes.txt",
                old_str="World",
                new_str="Claude"
            )
            assert "edited" in result
            
            # Verify replacement
            result = tool.view(path="/memories/notes.txt")
            assert "Hello, Claude!" in result
    
    def test_str_replace_not_found(self):
        """Test string replacement when text not found."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            tool.create(path="/memories/notes.txt", file_text="Hello, World!")
            
            with pytest.raises(ValueError, match="not found"):
                tool.str_replace(
                    path="/memories/notes.txt",
                    old_str="Nonexistent",
                    new_str="Replacement"
                )
    
    def test_insert(self):
        """Test inserting text at line."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            # Create file with multiple lines
            tool.create(path="/memories/notes.txt", file_text="Line 1\nLine 2\nLine 3")
            
            # Insert at line 1
            result = tool.insert(
                path="/memories/notes.txt",
                insert_line=1,
                insert_text="Inserted Line"
            )
            assert "inserted" in result
            
            # Verify insertion
            result = tool.view(path="/memories/notes.txt")
            assert "Inserted Line" in result
    
    def test_delete_file(self):
        """Test deleting a file."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            # Create and delete file
            tool.create(path="/memories/notes.txt", file_text="Content")
            result = tool.delete(path="/memories/notes.txt")
            
            assert "deleted" in result
            
            # Verify deletion
            with pytest.raises(RuntimeError):
                tool.view(path="/memories/notes.txt")
    
    def test_delete_root_blocked(self):
        """Test that deleting /memories root is blocked."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            with pytest.raises(ValueError, match="Cannot delete"):
                tool.delete(path="/memories")
    
    def test_rename(self):
        """Test renaming a file."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            # Create file
            tool.create(path="/memories/old.txt", file_text="Content")
            
            # Rename
            result = tool.rename(
                old_path="/memories/old.txt",
                new_path="/memories/new.txt"
            )
            assert "Renamed" in result
            
            # Verify rename
            with pytest.raises(RuntimeError):
                tool.view(path="/memories/old.txt")
            
            result = tool.view(path="/memories/new.txt")
            assert "Content" in result
    
    def test_clear_all(self):
        """Test clearing all memory."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            # Create files
            tool.create(path="/memories/file1.txt", file_text="Content 1")
            tool.create(path="/memories/file2.txt", file_text="Content 2")
            
            # Clear all
            result = tool.clear_all()
            assert "cleared" in result
            
            # Verify empty
            result = tool.view(path="/memories")
            assert "(empty directory)" in result


class TestClaudeMemoryToolProcessToolCall:
    """Tests for process_tool_call method."""
    
    def test_process_view_command(self):
        """Test processing view command."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            result = tool.process_tool_call({
                "command": "view",
                "path": "/memories"
            })
            
            assert "Directory: /memories" in result
    
    def test_process_create_command(self):
        """Test processing create command."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            result = tool.process_tool_call({
                "command": "create",
                "path": "/memories/test.txt",
                "file_text": "Test content"
            })
            
            assert "created" in result
    
    def test_process_unknown_command(self):
        """Test processing unknown command."""
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ClaudeMemoryTool(base_path=tmpdir)
            
            result = tool.process_tool_call({
                "command": "unknown_command",
                "path": "/memories"
            })
            
            assert "Error" in result


class TestLLMClaudeMemoryIntegration:
    """Tests for LLM class integration with Claude Memory Tool."""
    
    def test_llm_init_with_claude_memory_true(self):
        """Test LLM initialization with claude_memory=True."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-sonnet-4-20250514", claude_memory=True)
        assert llm.claude_memory == True
    
    def test_llm_init_with_claude_memory_false(self):
        """Test LLM initialization with claude_memory=False."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-sonnet-4-20250514", claude_memory=False)
        assert llm.claude_memory == False
    
    def test_llm_init_without_claude_memory(self):
        """Test LLM initialization without claude_memory parameter."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="gpt-4o-mini")
        assert llm.claude_memory is None
    
    def test_llm_supports_claude_memory_anthropic(self):
        """Test _supports_claude_memory for Anthropic model."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-sonnet-4-20250514", claude_memory=True)
        assert llm._supports_claude_memory() == True
    
    def test_llm_supports_claude_memory_non_anthropic(self):
        """Test _supports_claude_memory for non-Anthropic model."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="gpt-4o-mini", claude_memory=True)
        assert llm._supports_claude_memory() == False
    
    def test_llm_get_claude_memory_tool(self):
        """Test _get_claude_memory_tool method."""
        from praisonaiagents.llm.llm import LLM
        from praisonaiagents.tools.claude_memory_tool import ClaudeMemoryTool
        
        llm = LLM(model="anthropic/claude-sonnet-4-20250514", claude_memory=True)
        tool = llm._get_claude_memory_tool()
        
        assert isinstance(tool, ClaudeMemoryTool)
    
    def test_llm_is_memory_tool_call(self):
        """Test _is_memory_tool_call method."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-sonnet-4-20250514", claude_memory=True)
        
        assert llm._is_memory_tool_call("memory") == True
        assert llm._is_memory_tool_call("other_tool") == False


class TestAgentClaudeMemoryIntegration:
    """Tests for Agent class integration with Claude Memory Tool."""
    
    def test_agent_init_with_claude_memory_true(self):
        """Test Agent initialization with claude_memory=True."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-sonnet-4-20250514",
            claude_memory=True
        )
        assert agent.claude_memory == True
    
    def test_agent_init_with_claude_memory_false(self):
        """Test Agent initialization with claude_memory=False."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-sonnet-4-20250514",
            claude_memory=False
        )
        assert agent.claude_memory == False
    
    def test_agent_init_without_claude_memory(self):
        """Test Agent initialization without claude_memory parameter."""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test Agent")
        assert agent.claude_memory is None
    
    def test_agent_passes_claude_memory_to_llm(self):
        """Test that Agent passes claude_memory to LLM instance."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-sonnet-4-20250514",
            claude_memory=True
        )
        
        if hasattr(agent, 'llm_instance') and agent.llm_instance:
            assert agent.llm_instance.claude_memory == True


class TestClaudeMemoryToolIntegration:
    """Integration tests for Claude Memory Tool (requires API key)."""
    
    @pytest.mark.skip(reason="Requires ANTHROPIC_API_KEY environment variable")
    def test_claude_memory_with_anthropic(self):
        """Test Claude memory with actual Anthropic API."""
        import os
        from praisonaiagents import Agent
        
        # Skip if no API key
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")
        
        agent = Agent(
            name="Memory Test Agent",
            instructions="You are a helpful assistant with memory capabilities.",
            llm="anthropic/claude-sonnet-4-20250514",
            claude_memory=True,
            verbose=False
        )
        
        # First call - should check memory
        result1 = agent.start("Remember that my favorite color is blue.")
        assert result1 is not None
        
        # Second call - should recall from memory
        result2 = agent.start("What is my favorite color?")
        assert result2 is not None

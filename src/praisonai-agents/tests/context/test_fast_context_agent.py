"""
Tests for FastContextAgent class.
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directory structure
        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()
        
        (src_dir / "main.py").write_text("""
def main():
    print("Hello, World!")
    authenticate_user()

def authenticate_user():
    # Authentication logic here
    pass

class UserService:
    def login(self, username, password):
        return True
""")
        
        (src_dir / "utils.py").write_text("""
import os

def get_config():
    return {"debug": True}

def validate_input(data):
    if not data:
        raise ValueError("Empty data")
    return True
""")
        
        auth_dir = src_dir / "auth"
        auth_dir.mkdir()
        
        (auth_dir / "handler.py").write_text("""
from typing import Optional

class AuthHandler:
    def __init__(self):
        self.token = None
    
    def authenticate(self, credentials: dict) -> bool:
        return True
    
    def logout(self):
        self.token = None
""")
        
        yield tmpdir


class TestFastContextAgentInit:
    """Tests for FastContextAgent initialization."""
    
    def test_default_initialization(self, temp_workspace):
        """Test default initialization."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        
        assert agent.workspace_path == temp_workspace
        assert agent.max_turns == 4
        assert agent.max_parallel == 8
        assert agent.model == "gpt-4o-mini"
    
    def test_custom_initialization(self, temp_workspace):
        """Test custom initialization."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(
            workspace_path=temp_workspace,
            max_turns=3,
            max_parallel=4,
            model="claude-3-haiku-20240307"
        )
        
        assert agent.max_turns == 3
        assert agent.max_parallel == 4
        assert agent.model == "claude-3-haiku-20240307"


class TestFastContextAgentSearch:
    """Tests for FastContextAgent search functionality."""
    
    def test_search_returns_result(self, temp_workspace):
        """Test that search returns FastContextResult."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        from praisonaiagents.context.fast.result import FastContextResult
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        
        # Use simple search without LLM
        result = agent.search_simple("authenticate")
        
        assert isinstance(result, FastContextResult)
        assert result.total_files > 0
    
    def test_search_finds_relevant_files(self, temp_workspace):
        """Test that search finds relevant files."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        
        result = agent.search_simple("authenticate")
        
        # Should find files containing "authenticate"
        file_paths = [f.path for f in result.files]
        assert any("main.py" in p for p in file_paths)
        assert any("handler.py" in p for p in file_paths)
    
    def test_search_with_file_pattern(self, temp_workspace):
        """Test search with file pattern filter."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        
        result = agent.search_simple("def", include_patterns=["**/auth/*.py"])
        
        # Should only find in auth directory
        for f in result.files:
            assert "auth" in f.path
    
    def test_search_records_timing(self, temp_workspace):
        """Test that search records timing information."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        
        result = agent.search_simple("def")
        
        # search_time_ms >= 0 is valid (can be 0 for very fast searches)
        assert result.search_time_ms >= 0
        assert result.turns_used == 1
        assert result.total_tool_calls == 1
    
    def test_search_no_results(self, temp_workspace):
        """Test search with no matches."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        
        result = agent.search_simple("nonexistent_pattern_xyz123")
        
        assert result.total_files == 0


class TestFastContextAgentTools:
    """Tests for FastContextAgent tool definitions."""
    
    def test_get_tools(self, temp_workspace):
        """Test getting tool definitions."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        tools = agent.get_tools()
        
        assert len(tools) == 4
        tool_names = [t["name"] for t in tools]
        assert "grep_search" in tool_names
        assert "glob_search" in tool_names
        assert "read_file" in tool_names
        assert "list_directory" in tool_names
    
    def test_execute_tool(self, temp_workspace):
        """Test executing a tool directly."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        
        result = agent.execute_tool("glob_search", pattern="**/*.py")
        
        assert len(result) >= 3  # At least 3 .py files


class TestFastContextAgentLLMSearch:
    """Tests for FastContextAgent LLM-powered search."""
    
    def test_search_falls_back_to_simple(self, temp_workspace):
        """Test that search falls back to simple when LLM not available."""
        from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
        
        agent = FastContextAgent(workspace_path=temp_workspace)
        
        # search() should fall back to search_simple when LLM is not available
        result = agent.search("find authentication code")
        
        # Should still return results (from simple search fallback)
        assert result is not None
        assert result.query == "find authentication code"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

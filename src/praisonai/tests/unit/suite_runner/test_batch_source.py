"""
Tests for BatchSource - discovers Python files with PraisonAI imports.

TDD: These tests define the expected behavior before implementation.
"""

from pathlib import Path
import tempfile


class TestBatchSourceImportDetection:
    """Test import pattern detection."""
    
    def test_detects_praisonaiagents_import(self):
        """Should detect 'from praisonaiagents import ...'"""
        from praisonai.suite_runner.batch_source import BatchSource
        
        content = """
from praisonaiagents import Agent

agent = Agent(instructions="Test")
"""
        source = BatchSource(root=Path("."))
        assert source._has_praisonai_import(content) is True
    
    def test_detects_praisonai_import(self):
        """Should detect 'from praisonai import ...'"""
        from praisonai.suite_runner.batch_source import BatchSource
        
        content = """
from praisonai import Agent

agent = Agent()
"""
        source = BatchSource(root=Path("."))
        assert source._has_praisonai_import(content) is True
    
    def test_detects_import_praisonaiagents(self):
        """Should detect 'import praisonaiagents'"""
        from praisonai.suite_runner.batch_source import BatchSource
        
        content = """
import praisonaiagents

agent = praisonaiagents.Agent()
"""
        source = BatchSource(root=Path("."))
        assert source._has_praisonai_import(content) is True
    
    def test_rejects_non_praisonai_file(self):
        """Should reject files without PraisonAI imports."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        content = """
import os
import sys

print("Hello world")
"""
        source = BatchSource(root=Path("."))
        assert source._has_praisonai_import(content) is False
    
    def test_rejects_commented_import(self):
        """Should reject commented imports."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        content = """
# from praisonaiagents import Agent
print("Hello")
"""
        source = BatchSource(root=Path("."))
        # Commented imports should not match
        assert source._has_praisonai_import(content) is False


class TestBatchSourceDiscovery:
    """Test file discovery with filtering."""
    
    def test_discovers_files_in_current_directory(self):
        """Should discover .py files in root directory only (non-recursive)."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create a file with praisonai import (not a test file name)
            (root / "my_agent.py").write_text("from praisonaiagents import Agent\n")
            
            # Create a file without praisonai import
            (root / "other.py").write_text("print('hello')\n")
            
            # Create a subdirectory with a file (should not be found without recursive)
            subdir = root / "subdir"
            subdir.mkdir()
            (subdir / "nested.py").write_text("from praisonaiagents import Agent\n")
            
            source = BatchSource(root=root, recursive=False)
            items = source.discover()
            
            # Should only find my_agent.py (has praisonai import, in root)
            assert len(items) == 1
            assert items[0].source_path.name == "my_agent.py"
    
    def test_discovers_files_recursively(self):
        """Should discover .py files recursively when recursive=True."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create files
            (root / "root_agent.py").write_text("from praisonaiagents import Agent\n")
            
            subdir = root / "subdir"
            subdir.mkdir()
            (subdir / "nested_agent.py").write_text("from praisonai import Agent\n")
            
            source = BatchSource(root=root, recursive=True)
            items = source.discover()
            
            # Should find both files
            assert len(items) == 2
            names = {item.source_path.name for item in items}
            assert names == {"root_agent.py", "nested_agent.py"}
    
    def test_respects_depth_limit(self):
        """Should respect depth limit when recursive."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create nested structure
            (root / "level0.py").write_text("from praisonaiagents import Agent\n")
            
            level1 = root / "level1"
            level1.mkdir()
            (level1 / "level1.py").write_text("from praisonaiagents import Agent\n")
            
            level2 = level1 / "level2"
            level2.mkdir()
            (level2 / "level2.py").write_text("from praisonaiagents import Agent\n")
            
            # Depth 1 should only find level0 and level1
            source = BatchSource(root=root, recursive=True, depth=1)
            items = source.discover()
            
            names = {item.source_path.name for item in items}
            assert "level0.py" in names
            assert "level1.py" in names
            assert "level2.py" not in names
    
    def test_excludes_test_files_by_default(self):
        """Should exclude test_*.py and *_test.py by default."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create test files
            (root / "test_agent.py").write_text("from praisonaiagents import Agent\n")
            (root / "agent_test.py").write_text("from praisonaiagents import Agent\n")
            (root / "conftest.py").write_text("from praisonaiagents import Agent\n")
            
            # Create regular file
            (root / "my_agent.py").write_text("from praisonaiagents import Agent\n")
            
            source = BatchSource(root=root, exclude_tests=True)
            items = source.discover()
            
            # Should only find my_agent.py
            assert len(items) == 1
            assert items[0].source_path.name == "my_agent.py"
    
    def test_includes_test_files_when_disabled(self):
        """Should include test files when exclude_tests=False."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "test_agent.py").write_text("from praisonaiagents import Agent\n")
            (root / "my_agent.py").write_text("from praisonaiagents import Agent\n")
            
            source = BatchSource(root=root, exclude_tests=False)
            items = source.discover()
            
            assert len(items) == 2


class TestBatchSourceRunItem:
    """Test RunItem creation."""
    
    def test_creates_runitem_with_correct_fields(self):
        """Should create RunItem with correct metadata."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            content = """
from praisonaiagents import Agent

agent = Agent(instructions="Test")
agent.start()
"""
            (root / "my_agent.py").write_text(content)
            
            source = BatchSource(root=root)
            items = source.discover()
            
            assert len(items) == 1
            item = items[0]
            
            assert item.suite == "batch"
            assert item.language == "python"
            assert item.runnable is True
            assert item.uses_agent is True
    
    def test_detects_agent_usage(self):
        """Should detect Agent class usage."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "agent.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
""")
            
            source = BatchSource(root=root)
            items = source.discover()
            
            assert items[0].uses_agent is True
    
    def test_detects_agents_usage(self):
        """Should detect Agents/PraisonAIAgents class usage."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "agents.py").write_text("""
from praisonaiagents import Agent, Agents
agents = Agents(agents=[Agent()])
""")
            
            source = BatchSource(root=root)
            items = source.discover()
            
            assert items[0].uses_agents is True


class TestBatchSourceGroups:
    """Test group detection."""
    
    def test_assigns_root_group_for_top_level_files(self):
        """Files in root should have group 'root'."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "agent.py").write_text("from praisonaiagents import Agent\n")
            
            source = BatchSource(root=root)
            items = source.discover()
            
            assert items[0].group == "root"
    
    def test_assigns_directory_group_for_nested_files(self):
        """Files in subdirs should have group = subdir name."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subdir = root / "my_agents"
            subdir.mkdir()
            (subdir / "agent.py").write_text("from praisonaiagents import Agent\n")
            
            source = BatchSource(root=root, recursive=True)
            items = source.discover()
            
            assert items[0].group == "my_agents"
    
    def test_get_groups_returns_all_groups(self):
        """get_groups() should return all discovered groups."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "root.py").write_text("from praisonaiagents import Agent\n")
            
            dir1 = root / "agents"
            dir1.mkdir()
            (dir1 / "a.py").write_text("from praisonaiagents import Agent\n")
            
            dir2 = root / "tools"
            dir2.mkdir()
            (dir2 / "b.py").write_text("from praisonaiagents import Agent\n")
            
            source = BatchSource(root=root, recursive=True)
            groups = source.get_groups()
            
            assert set(groups) == {"root", "agents", "tools"}


class TestBatchSourceServerDetection:
    """Test server script detection."""
    
    def test_detects_uvicorn_server(self):
        """Should detect uvicorn.run() as server script."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "server.py").write_text("""
from praisonaiagents import Agent
import uvicorn
from fastapi import FastAPI

app = FastAPI()
uvicorn.run(app, host="0.0.0.0", port=8000)
""")
            
            # Need exclude_servers=False to include server scripts
            source = BatchSource(root=root, exclude_servers=False)
            items = source.discover()
            
            assert len(items) == 1
            assert items[0].is_server is True
    
    def test_detects_launch_method(self):
        """Should detect .launch() as server script."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "api.py").write_text("""
from praisonaiagents import Agent

agent = Agent(instructions="Test")
agent.launch(path="/ask", port=3030)
""")
            
            source = BatchSource(root=root, exclude_servers=False)
            items = source.discover()
            
            assert len(items) == 1
            assert items[0].is_server is True
    
    def test_detects_flask_app_run(self):
        """Should detect app.run() (Flask) as server script."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "flask_app.py").write_text("""
from praisonaiagents import Agent
from flask import Flask

app = Flask(__name__)
app.run(debug=True)
""")
            
            source = BatchSource(root=root, exclude_servers=False)
            items = source.discover()
            
            assert len(items) == 1
            assert items[0].is_server is True
    
    def test_detects_streamlit_import(self):
        """Should detect streamlit import as server script."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "streamlit_app.py").write_text("""
from praisonaiagents import Agent
import streamlit as st

st.title("Agent App")
""")
            
            source = BatchSource(root=root, exclude_servers=False)
            items = source.discover()
            
            assert len(items) == 1
            assert items[0].is_server is True
    
    def test_detects_gradio_import(self):
        """Should detect gradio import as server script."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "gradio_app.py").write_text("""
from praisonaiagents import Agent
import gradio as gr

demo = gr.Interface(fn=lambda x: x, inputs="text", outputs="text")
demo.launch()
""")
            
            source = BatchSource(root=root, exclude_servers=False)
            items = source.discover()
            
            assert len(items) == 1
            assert items[0].is_server is True
    
    def test_non_server_script(self):
        """Should not mark regular scripts as server."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "agent.py").write_text("""
from praisonaiagents import Agent

agent = Agent(instructions="Test")
result = agent.start("Hello")
print(result)
""")
            
            source = BatchSource(root=root)
            items = source.discover()
            
            assert len(items) == 1
            assert items[0].is_server is False


class TestBatchSourceServerExclusion:
    """Test server script exclusion."""
    
    def test_excludes_servers_by_default(self):
        """Should exclude server scripts by default."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Server script
            (root / "server.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
agent.launch(path="/ask", port=3030)
""")
            
            # Regular script
            (root / "agent.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
print(agent.start("Hello"))
""")
            
            source = BatchSource(root=root, exclude_servers=True)
            items = source.discover()
            
            # Should only find agent.py
            assert len(items) == 1
            assert items[0].source_path.name == "agent.py"
    
    def test_includes_servers_when_disabled(self):
        """Should include server scripts when exclude_servers=False."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "server.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
agent.launch(path="/ask", port=3030)
""")
            
            (root / "agent.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
""")
            
            source = BatchSource(root=root, exclude_servers=False)
            items = source.discover()
            
            assert len(items) == 2
    
    def test_server_only_mode(self):
        """Should only return server scripts when server_only=True."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "server.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
agent.launch(path="/ask", port=3030)
""")
            
            (root / "agent.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
""")
            
            source = BatchSource(root=root, server_only=True)
            items = source.discover()
            
            # Should only find server.py
            assert len(items) == 1
            assert items[0].source_path.name == "server.py"


class TestBatchSourceFiltering:
    """Test filtering by agent type."""
    
    def test_filter_agent_only(self):
        """Should filter to only scripts using Agent class."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Agent only
            (root / "single.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
""")
            
            # Agents (multi-agent)
            (root / "multi.py").write_text("""
from praisonaiagents import Agent, Agents
agents = Agents(agents=[Agent()])
""")
            
            source = BatchSource(root=root, filter_type="agent")
            items = source.discover()
            
            # Should find both (both use Agent)
            assert len(items) == 2
    
    def test_filter_agents_only(self):
        """Should filter to only scripts using Agents/PraisonAIAgents class."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Agent only
            (root / "single.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
""")
            
            # Agents (multi-agent)
            (root / "multi.py").write_text("""
from praisonaiagents import Agent, Agents
agents = Agents(agents=[Agent()])
""")
            
            source = BatchSource(root=root, filter_type="agents")
            items = source.discover()
            
            # Should only find multi.py
            assert len(items) == 1
            assert items[0].source_path.name == "multi.py"
    
    def test_filter_workflow_only(self):
        """Should filter to only scripts using Workflow class."""
        from praisonai.suite_runner.batch_source import BatchSource
        
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Agent only
            (root / "agent.py").write_text("""
from praisonaiagents import Agent
agent = Agent(instructions="Test")
""")
            
            # Workflow
            (root / "workflow.py").write_text("""
from praisonaiagents import Agent, Workflow
workflow = Workflow(agents=[Agent()])
""")
            
            source = BatchSource(root=root, filter_type="workflow")
            items = source.discover()
            
            # Should only find workflow.py
            assert len(items) == 1
            assert items[0].source_path.name == "workflow.py"

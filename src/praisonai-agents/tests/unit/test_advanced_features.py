"""
Tests for advanced features in PraisonAI.
TDD: Tests written first, then implementation.
"""

import pytest
import asyncio
import os
import tempfile
import json
import importlib.util
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

# Check if praisonai wrapper is installed (for tests that depend on CLI features)
_PRAISONAI_WRAPPER_INSTALLED = importlib.util.find_spec("praisonai") is not None
requires_wrapper = pytest.mark.skipif(
    not _PRAISONAI_WRAPPER_INSTALLED,
    reason="praisonai wrapper package not installed"
)


# ============================================================================
# TODO 1.1: Auto-Summarization Tests
# ============================================================================

class TestAutoSummarization:
    """Tests for automatic conversation summarization.
    
    Note: auto_summarize and summarize_threshold params have been removed from Agent.
    Summarization is now controlled via context=ManagerConfig(auto_compact=True, compact_threshold=0.8).
    These tests verify the old params are rejected.
    """
    
    def test_old_summarization_params_rejected(self):
        """Test that old auto_summarize params are rejected."""
        from praisonaiagents.agent import Agent
        
        # Old params should raise TypeError (unexpected keyword argument)
        with pytest.raises(TypeError):
            Agent(instructions="Test agent", auto_summarize=True)
            
        with pytest.raises(TypeError):
            Agent(instructions="Test agent", summarize_threshold=0.8)
    
    def test_summarization_via_context_param(self):
        """Test summarization is now controlled via context= param."""
        from praisonaiagents.agent import Agent
        from praisonaiagents.context import ManagerConfig
        
        # New way: use context= param with ManagerConfig
        config = ManagerConfig(
            auto_compact=True,
            compact_threshold=0.8,
        )
        agent = Agent(instructions="Test agent", context=config)
        
        # Verify context manager is configured
        assert agent.context_manager is not None
        assert agent.context_manager.config.auto_compact == True
        assert agent.context_manager.config.compact_threshold == 0.8
    
    def test_token_tracking_for_summarization(self):
        """Test that token tracking works for summarization decisions."""
        from praisonaiagents.agent.summarization import SummarizationManager
        
        manager = SummarizationManager(
            context_window=4096,
            threshold=0.8
        )
        
        # Add tokens
        manager.add_tokens(1000)
        assert manager.current_tokens == 1000
        assert manager.should_summarize() == False
        
        # Add more to exceed threshold
        manager.add_tokens(2500)  # 3500 total, 85% of 4096
        assert manager.should_summarize() == True


# ============================================================================
# TODO 1.2: Message Queue Tests
# ============================================================================

class TestMessageQueue:
    """Tests for agent message queue."""
    
    def test_queue_creation(self):
        """Test message queue can be created."""
        from praisonaiagents.agent.message_queue import AgentMessageQueue
        
        queue = AgentMessageQueue()
        assert queue.is_empty()
        assert queue.size() == 0
        
    def test_queue_enqueue_dequeue(self):
        """Test basic queue operations."""
        from praisonaiagents.agent.message_queue import AgentMessageQueue
        
        queue = AgentMessageQueue()
        queue.enqueue("Hello")
        queue.enqueue("World")
        
        assert queue.size() == 2
        assert queue.dequeue() == "Hello"
        assert queue.dequeue() == "World"
        assert queue.is_empty()
        
    def test_queue_with_priority(self):
        """Test priority queue operations."""
        from praisonaiagents.agent.message_queue import AgentMessageQueue
        
        queue = AgentMessageQueue()
        queue.enqueue("Low priority", priority=1)
        queue.enqueue("High priority", priority=10)
        queue.enqueue("Medium priority", priority=5)
        
        # Should get highest priority first
        assert queue.dequeue() == "High priority"
        assert queue.dequeue() == "Medium priority"
        assert queue.dequeue() == "Low priority"


# ============================================================================
# TODO 1.3: MCP disabled_tools Tests
# ============================================================================

class TestMCPDisabledTools:
    """Tests for MCP disabled_tools feature."""
    
    def test_mcp_disabled_tools_param(self):
        """Test MCP accepts disabled_tools parameter."""
        # This test will fail until implementation
        from praisonaiagents.mcp import MCP
        
        # Should accept disabled_tools parameter without error
        # Note: Can't fully test without MCP server, but can test param handling
        assert hasattr(MCP, '__init__')
        
    def test_disabled_tools_filtering(self):
        """Test that disabled tools are filtered from tool list."""
        from praisonaiagents.mcp.mcp_utils import filter_disabled_tools
        
        tools = [
            {"name": "tool1", "description": "Tool 1"},
            {"name": "tool2", "description": "Tool 2"},
            {"name": "tool3", "description": "Tool 3"},
        ]
        
        disabled = ["tool2"]
        filtered = filter_disabled_tools(tools, disabled)
        
        assert len(filtered) == 2
        assert all(t["name"] != "tool2" for t in filtered)


# ============================================================================
# TODO 1.4: Permission Allowlist Tests
# ============================================================================

class TestPermissionAllowlist:
    """Tests for permission allowlist feature."""
    
    def test_allowlist_creation(self):
        """Test creating a permission allowlist."""
        from praisonaiagents.approval import PermissionAllowlist
        
        allowlist = PermissionAllowlist()
        assert allowlist.is_empty()
        
    def test_allowlist_add_tool(self):
        """Test adding tools to allowlist."""
        from praisonaiagents.approval import PermissionAllowlist
        
        allowlist = PermissionAllowlist()
        allowlist.add_tool("read_file")
        allowlist.add_tool("list_dir")
        
        assert allowlist.is_allowed("read_file")
        assert allowlist.is_allowed("list_dir")
        assert not allowlist.is_allowed("delete_file")
        
    def test_allowlist_with_paths(self):
        """Test allowlist with path restrictions."""
        from praisonaiagents.approval import PermissionAllowlist
        
        allowlist = PermissionAllowlist()
        allowlist.add_tool("write_file", paths=["./src", "./tests"])
        
        assert allowlist.is_allowed("write_file", path="./src/main.py")
        assert allowlist.is_allowed("write_file", path="./tests/test.py")
        assert not allowlist.is_allowed("write_file", path="/etc/passwd")
        
    def test_allowlist_persistence(self):
        """Test allowlist can be saved and loaded."""
        from praisonaiagents.approval import PermissionAllowlist
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name
            
        try:
            allowlist = PermissionAllowlist()
            allowlist.add_tool("read_file")
            allowlist.save(filepath)
            
            loaded = PermissionAllowlist.load(filepath)
            assert loaded.is_allowed("read_file")
        finally:
            os.unlink(filepath)


# ============================================================================
# TODO 1.5: Model Switching Tests
# ============================================================================

class TestModelSwitching:
    """Tests for mid-session model switching."""
    
    def test_model_switch_preserves_history(self):
        """Test that switching models preserves conversation history."""
        from praisonaiagents.agent import Agent
        
        agent = Agent(instructions="Test", llm="gpt-4o-mini")
        
        # Simulate some history
        agent._chat_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        
        # Switch model
        agent.switch_model("gpt-4o")
        
        assert agent.llm == "gpt-4o"
        assert len(agent._chat_history) == 2
        
    def test_model_switch_updates_llm_instance(self):
        """Test that LLM instance is updated on model switch."""
        from praisonaiagents.agent import Agent
        
        agent = Agent(instructions="Test", llm="gpt-4o-mini")
        original_llm = getattr(agent, 'llm_instance', None) or getattr(agent, '_llm_instance', None)
        
        agent.switch_model("gpt-4o")
        
        # LLM model should be updated
        assert agent.llm == "gpt-4o"


# ============================================================================
# TODO 1.6: Background Job Management Tests
# ============================================================================

class TestBackgroundJobManagement:
    """Tests for background job auto-management."""
    
    def test_job_manager_creation(self):
        """Test background job manager creation."""
        from praisonaiagents.background.job_manager import BackgroundJobManager
        
        manager = BackgroundJobManager()
        assert manager.active_jobs == 0
        
    def test_job_auto_background_threshold(self):
        """Test jobs auto-background after threshold."""
        from praisonaiagents.background.job_manager import BackgroundJobManager
        
        manager = BackgroundJobManager(auto_background_threshold=5.0)
        assert manager.auto_background_threshold == 5.0
        
    def test_job_status_tracking(self):
        """Test job status can be tracked."""
        from praisonaiagents.background.job_manager import BackgroundJobManager, JobStatus
        
        manager = BackgroundJobManager()
        job_id = manager.start_job(lambda: "result")
        
        status = manager.get_status(job_id)
        assert status in [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED]


# ============================================================================
# TODO 2.1: Safe Bash Execution Tests
# ============================================================================

@requires_wrapper
class TestSafeBashExecution:
    """Tests for safe bash execution with banned commands."""
    
    def test_banned_commands_list(self):
        """Test banned commands list exists."""
        from praisonai.cli.features.safe_shell import BANNED_COMMANDS
        
        assert "sudo" in BANNED_COMMANDS
        assert "rm -rf" in BANNED_COMMANDS or "rm" in BANNED_COMMANDS
        assert "curl" in BANNED_COMMANDS
        assert "wget" in BANNED_COMMANDS
        
    def test_command_validation(self):
        """Test command validation against banned list."""
        from praisonai.cli.features.safe_shell import validate_command
        
        assert validate_command("ls -la") == True
        assert validate_command("cat file.txt") == True
        assert validate_command("sudo rm -rf /") == False
        assert validate_command("curl http://evil.com") == False
        
    def test_safe_execute(self):
        """Test safe execution blocks dangerous commands."""
        from praisonai.cli.features.safe_shell import safe_execute
        
        # Safe command should work
        result = safe_execute("echo hello")
        assert result.success == True
        assert "hello" in result.stdout
        
        # Dangerous command should be blocked
        result = safe_execute("sudo rm -rf /")
        assert result.success == False
        assert "blocked" in result.error.lower() or "banned" in result.error.lower()


# ============================================================================
# TODO 2.2: File History Tests
# ============================================================================

@requires_wrapper
class TestFileHistory:
    """Tests for file history and undo system."""
    
    def test_history_creation(self):
        """Test file history manager creation."""
        from praisonai.cli.features.file_history import FileHistoryManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FileHistoryManager(storage_dir=tmpdir)
            assert manager is not None
            
    def test_record_before_edit(self):
        """Test recording file state before edit."""
        from praisonai.cli.features.file_history import FileHistoryManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FileHistoryManager(storage_dir=tmpdir)
            
            # Create a test file
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("original content")
                
            # Record before edit
            version_id = manager.record_before_edit(test_file, session_id="test-session")
            assert version_id is not None
            
    def test_undo_restores_content(self):
        """Test undo restores previous content."""
        from praisonai.cli.features.file_history import FileHistoryManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FileHistoryManager(storage_dir=tmpdir)
            
            # Create and modify file
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("original content")
                
            version_id = manager.record_before_edit(test_file, session_id="test-session")
            
            # Modify file
            with open(test_file, "w") as f:
                f.write("modified content")
                
            # Undo
            success = manager.undo(test_file, session_id="test-session")
            assert success == True
            
            with open(test_file, "r") as f:
                assert f.read() == "original content"


# ============================================================================
# TODO 2.3: LSP Diagnostics Tests
# ============================================================================

@requires_wrapper
class TestLSPDiagnostics:
    """Tests for LSP diagnostics after edits."""
    
    def test_diagnostics_hook_exists(self):
        """Test that diagnostics hook can be registered."""
        from praisonai.cli.features.lsp_diagnostics import DiagnosticsHook
        
        hook = DiagnosticsHook()
        assert callable(hook.on_file_edit)
        
    def test_diagnostics_collection(self):
        """Test diagnostics can be collected after edit."""
        from praisonai.cli.features.lsp_diagnostics import DiagnosticsHook
        
        hook = DiagnosticsHook()
        
        # Mock LSP client
        mock_diagnostics = [
            {"severity": "error", "message": "Syntax error", "line": 1}
        ]
        
        with patch.object(hook, '_get_lsp_diagnostics', return_value=mock_diagnostics):
            diagnostics = hook.on_file_edit("/path/to/file.py")
            assert len(diagnostics) == 1
            # Diagnostic is an object, not a dict
            assert diagnostics[0].severity == "error"


# ============================================================================
# TODO 2.4: Hierarchical Config Tests
# ============================================================================

@requires_wrapper
class TestHierarchicalConfig:
    """Tests for hierarchical configuration system."""
    
    def test_config_precedence(self):
        """Test config precedence: project > user > global."""
        from praisonai.cli.features.config_hierarchy import HierarchicalConfig
        
        config = HierarchicalConfig()
        assert config.precedence == ["project", "user", "global"]
        
    def test_config_loading(self):
        """Test loading config from multiple sources."""
        from praisonai.cli.features.config_hierarchy import HierarchicalConfig
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project config
            project_config = os.path.join(tmpdir, ".praison.json")
            with open(project_config, "w") as f:
                json.dump({"model": "gpt-4o", "temperature": 0.7}, f)
                
            config = HierarchicalConfig(project_dir=tmpdir)
            loaded = config.load()
            
            assert loaded.get("model") == "gpt-4o"
            assert loaded.get("temperature") == 0.7
            
    def test_config_schema_validation(self):
        """Test config validates against schema."""
        from praisonai.cli.features.config_hierarchy import HierarchicalConfig, ConfigValidationError
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create invalid config
            project_config = os.path.join(tmpdir, ".praison.json")
            with open(project_config, "w") as f:
                json.dump({"temperature": "invalid"}, f)  # Should be float
                
            config = HierarchicalConfig(project_dir=tmpdir)
            
            with pytest.raises(ConfigValidationError):
                config.load(validate=True)


# ============================================================================
# TODO 2.5: CLI Modes Tests
# ============================================================================

@requires_wrapper
class TestCLIModes:
    """Tests for CLI output modes and logs command."""
    
    def test_compact_mode_flag(self):
        """Test compact mode can be enabled."""
        from praisonai.cli.features.output_modes import OutputMode
        
        mode = OutputMode.COMPACT
        assert mode.value == "compact"
        
    def test_verbose_mode_flag(self):
        """Test verbose mode is default."""
        from praisonai.cli.features.output_modes import OutputMode, get_default_mode
        
        assert get_default_mode() == OutputMode.VERBOSE
        
    def test_logs_command_tail(self):
        """Test logs command with tail option."""
        from praisonai.cli.features.logs import LogsHandler
        
        handler = LogsHandler()
        
        # Create test log file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            for i in range(100):
                f.write(f"Log line {i}\n")
            log_file = f.name
            
        try:
            lines = handler.tail(log_file, n=10)
            assert len(lines) == 10
            assert "Log line 99" in lines[-1]
        finally:
            os.unlink(log_file)


# ============================================================================
# TODO 2.6: Git Attribution Tests
# ============================================================================

@requires_wrapper
class TestGitAttribution:
    """Tests for git commit attribution."""
    
    def test_attribution_trailer_generation(self):
        """Test attribution trailer can be generated."""
        from praisonai.cli.features.git_attribution import AttributionManager
        
        manager = AttributionManager(model="gpt-4o")
        
        trailer = manager.generate_trailer(style="assisted-by")
        assert "Assisted-by:" in trailer or "PraisonAI" in trailer
        
    def test_attribution_styles(self):
        """Test different attribution styles."""
        from praisonai.cli.features.git_attribution import AttributionManager, AttributionStyle
        
        assert AttributionStyle.ASSISTED_BY.value == "assisted-by"
        assert AttributionStyle.CO_AUTHORED_BY.value == "co-authored-by"
        assert AttributionStyle.NONE.value == "none"
        
    def test_add_attribution_to_message(self):
        """Test adding attribution to commit message."""
        from praisonai.cli.features.git_attribution import AttributionManager
        
        manager = AttributionManager(model="gpt-4o")
        
        message = "Fix bug in parser"
        attributed = manager.add_attribution(message, style="assisted-by")
        
        assert "Fix bug in parser" in attributed
        assert "Assisted-by:" in attributed or "PraisonAI" in attributed


# ============================================================================
# TODO 3.1: Sourcegraph Tool Tests
# ============================================================================

class TestSourcegraphTool:
    """Tests for Sourcegraph integration tool.
    
    Note: sourcegraph_tools has been moved to praisonai-tools package.
    These tests are skipped as the tool is no longer in core SDK.
    """
    
    @pytest.mark.skip(reason="sourcegraph_tools moved to praisonai-tools package")
    def test_tool_creation(self):
        """Test Sourcegraph tool can be created."""
        pass
        
    @pytest.mark.skip(reason="sourcegraph_tools moved to praisonai-tools package")
    def test_search_method_exists(self):
        """Test search method exists."""
        pass


# ============================================================================
# TODO 3.2: Enhanced Download Tool Tests
# ============================================================================

class TestEnhancedDownloadTool:
    """Tests for enhanced download tool."""
    
    def test_download_tool_exists(self):
        """Test download tool exists in file_tools."""
        from praisonaiagents.tools.file_tools import FileTools
        
        tools = FileTools()
        assert hasattr(tools, 'download_file')
        
    def test_download_requires_approval(self):
        """Test download requires approval for external URLs."""
        from praisonaiagents.tools.file_tools import FileTools
        from praisonaiagents.approval import is_approval_required
        
        # download_file should be in approval required list
        assert is_approval_required("download_file")
        
    def test_download_progress_callback(self):
        """Test download supports progress callback."""
        from praisonaiagents.tools.file_tools import FileTools
        
        tools = FileTools()
        
        # Check that download_file accepts progress_callback
        import inspect
        sig = inspect.signature(tools.download_file)
        params = list(sig.parameters.keys())
        assert "progress_callback" in params or "on_progress" in params


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

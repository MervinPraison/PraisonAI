"""
Unit tests for EditorOutput module.

Tests the user-friendly editor-style output mode with:
- Step numbering
- Human-readable tool labels
- Multi-agent prefix support
- Markdown export
- Thread safety
"""

import pytest
import threading
from unittest.mock import MagicMock, patch


class TestEditorOutputImports:
    """Test that EditorOutput can be imported correctly."""
    
    def test_import_from_output_module(self):
        """Test lazy import from output module."""
        from praisonaiagents.output import EditorOutput
        assert EditorOutput is not None
    
    def test_import_enable_disable(self):
        """Test enable/disable functions can be imported."""
        from praisonaiagents.output import enable_editor_output, disable_editor_output
        assert callable(enable_editor_output)
        assert callable(disable_editor_output)
    
    def test_import_tool_labels(self):
        """Test TOOL_LABELS can be imported."""
        from praisonaiagents.output import TOOL_LABELS
        assert isinstance(TOOL_LABELS, dict)
        assert 'internet_search' in TOOL_LABELS
    
    def test_import_block_types(self):
        """Test BlockType and DisplayBlock can be imported."""
        from praisonaiagents.output import BlockType, DisplayBlock
        assert BlockType.NARRATIVE.value == "narrative"
        assert BlockType.COMMAND.value == "command"


class TestEditorOutputBasic:
    """Test basic EditorOutput functionality."""
    
    def test_init_default(self):
        """Test default initialization."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        assert editor._step_count == 0
        assert editor._blocks == []
        assert editor._multi_agent_mode is False
    
    def test_init_with_agent_name(self):
        """Test initialization with agent name."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False, agent_name="TestAgent")
        assert editor._agent_name == "TestAgent"
    
    def test_elapsed_time(self):
        """Test elapsed time tracking."""
        from praisonaiagents.output.editor import EditorOutput
        import time
        editor = EditorOutput(use_rich=False)
        time.sleep(0.1)
        elapsed = editor.elapsed_time()
        assert elapsed >= 0.1


class TestToolCall:
    """Test tool_call method."""
    
    def test_tool_call_increments_step(self):
        """Test that tool_call increments step counter."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        
        editor.tool_call("test_tool")
        assert editor._step_count == 1
        
        editor.tool_call("test_tool")
        assert editor._step_count == 2
    
    def test_tool_call_with_known_tool(self):
        """Test tool_call with a known tool label."""
        from praisonaiagents.output.editor import EditorOutput, TOOL_LABELS
        editor = EditorOutput(use_rich=False)
        
        # internet_search should have a label
        assert 'internet_search' in TOOL_LABELS
        editor.tool_call("internet_search", args={"query": "test"})
        
        blocks = editor.get_blocks()
        assert len(blocks) == 1
        assert "Searching the web" in blocks[0].content
    
    def test_tool_call_with_unknown_tool(self):
        """Test tool_call with an unknown tool."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        
        editor.tool_call("my_custom_tool")
        blocks = editor.get_blocks()
        assert len(blocks) == 1
        assert "my_custom_tool" in blocks[0].content
    
    def test_tool_call_result_formatting(self):
        """Test that JSON results are formatted nicely."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        
        # Test list result
        editor.tool_call("test", result='[{"a": 1}, {"b": 2}]')
        blocks = editor.get_blocks()
        assert "Found 2 items" in blocks[0].output
    
    def test_tool_call_success_result(self):
        """Test success result formatting."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        
        editor.tool_call("test", result='{"success": true}')
        blocks = editor.get_blocks()
        assert "Success" in blocks[0].output


class TestMultiAgentPrefix:
    """Test multi-agent prefix support."""
    
    def test_no_prefix_by_default(self):
        """Test that no prefix is shown by default."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False, agent_name="Agent1")
        
        prefix = editor._get_prefix()
        assert prefix == ""
    
    def test_prefix_when_multi_agent_enabled(self):
        """Test prefix is shown when multi-agent mode is enabled."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False, agent_name="Agent1")
        editor.enable_multi_agent_mode()
        
        prefix = editor._get_prefix()
        assert prefix == "[Agent1] "
    
    def test_set_agent_name(self):
        """Test setting agent name."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        editor.set_agent_name("NewAgent")
        editor.enable_multi_agent_mode()
        
        prefix = editor._get_prefix()
        assert prefix == "[NewAgent] "
    
    def test_prefix_override(self):
        """Test prefix can be overridden per-call."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False, agent_name="Agent1")
        editor.enable_multi_agent_mode()
        
        prefix = editor._get_prefix("Agent2")
        assert prefix == "[Agent2] "


class TestAdditionalMethods:
    """Test additional display methods."""
    
    def test_narrative(self):
        """Test narrative method."""
        from praisonaiagents.output.editor import EditorOutput, BlockType
        editor = EditorOutput(use_rich=False)
        
        editor.narrative("This is a narrative block")
        blocks = editor.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == BlockType.NARRATIVE
        assert blocks[0].content == "This is a narrative block"
    
    def test_code(self):
        """Test code method."""
        from praisonaiagents.output.editor import EditorOutput, BlockType
        editor = EditorOutput(use_rich=False)
        
        editor.code("print('hello')", language="python")
        blocks = editor.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == BlockType.CODE
        assert blocks[0].metadata["language"] == "python"
    
    def test_action(self):
        """Test action method."""
        from praisonaiagents.output.editor import EditorOutput, BlockType
        editor = EditorOutput(use_rich=False)
        
        editor.action("File created", details=["path: /tmp/test.py"])
        blocks = editor.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == BlockType.ACTION
        assert blocks[0].title == "File created"
    
    def test_list_items(self):
        """Test list_items method."""
        from praisonaiagents.output.editor import EditorOutput, BlockType
        editor = EditorOutput(use_rich=False)
        
        editor.list_items(["Item 1", "Item 2"], title="My List")
        blocks = editor.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == BlockType.LIST
        assert blocks[0].items == ["Item 1", "Item 2"]
    
    def test_error(self):
        """Test error method."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        
        # Just verify it doesn't crash
        editor.error("Something went wrong")
    
    def test_summary(self):
        """Test summary method."""
        from praisonaiagents.output.editor import EditorOutput, BlockType
        editor = EditorOutput(use_rich=False)
        
        editor.summary("Completed", items=["Duration: 5s", "Steps: 3"])
        blocks = editor.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == BlockType.SUMMARY


class TestToMarkdown:
    """Test to_markdown export."""
    
    def test_to_markdown_empty(self):
        """Test to_markdown with no blocks."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        
        md = editor.to_markdown()
        assert md == ""
    
    def test_to_markdown_with_blocks(self):
        """Test to_markdown with various blocks."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        
        editor.narrative("Hello world")
        editor.tool_call("test_tool", result="Done")
        editor.summary("Complete", items=["Step 1"])
        
        md = editor.to_markdown()
        assert "Hello world" in md
        assert "Complete" in md
        assert "Step 1" in md


class TestThreadSafety:
    """Test thread safety of EditorOutput."""
    
    def test_concurrent_tool_calls(self):
        """Test that concurrent tool_call is thread-safe."""
        from praisonaiagents.output.editor import EditorOutput
        editor = EditorOutput(use_rich=False)
        
        def call_tool(n):
            for _ in range(10):
                editor.tool_call(f"tool_{n}")
        
        threads = [threading.Thread(target=call_tool, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have 50 steps total (5 threads * 10 calls)
        assert editor._step_count == 50
        assert len(editor.get_blocks()) == 50


class TestEnableDisable:
    """Test enable/disable functions."""
    
    def test_enable_returns_editor(self):
        """Test that enable_editor_output returns an EditorOutput instance."""
        from praisonaiagents.output.editor import enable_editor_output, disable_editor_output, EditorOutput
        
        editor = enable_editor_output(use_color=False)
        assert isinstance(editor, EditorOutput)
        
        disable_editor_output()
    
    def test_is_enabled(self):
        """Test is_editor_output_enabled function."""
        from praisonaiagents.output.editor import (
            enable_editor_output, disable_editor_output, is_editor_output_enabled
        )
        
        disable_editor_output()
        assert is_editor_output_enabled() is False
        
        enable_editor_output(use_color=False)
        assert is_editor_output_enabled() is True
        
        disable_editor_output()
        assert is_editor_output_enabled() is False
    
    def test_get_editor_output(self):
        """Test get_editor_output function."""
        from praisonaiagents.output.editor import (
            enable_editor_output, disable_editor_output, get_editor_output
        )
        
        disable_editor_output()
        assert get_editor_output() is None
        
        editor = enable_editor_output(use_color=False)
        assert get_editor_output() is editor
        
        disable_editor_output()

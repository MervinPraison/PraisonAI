"""
Unit tests for llm_content callback emission.

Verifies that the llm_content display event fires correctly for:
- Tool-call responses (intermediate narrative)
- Text-only responses (no tool calls)
- Empty response_text (no double-fire)
- Interaction callback already displayed (no duplicate)
"""

import pytest
from unittest.mock import patch, MagicMock, call


class TestLlmContentCallbackEmission:
    """Test that llm_content fires for all responses with text content."""

    def _make_response(self, content="Hello", tool_calls=None):
        """Build a mock LiteLLM response."""
        msg = {"content": content, "tool_calls": tool_calls}
        return {"choices": [{"message": msg}]}

    @patch('praisonaiagents.main.sync_display_callbacks', {})
    def test_llm_content_fires_with_text_and_tool_calls(self):
        """llm_content callback should fire for text with tool calls."""
        from praisonaiagents.output.editor import enable_editor_output, disable_editor_output, BlockType
        from praisonaiagents.main import sync_display_callbacks

        try:
            editor_output = enable_editor_output(use_color=False)

            # The callback should be registered
            assert 'llm_content' in sync_display_callbacks

            # Simulate what llm.py now does: emit llm_content for text
            callback = sync_display_callbacks['llm_content']
            callback(content="Let me check the weather for you.", agent_name="WeatherBot")

            # Verify narrative block was created
            narrative_blocks = [b for b in editor_output._blocks if b.type == BlockType.NARRATIVE]
            assert len(narrative_blocks) == 1
            assert "weather" in narrative_blocks[0].content.lower()
        finally:
            disable_editor_output()

    def test_narrative_method_renders_text(self):
        """EditorOutput.narrative() should add a NARRATIVE block."""
        from praisonaiagents.output.editor import EditorOutput, BlockType

        editor = EditorOutput(use_rich=False)
        editor.narrative("I'll search for the latest data.", agent_name="Researcher")

        # Check that a NARRATIVE block was added
        assert len(editor._blocks) == 1
        assert editor._blocks[0].type == BlockType.NARRATIVE

    def test_narrative_method_handles_empty(self):
        """EditorOutput.narrative() should not add block for empty content."""
        from praisonaiagents.output.editor import EditorOutput

        editor = EditorOutput(use_rich=False)
        editor.narrative("", agent_name="Test")
        editor.narrative("   ", agent_name="Test")

        # No blocks should be added for empty content
        assert len(editor._blocks) == 0

    def test_llm_content_callback_registration(self):
        """enable_editor_output should register llm_content callback."""
        from praisonaiagents.output.editor import enable_editor_output, disable_editor_output
        from praisonaiagents.main import sync_display_callbacks

        try:
            enable_editor_output(use_color=False)
            assert 'llm_content' in sync_display_callbacks
            callback = sync_display_callbacks['llm_content']
            assert callable(callback)
        finally:
            disable_editor_output()

    def test_llm_content_callback_calls_narrative(self):
        """The llm_content callback should call EditorOutput.narrative()."""
        from praisonaiagents.output.editor import enable_editor_output, disable_editor_output
        from praisonaiagents.main import sync_display_callbacks

        try:
            editor_output = enable_editor_output(use_color=False)
            callback = sync_display_callbacks['llm_content']

            # Call the callback with content
            callback(content="Analyzing the code structure", agent_name="CodeAgent")

            # Check a NARRATIVE block was added
            from praisonaiagents.output.editor import BlockType
            narrative_blocks = [b for b in editor_output._blocks if b.type == BlockType.NARRATIVE]
            assert len(narrative_blocks) == 1
        finally:
            disable_editor_output()

    def test_llm_content_callback_ignores_empty(self):
        """The llm_content callback should ignore empty content."""
        from praisonaiagents.output.editor import enable_editor_output, disable_editor_output
        from praisonaiagents.main import sync_display_callbacks

        try:
            editor_output = enable_editor_output(use_color=False)
            callback = sync_display_callbacks['llm_content']

            # Call with empty content
            callback(content="", agent_name="Test")
            callback(content=None, agent_name="Test")
            callback(content="   ", agent_name="Test")

            # No blocks added
            assert len(editor_output._blocks) == 0
        finally:
            disable_editor_output()

    def test_narrative_before_tool_calls(self):
        """Narrative should appear before tool call blocks in the block list."""
        from praisonaiagents.output.editor import EditorOutput, BlockType

        editor = EditorOutput(use_rich=False)

        # Simulate: LLM narrative first, then tool call
        editor.narrative("Let me search for that information.")
        editor.tool_call("internet_search", args={"query": "python 3.13"}, result="Found 5 results")

        assert len(editor._blocks) == 2
        assert editor._blocks[0].type == BlockType.NARRATIVE
        assert editor._blocks[1].type == BlockType.COMMAND

    def test_multiple_narrative_tool_groups(self):
        """Multiple narrative+tool groups should render in order."""
        from praisonaiagents.output.editor import EditorOutput, BlockType

        editor = EditorOutput(use_rich=False)

        # First group
        editor.narrative("I'll start by searching.")
        editor.tool_call("internet_search", args={"query": "topic A"}, result="3 results")

        # Second group
        editor.narrative("Now let me create the summary file.")
        editor.tool_call("write_file", args={"path": "/tmp/summary.md"}, result="File created")

        assert len(editor._blocks) == 4
        types = [b.type for b in editor._blocks]
        assert types == [BlockType.NARRATIVE, BlockType.COMMAND, BlockType.NARRATIVE, BlockType.COMMAND]


class TestLlmContentNoDoubleEmission:
    """Test that llm_content doesn't double-emit when interaction fires."""

    def test_interaction_callback_does_not_trigger_narrative(self):
        """After interaction callback fires, no narrative should duplicate."""
        from praisonaiagents.output.editor import enable_editor_output, disable_editor_output
        import praisonaiagents.main as _main

        # Save and clear callbacks to isolate from test pollution
        saved_sync = dict(_main.sync_display_callbacks)
        saved_async = dict(_main.async_display_callbacks)
        _main.sync_display_callbacks.clear()
        _main.async_display_callbacks.clear()

        try:
            editor_output = enable_editor_output(use_color=False)

            # Verify callbacks got registered
            assert 'llm_content' in _main.sync_display_callbacks, \
                f"llm_content not registered. Keys: {list(_main.sync_display_callbacks.keys())}"

            # Simulate: interaction fires first (final response)
            interaction_cb = _main.sync_display_callbacks.get('interaction')
            if interaction_cb:
                interaction_cb(
                    message="What is Python?",
                    response="Python is a programming language.",
                    agent_name="TestAgent",
                )

            # Then llm_content fires with same text
            llm_content_cb = _main.sync_display_callbacks['llm_content']
            llm_content_cb(content="Python is a programming language.", agent_name="TestAgent")

            from praisonaiagents.output.editor import BlockType
            narrative_blocks = [b for b in editor_output._blocks if b.type == BlockType.NARRATIVE]
            summary_blocks = [b for b in editor_output._blocks if b.type == BlockType.SUMMARY]

            # The deduplication logic should prevent llm_content from adding a narrative block
            # because the interaction callback already displayed the same text
            assert len(narrative_blocks) == 0, \
                f"Expected 0 NARRATIVE blocks due to deduplication, got {len(narrative_blocks)}"
        finally:
            disable_editor_output()
            # Restore original callbacks
            _main.sync_display_callbacks.clear()
            _main.sync_display_callbacks.update(saved_sync)
            _main.async_display_callbacks.clear()
            _main.async_display_callbacks.update(saved_async)

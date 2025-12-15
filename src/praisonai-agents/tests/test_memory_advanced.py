"""
Tests for advanced memory features:
- Session Save/Resume
- Context Compression
- Checkpointing
- Slash Commands
- Rules Manager
"""

import os
import sys
import pytest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from praisonaiagents.memory import FileMemory, RulesManager, Rule


class TestSessionManagement:
    """Tests for session save/resume functionality."""
    
    @pytest.fixture
    def memory(self, tmp_path):
        """Create a FileMemory instance with temp directory."""
        return FileMemory(user_id="test_user", base_path=str(tmp_path / "memory"))
    
    def test_save_session(self, memory):
        """Test saving a session."""
        # Add some memories
        memory.add_short_term("User prefers Python")
        memory.add_short_term("Working on AI project")
        memory.add_long_term("User name is John")
        
        # Save session
        path = memory.save_session("test_session")
        
        assert Path(path).exists()
        assert "test_session.json" in path
    
    def test_save_session_with_conversation(self, memory):
        """Test saving session with conversation history."""
        conversation = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        
        path = memory.save_session("conv_session", conversation_history=conversation)
        
        assert Path(path).exists()
    
    def test_resume_session(self, memory):
        """Test resuming a saved session."""
        # Add memories and save
        memory.add_short_term("Important context")
        memory.save_session("resume_test")
        
        # Clear and verify empty
        memory.clear_short_term()
        assert len(memory.get_short_term()) == 0
        
        # Resume session
        memory.resume_session("resume_test")
        
        # Verify restored
        assert len(memory.get_short_term()) > 0
        assert "Important context" in [m.content for m in memory.get_short_term()]
    
    def test_list_sessions(self, memory):
        """Test listing saved sessions."""
        memory.save_session("session1")
        memory.save_session("session2")
        
        sessions = memory.list_sessions()
        
        assert len(sessions) >= 2
        names = [s["name"] for s in sessions]
        assert "session1" in names
        assert "session2" in names
    
    def test_delete_session(self, memory):
        """Test deleting a session."""
        memory.save_session("to_delete")
        
        assert memory.delete_session("to_delete")
        
        sessions = memory.list_sessions()
        names = [s["name"] for s in sessions]
        assert "to_delete" not in names
    
    def test_resume_nonexistent_session(self, memory):
        """Test resuming a session that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            memory.resume_session("nonexistent")


class TestContextCompression:
    """Tests for context compression functionality."""
    
    @pytest.fixture
    def memory(self, tmp_path):
        """Create a FileMemory instance with temp directory."""
        return FileMemory(
            user_id="test_user",
            base_path=str(tmp_path / "memory"),
            config={"short_term_limit": 20}
        )
    
    def test_compress_basic(self, memory):
        """Test basic compression without LLM."""
        # Add many items
        for i in range(15):
            memory.add_short_term(f"Context item {i}")
        
        # Compress
        summary = memory.compress(max_items=5)
        
        # Verify compression
        assert len(memory.get_short_term()) <= 5
        assert len(summary) > 0
    
    def test_compress_with_llm_func(self, memory):
        """Test compression with custom LLM function."""
        for i in range(15):
            memory.add_short_term(f"Item {i}")
        
        # Mock LLM function
        def mock_llm(prompt):
            return "Summary: Multiple items discussed."
        
        summary = memory.compress(llm_func=mock_llm, max_items=5)
        
        assert "Summary:" in summary
    
    def test_auto_compress_below_threshold(self, memory):
        """Test auto-compress doesn't trigger below threshold."""
        # Add few items (below 70% of 20 = 14)
        for i in range(10):
            memory.add_short_term(f"Item {i}")
        
        result = memory.auto_compress_if_needed(threshold_percent=0.7)
        
        assert result is None
    
    def test_auto_compress_above_threshold(self, memory):
        """Test auto-compress triggers above threshold."""
        # Add many items (above 70% of 20 = 14)
        for i in range(16):
            memory.add_short_term(f"Item {i}")
        
        result = memory.auto_compress_if_needed(threshold_percent=0.7)
        
        assert result is not None or len(memory.get_short_term()) < 16


class TestCheckpointing:
    """Tests for checkpointing functionality."""
    
    @pytest.fixture
    def memory(self, tmp_path):
        """Create a FileMemory instance with temp directory."""
        return FileMemory(user_id="test_user", base_path=str(tmp_path / "memory"))
    
    def test_create_checkpoint(self, memory):
        """Test creating a checkpoint."""
        memory.add_short_term("Before checkpoint")
        memory.add_long_term("Important fact")
        
        checkpoint_id = memory.create_checkpoint("test_checkpoint")
        
        assert checkpoint_id == "test_checkpoint"
        checkpoints = memory.list_checkpoints()
        assert any(c["id"] == "test_checkpoint" for c in checkpoints)
    
    def test_create_checkpoint_auto_name(self, memory):
        """Test creating checkpoint with auto-generated name."""
        checkpoint_id = memory.create_checkpoint()
        
        assert checkpoint_id.startswith("checkpoint_")
    
    def test_restore_checkpoint(self, memory):
        """Test restoring from checkpoint."""
        # Add initial data
        memory.add_short_term("Original data")
        memory.create_checkpoint("restore_test")
        
        # Modify data
        memory.clear_short_term()
        memory.add_short_term("New data")
        
        # Restore
        success = memory.restore_checkpoint("restore_test")
        
        assert success
        contents = [m.content for m in memory.get_short_term()]
        assert "Original data" in contents
    
    def test_checkpoint_with_files(self, memory, tmp_path):
        """Test checkpoint with file snapshots."""
        # Create a test file
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("Original content")
        
        # Create checkpoint with file
        checkpoint_id = memory.create_checkpoint(
            "file_checkpoint",
            include_files=[str(test_file)]
        )
        
        # Modify file
        test_file.write_text("Modified content")
        
        # Restore with files
        memory.restore_checkpoint(checkpoint_id, restore_files=True)
        
        assert test_file.read_text() == "Original content"
    
    def test_list_checkpoints(self, memory):
        """Test listing checkpoints."""
        memory.create_checkpoint("cp1")
        memory.create_checkpoint("cp2")
        
        checkpoints = memory.list_checkpoints()
        
        assert len(checkpoints) >= 2
        ids = [c["id"] for c in checkpoints]
        assert "cp1" in ids
        assert "cp2" in ids
    
    def test_delete_checkpoint(self, memory):
        """Test deleting a checkpoint."""
        memory.create_checkpoint("to_delete")
        
        assert memory.delete_checkpoint("to_delete")
        
        checkpoints = memory.list_checkpoints()
        ids = [c["id"] for c in checkpoints]
        assert "to_delete" not in ids


class TestSlashCommands:
    """Tests for slash command handling."""
    
    @pytest.fixture
    def memory(self, tmp_path):
        """Create a FileMemory instance with temp directory."""
        return FileMemory(user_id="test_user", base_path=str(tmp_path / "memory"))
    
    def test_command_show(self, memory):
        """Test /memory show command."""
        memory.add_short_term("Test item")
        
        result = memory.handle_command("/memory show")
        
        assert result["action"] == "show"
        assert "stats" in result
        assert "short_term" in result
    
    def test_command_add(self, memory):
        """Test /memory add command."""
        result = memory.handle_command("/memory add User likes coffee")
        
        assert result["action"] == "add"
        assert result["content"] == "User likes coffee"
        
        # Verify it was added
        long_term = memory.get_long_term()
        assert any("coffee" in m.content for m in long_term)
    
    def test_command_clear(self, memory):
        """Test /memory clear command."""
        memory.add_short_term("To be cleared")
        
        result = memory.handle_command("/memory clear short")
        
        assert result["action"] == "clear"
        assert len(memory.get_short_term()) == 0
    
    def test_command_search(self, memory):
        """Test /memory search command."""
        memory.add_long_term("Python programming")
        
        result = memory.handle_command("/memory search Python")
        
        assert result["action"] == "search"
        assert "results" in result
    
    def test_command_save(self, memory):
        """Test /memory save command."""
        result = memory.handle_command("/memory save my_session")
        
        assert result["action"] == "save"
        assert result["session"] == "my_session"
    
    def test_command_sessions(self, memory):
        """Test /memory sessions command."""
        memory.save_session("test")
        
        result = memory.handle_command("/memory sessions")
        
        assert result["action"] == "sessions"
        assert "sessions" in result
    
    def test_command_checkpoint(self, memory):
        """Test /memory checkpoint command."""
        result = memory.handle_command("/memory checkpoint my_cp")
        
        assert result["action"] == "checkpoint"
        assert result["id"] == "my_cp"
    
    def test_command_checkpoints(self, memory):
        """Test /memory checkpoints command."""
        memory.create_checkpoint("test")
        
        result = memory.handle_command("/memory checkpoints")
        
        assert result["action"] == "checkpoints"
        assert "checkpoints" in result
    
    def test_command_help(self, memory):
        """Test /memory help command."""
        result = memory.handle_command("/memory help")
        
        assert result["action"] == "help"
        assert "commands" in result
        assert "/memory show" in result["commands"]
    
    def test_command_invalid(self, memory):
        """Test invalid command."""
        result = memory.handle_command("/memory invalid_action")
        
        assert "error" in result


class TestRulesManager:
    """Tests for RulesManager functionality."""
    
    @pytest.fixture
    def rules_dir(self, tmp_path):
        """Create a temp rules directory."""
        rules_path = tmp_path / ".praison" / "rules"
        rules_path.mkdir(parents=True)
        return rules_path
    
    @pytest.fixture
    def manager(self, tmp_path, rules_dir):
        """Create a RulesManager instance."""
        return RulesManager(workspace_path=str(tmp_path))
    
    def test_create_rule(self, manager, tmp_path):
        """Test creating a rule."""
        rule = manager.create_rule(
            name="python_style",
            content="# Python Style\n- Use type hints\n- Follow PEP 8",
            description="Python coding guidelines",
            globs=["**/*.py"],
            activation="glob"
        )
        
        assert rule.name == "python_style"
        assert rule.activation == "glob"
        assert "**/*.py" in rule.globs
        
        # Verify file was created
        rule_file = tmp_path / ".praison" / "rules" / "python_style.md"
        assert rule_file.exists()
    
    def test_load_rule_with_frontmatter(self, rules_dir, tmp_path):
        """Test loading a rule with YAML frontmatter."""
        rule_content = """---
description: Test rule
globs: ["*.py", "*.pyx"]
activation: glob
priority: 10
---

# Test Rule
- Rule content here
"""
        (rules_dir / "test_rule.md").write_text(rule_content)
        
        manager = RulesManager(workspace_path=str(tmp_path))
        rule = manager.get_rule_by_name("test_rule")
        
        assert rule is not None
        assert rule.description == "Test rule"
        assert "*.py" in rule.globs
        assert rule.activation == "glob"
        assert rule.priority == 10
    
    def test_get_active_rules_always(self, manager):
        """Test getting always-active rules."""
        manager.create_rule(
            name="always_rule",
            content="Always active",
            activation="always"
        )
        
        active = manager.get_active_rules()
        
        assert any(r.name == "always_rule" for r in active)
    
    def test_get_rules_for_file_glob(self, manager):
        """Test getting rules for a specific file."""
        manager.create_rule(
            name="py_rule",
            content="Python rule",
            globs=["**/*.py"],
            activation="glob"
        )
        manager.create_rule(
            name="js_rule",
            content="JS rule",
            globs=["**/*.js"],
            activation="glob"
        )
        
        py_rules = manager.get_rules_for_file("src/main.py")
        
        rule_names = [r.name for r in py_rules]
        assert "py_rule" in rule_names
        # js_rule should not match .py files
    
    def test_get_manual_rules(self, manager):
        """Test getting manual-only rules."""
        manager.create_rule(
            name="manual_rule",
            content="Manual only",
            activation="manual"
        )
        
        manual = manager.get_manual_rules()
        
        assert any(r.name == "manual_rule" for r in manual)
    
    def test_build_rules_context(self, manager):
        """Test building context string from rules."""
        manager.create_rule(
            name="rule1",
            content="Rule 1 content",
            description="First rule",
            activation="always"
        )
        manager.create_rule(
            name="rule2",
            content="Rule 2 content",
            description="Second rule",
            activation="always"
        )
        
        context = manager.build_rules_context()
        
        assert "rule1" in context
        assert "Rule 1 content" in context
    
    def test_build_rules_context_with_manual(self, manager):
        """Test building context with manual rules included."""
        manager.create_rule(
            name="auto_rule",
            content="Auto content",
            activation="always"
        )
        manager.create_rule(
            name="manual_rule",
            content="Manual content",
            activation="manual"
        )
        
        # Without manual
        context1 = manager.build_rules_context()
        assert "manual_rule" not in context1
        
        # With manual included
        context2 = manager.build_rules_context(include_manual=["manual_rule"])
        assert "Manual content" in context2
    
    def test_delete_rule(self, manager):
        """Test deleting a rule."""
        manager.create_rule(name="to_delete", content="Delete me")
        
        assert manager.delete_rule("to_delete")
        assert manager.get_rule_by_name("to_delete") is None
    
    def test_get_stats(self, manager):
        """Test getting rules statistics."""
        manager.create_rule(name="r1", content="c1", activation="always")
        manager.create_rule(name="r2", content="c2", activation="glob", globs=["*.py"])
        manager.create_rule(name="r3", content="c3", activation="manual")
        
        stats = manager.get_stats()
        
        assert stats["total_rules"] >= 3
        assert stats["always_rules"] >= 1
        assert stats["glob_rules"] >= 1
        assert stats["manual_rules"] >= 1
    
    def test_reload_rules(self, manager, rules_dir):
        """Test reloading rules from disk."""
        # Create rule via manager
        manager.create_rule(name="initial", content="Initial")
        
        # Create rule directly on disk
        new_rule = """---
description: New rule
activation: always
---
New rule content
"""
        (rules_dir / "new_rule.md").write_text(new_rule)
        
        # Reload
        manager.reload()
        
        # Should find new rule
        assert manager.get_rule_by_name("new_rule") is not None


class TestRuleMatching:
    """Tests for rule glob pattern matching."""
    
    def test_rule_matches_exact_glob(self):
        """Test exact glob matching."""
        rule = Rule(
            name="test",
            content="test",
            globs=["*.py"],
            activation="glob"
        )
        
        assert rule.matches_file("main.py")
        assert not rule.matches_file("main.js")
    
    def test_rule_matches_recursive_glob(self):
        """Test recursive glob matching."""
        rule = Rule(
            name="test",
            content="test",
            globs=["**/*.py"],
            activation="glob"
        )
        
        assert rule.matches_file("src/main.py")
        assert rule.matches_file("src/utils/helper.py")
    
    def test_rule_always_matches(self):
        """Test always activation mode."""
        rule = Rule(
            name="test",
            content="test",
            activation="always"
        )
        
        assert rule.matches_file("anything.txt")
        assert rule.matches_file("src/main.py")
    
    def test_rule_manual_never_matches(self):
        """Test manual activation mode never auto-matches."""
        rule = Rule(
            name="test",
            content="test",
            activation="manual"
        )
        
        assert not rule.matches_file("anything.txt")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

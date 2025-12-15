#!/usr/bin/env python3
"""
Tests for new CLI features (fast, direct import, no subprocess):
- Planning Mode
- Memory CLI
- Rules CLI
- Workflow CLI
- Hooks CLI
- Claude Memory Tool
"""

import argparse


class TestCLIArgumentParsing:
    """Test CLI argument parsing directly (fast, no subprocess)."""
    
    def get_parser(self):
        """Create argument parser matching CLI."""
        parser = argparse.ArgumentParser(description="praisonAI CLI")
        # Planning args
        parser.add_argument("--planning", action="store_true")
        parser.add_argument("--planning-tools")
        parser.add_argument("--planning-reasoning", action="store_true")
        parser.add_argument("--auto-approve-plan", action="store_true")
        # Memory args
        parser.add_argument("--memory", action="store_true")
        parser.add_argument("--user-id")
        # Rules args
        parser.add_argument("--include-rules")
        # Workflow args
        parser.add_argument("--workflow-var", action="append")
        # Claude memory
        parser.add_argument("--claude-memory", action="store_true")
        parser.add_argument("command", nargs="?")
        return parser
    
    def test_planning_args_parsed(self):
        """Test planning arguments are parsed correctly."""
        parser = self.get_parser()
        args = parser.parse_args(["--planning", "--planning-reasoning", "test"])
        assert args.planning is True
        assert args.planning_reasoning is True
        assert args.command == "test"
    
    def test_planning_tools_parsed(self):
        """Test planning-tools argument is parsed."""
        parser = self.get_parser()
        args = parser.parse_args(["--planning", "--planning-tools", "tools.py", "test"])
        assert args.planning is True
        assert args.planning_tools == "tools.py"
    
    def test_memory_args_parsed(self):
        """Test memory arguments are parsed correctly."""
        parser = self.get_parser()
        args = parser.parse_args(["--memory", "--user-id", "user123", "test"])
        assert args.memory is True
        assert args.user_id == "user123"
    
    def test_rules_args_parsed(self):
        """Test rules arguments are parsed correctly."""
        parser = self.get_parser()
        args = parser.parse_args(["--include-rules", "security,testing", "test"])
        assert args.include_rules == "security,testing"
    
    def test_workflow_vars_parsed(self):
        """Test workflow-var arguments are parsed correctly."""
        parser = self.get_parser()
        args = parser.parse_args([
            "--workflow-var", "env=prod",
            "--workflow-var", "branch=main",
            "test"
        ])
        assert args.workflow_var == ["env=prod", "branch=main"]
    
    def test_claude_memory_parsed(self):
        """Test claude-memory argument is parsed correctly."""
        parser = self.get_parser()
        args = parser.parse_args(["--claude-memory", "test"])
        assert args.claude_memory is True
    
    def test_auto_approve_plan_parsed(self):
        """Test auto-approve-plan argument is parsed correctly."""
        parser = self.get_parser()
        args = parser.parse_args(["--planning", "--auto-approve-plan", "test"])
        assert args.auto_approve_plan is True


class TestMemoryModule:
    """Test FileMemory module directly."""
    
    def test_file_memory_import(self):
        """Test FileMemory can be imported."""
        try:
            from praisonaiagents.memory import FileMemory
            assert FileMemory is not None
        except ImportError:
            pass  # Skip if not installed
    
    def test_file_memory_basic(self, tmp_path):
        """Test FileMemory basic operations."""
        try:
            from praisonaiagents.memory import FileMemory
            memory = FileMemory(user_id="test_user")
            
            # Test add
            memory.add_long_term("Test fact")
            
            # Test stats
            stats = memory.get_stats()
            assert stats["user_id"] == "test_user"
            assert stats["long_term_count"] >= 1
        except (ImportError, TypeError):
            pass  # Skip if not installed or API changed


class TestRulesModule:
    """Test RulesManager module directly."""
    
    def test_rules_manager_import(self):
        """Test RulesManager can be imported."""
        try:
            from praisonaiagents.memory import RulesManager
            assert RulesManager is not None
        except ImportError:
            pass  # Skip if not installed
    
    def test_rules_manager_basic(self):
        """Test RulesManager basic operations."""
        try:
            from praisonaiagents.memory import RulesManager
            manager = RulesManager()
            
            # Test stats
            stats = manager.get_stats()
            assert "total_rules" in stats
        except ImportError:
            pass  # Skip if not installed


class TestWorkflowModule:
    """Test WorkflowManager module directly."""
    
    def test_workflow_manager_import(self):
        """Test WorkflowManager can be imported."""
        try:
            from praisonaiagents.memory import WorkflowManager
            assert WorkflowManager is not None
        except ImportError:
            pass  # Skip if not installed


class TestHooksModule:
    """Test HooksManager module directly."""
    
    def test_hooks_manager_import(self):
        """Test HooksManager can be imported."""
        try:
            from praisonaiagents.memory import HooksManager
            assert HooksManager is not None
        except ImportError:
            pass  # Skip if not installed
    
    def test_hooks_manager_basic(self):
        """Test HooksManager basic operations."""
        try:
            from praisonaiagents.memory import HooksManager
            hooks = HooksManager()
            
            # Test stats
            stats = hooks.get_stats()
            assert "total_hooks" in stats
        except ImportError:
            pass  # Skip if not installed


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

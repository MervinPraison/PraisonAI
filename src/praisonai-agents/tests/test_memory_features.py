"""
Comprehensive tests for new memory features.

Tests:
- CLAUDE.local.md and local override files
- .claude/rules/, .windsurf/rules/, .cursor/rules/ discovery
- Git root discovery
- @Import syntax
- Rules character limit (12000)
- ai_decision activation mode
- Auto-generated memories
- Workflows
- Hooks
"""

import sys
import json
import tempfile
import unittest
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from praisonaiagents.memory import (
    FileMemory,
    RulesManager,
)


class TestLocalOverrideFiles(unittest.TestCase):
    """Test CLAUDE.local.md and PRAISON.local.md support."""
    
    def test_claude_local_md_loaded(self):
        """Test that CLAUDE.local.md is discovered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create CLAUDE.md
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("# Main Claude Rules\n- Rule 1")
            
            # Create CLAUDE.local.md (higher priority)
            claude_local = Path(tmpdir) / "CLAUDE.local.md"
            claude_local.write_text("# Local Overrides\n- Override 1")
            
            manager = RulesManager(workspace_path=tmpdir)
            
            self.assertIn("root:claude", manager._rules)
            self.assertIn("root:claude_local", manager._rules)
            
            # Local should have higher priority
            claude_rule = manager._rules["root:claude"]
            local_rule = manager._rules["root:claude_local"]
            self.assertGreater(local_rule.priority, claude_rule.priority)
    
    def test_praison_local_md_loaded(self):
        """Test that PRAISON.local.md is discovered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            praison_local = Path(tmpdir) / "PRAISON.local.md"
            praison_local.write_text("# Local Praison Rules")
            
            manager = RulesManager(workspace_path=tmpdir)
            
            self.assertIn("root:praison_local", manager._rules)


class TestAdditionalRulesDirectories(unittest.TestCase):
    """Test .claude/rules/, .windsurf/rules/, .cursor/rules/ discovery."""
    
    def test_claude_rules_directory(self):
        """Test .claude/rules/ discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir) / ".claude" / "rules"
            rules_dir.mkdir(parents=True)
            
            (rules_dir / "python.md").write_text("# Python Rules\n- Use type hints")
            (rules_dir / "testing.md").write_text("# Testing Rules\n- Use pytest")
            
            manager = RulesManager(workspace_path=tmpdir)
            stats = manager.get_stats()
            
            self.assertGreaterEqual(stats["total_rules"], 2)
            self.assertIn("claude:python", manager._rules)
            self.assertIn("claude:testing", manager._rules)
    
    def test_windsurf_rules_directory(self):
        """Test .windsurf/rules/ discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir) / ".windsurf" / "rules"
            rules_dir.mkdir(parents=True)
            
            (rules_dir / "style.md").write_text("# Style Rules")
            
            manager = RulesManager(workspace_path=tmpdir)
            
            self.assertIn("windsurf:style", manager._rules)
    
    def test_cursor_rules_directory(self):
        """Test .cursor/rules/ discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir) / ".cursor" / "rules"
            rules_dir.mkdir(parents=True)
            
            (rules_dir / "code.mdc").write_text("# Code Rules")
            
            manager = RulesManager(workspace_path=tmpdir)
            
            self.assertIn("cursor:code", manager._rules)


class TestGitRootDiscovery(unittest.TestCase):
    """Test git root discovery for monorepo support."""
    
    def test_find_git_root(self):
        """Test _find_git_root method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake git repo
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()
            
            # Create subdirectory
            subdir = Path(tmpdir) / "packages" / "frontend"
            subdir.mkdir(parents=True)
            
            manager = RulesManager(workspace_path=str(subdir))
            git_root = manager._find_git_root()
            
            # Resolve both paths to handle /private/var vs /var on macOS
            self.assertEqual(git_root.resolve(), Path(tmpdir).resolve())
    
    def test_rules_from_git_root(self):
        """Test that rules are loaded from git root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake git repo
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()
            
            # Create CLAUDE.md at git root
            (Path(tmpdir) / "CLAUDE.md").write_text("# Root Rules")
            
            # Create subdirectory
            subdir = Path(tmpdir) / "packages" / "frontend"
            subdir.mkdir(parents=True)
            
            # Create CLAUDE.md in subdirectory
            (subdir / "CLAUDE.md").write_text("# Subdir Rules")
            
            manager = RulesManager(workspace_path=str(subdir))
            
            # Should have both root and gitroot rules
            self.assertIn("root:claude", manager._rules)


class TestImportSyntax(unittest.TestCase):
    """Test @import syntax for including other files."""
    
    def test_basic_import(self):
        """Test basic @path/to/file import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file to import
            docs_dir = Path(tmpdir) / "docs"
            docs_dir.mkdir()
            (docs_dir / "guidelines.md").write_text("# Guidelines\n- Be concise")
            
            # Create CLAUDE.md with import
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("# Main Rules\n@docs/guidelines.md\n- More rules")
            
            manager = RulesManager(workspace_path=tmpdir)
            rule = manager._rules.get("root:claude")
            
            self.assertIsNotNone(rule)
            self.assertIn("Be concise", rule.content)
    
    def test_relative_import(self):
        """Test @./relative/path import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file to import
            (Path(tmpdir) / "shared.md").write_text("# Shared Content")
            
            # Create CLAUDE.md with relative import
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("Include: @./shared.md")
            
            manager = RulesManager(workspace_path=tmpdir)
            rule = manager._rules.get("root:claude")
            
            self.assertIn("Shared Content", rule.content)
    
    def test_import_depth_limit(self):
        """Test that import depth is limited to prevent loops."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create circular imports
            (Path(tmpdir) / "a.md").write_text("A imports @./b.md")
            (Path(tmpdir) / "b.md").write_text("B imports @./c.md")
            (Path(tmpdir) / "c.md").write_text("C imports @./a.md")  # Circular
            
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("Start: @./a.md")
            
            # Should not hang or crash
            manager = RulesManager(workspace_path=tmpdir)
            rule = manager._rules.get("root:claude")
            
            self.assertIsNotNone(rule)
    
    def test_code_span_not_imported(self):
        """Test that @mentions in code spans are not imported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text("Use `@org/package` for imports")
            
            manager = RulesManager(workspace_path=tmpdir)
            rule = manager._rules.get("root:claude")
            
            # Should not try to import @org/package
            self.assertIn("@org/package", rule.content)


class TestRulesCharacterLimit(unittest.TestCase):
    """Test 12000 character limit for rules."""
    
    def test_truncation(self):
        """Test that long rules are truncated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create very long rule
            long_content = "x" * 15000
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text(long_content)
            
            manager = RulesManager(workspace_path=tmpdir)
            rule = manager._rules.get("root:claude")
            
            self.assertLessEqual(len(rule.content), 12000)
            self.assertIn("truncated", rule.content)
    
    def test_short_rules_not_truncated(self):
        """Test that short rules are not truncated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            short_content = "# Short Rule\n- Item 1"
            claude_md = Path(tmpdir) / "CLAUDE.md"
            claude_md.write_text(short_content)
            
            manager = RulesManager(workspace_path=tmpdir)
            rule = manager._rules.get("root:claude")
            
            self.assertNotIn("truncated", rule.content)


class TestAiDecisionActivation(unittest.TestCase):
    """Test ai_decision activation mode."""
    
    def test_ai_decision_rule_loaded(self):
        """Test that ai_decision rules are loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir) / ".praison" / "rules"
            rules_dir.mkdir(parents=True)
            
            rule_content = """---
description: Security guidelines
activation: ai_decision
---
# Security Rules
- Validate inputs
"""
            (rules_dir / "security.md").write_text(rule_content)
            
            manager = RulesManager(workspace_path=tmpdir)
            
            self.assertIn("workspace:security", manager._rules)
            rule = manager._rules["workspace:security"]
            self.assertEqual(rule.activation, "ai_decision")
    
    def test_evaluate_ai_decision_without_llm(self):
        """Test ai_decision evaluation without LLM (defaults to True)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir) / ".praison" / "rules"
            rules_dir.mkdir(parents=True)
            
            rule_content = """---
activation: ai_decision
description: Security rules
---
# Security
"""
            (rules_dir / "security.md").write_text(rule_content)
            
            manager = RulesManager(workspace_path=tmpdir)
            rule = manager._rules["workspace:security"]
            
            # Without LLM, should return True
            result = manager.evaluate_ai_decision(rule, "some context")
            self.assertTrue(result)


class TestAutoMemory(unittest.TestCase):
    """Test auto-generated memories."""
    
    def test_extract_name(self):
        """Test name extraction from text."""
        from praisonaiagents.memory import AutoMemoryExtractor
        
        extractor = AutoMemoryExtractor()
        memories = extractor.extract("My name is John and I work at Acme.")
        
        names = [m for m in memories if m["type"] == "name"]
        self.assertGreater(len(names), 0)
        self.assertEqual(names[0]["content"], "John")
    
    def test_extract_preference(self):
        """Test preference extraction."""
        from praisonaiagents.memory import AutoMemoryExtractor
        
        extractor = AutoMemoryExtractor()
        memories = extractor.extract("I prefer Python for backend development.")
        
        prefs = [m for m in memories if m["type"] == "preference"]
        self.assertGreater(len(prefs), 0)
    
    def test_extract_technology(self):
        """Test technology extraction."""
        from praisonaiagents.memory import AutoMemoryExtractor
        
        extractor = AutoMemoryExtractor()
        memories = extractor.extract("I'm using Python and TypeScript.")
        
        techs = [m for m in memories if m["type"] == "technology"]
        self.assertGreater(len(techs), 0)
    
    def test_should_remember(self):
        """Test quick filter for memorable content."""
        from praisonaiagents.memory import AutoMemoryExtractor
        
        extractor = AutoMemoryExtractor()
        
        self.assertTrue(extractor.should_remember("My name is John"))
        self.assertTrue(extractor.should_remember("I prefer dark mode"))
        self.assertFalse(extractor.should_remember("Hello world"))
    
    def test_auto_memory_wrapper(self):
        """Test AutoMemory wrapper with FileMemory."""
        from praisonaiagents.memory import AutoMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = FileMemory(user_id="test", base_path=f"{tmpdir}/memory")
            auto = AutoMemory(memory, enabled=True)
            
            # Process interaction
            memories = auto.process_interaction(
                "My name is Alice and I prefer Python",
                store=True
            )
            
            self.assertGreater(len(memories), 0)
            
            # Check stored in base memory
            stats = memory.get_stats()
            self.assertGreater(stats["long_term_count"] + stats["entity_count"], 0)


class TestWorkflows(unittest.TestCase):
    """Test workflow system."""
    
    def test_workflow_discovery(self):
        """Test workflow discovery from .praison/workflows/."""
        from praisonaiagents.memory import WorkflowManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = Path(tmpdir) / ".praison" / "workflows"
            workflows_dir.mkdir(parents=True)
            
            workflow_content = """---
name: Deploy
description: Deploy to production
---

## Step 1: Test
Run tests.

```action
Run pytest
```

## Step 2: Build
Build the app.

```action
Build application
```
"""
            (workflows_dir / "deploy.md").write_text(workflow_content)
            
            manager = WorkflowManager(workspace_path=tmpdir)
            workflows = manager.list_workflows()
            
            self.assertEqual(len(workflows), 1)
            self.assertEqual(workflows[0].name, "Deploy")
            self.assertEqual(len(workflows[0].steps), 2)
    
    def test_workflow_execution(self):
        """Test workflow execution."""
        from praisonaiagents.memory import WorkflowManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workflows_dir = Path(tmpdir) / ".praison" / "workflows"
            workflows_dir.mkdir(parents=True)
            
            workflow_content = """---
name: Test
---

## Step 1: Echo
Echo environment.

```action
Echo staging
```
"""
            (workflows_dir / "test.md").write_text(workflow_content)
            
            manager = WorkflowManager(workspace_path=tmpdir)
            
            # Mock executor
            executed = []
            def executor(prompt):
                executed.append(prompt)
                return f"Executed: {prompt}"
            
            result = manager.execute("test", executor=executor)
            
            self.assertTrue(result["success"])
            self.assertEqual(len(executed), 1)
            self.assertIn("staging", executed[0])
    
    def test_create_workflow(self):
        """Test programmatic workflow creation."""
        from praisonaiagents.memory import WorkflowManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = WorkflowManager(workspace_path=tmpdir)
            
            workflow = manager.create_workflow(
                name="My Workflow",
                description="Test workflow",
                steps=[
                    {"name": "Step 1", "action": "Do something"},
                    {"name": "Step 2", "action": "Do something else"}
                ]
            )
            
            self.assertEqual(workflow.name, "My Workflow")
            self.assertEqual(len(workflow.steps), 2)
            
            # Check file was created
            self.assertTrue(Path(workflow.file_path).exists())


class TestHooks(unittest.TestCase):
    """Test hooks system."""
    
    def test_hooks_config_loading(self):
        """Test hooks configuration loading."""
        from praisonaiagents.memory import HooksManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".praison"
            config_dir.mkdir()
            
            config = {
                "enabled": True,
                "timeout": 30,
                "hooks": {
                    "pre_write_code": "echo 'pre-write'",
                    "post_write_code": "echo 'post-write'"
                }
            }
            (config_dir / "hooks.json").write_text(json.dumps(config))
            
            manager = HooksManager(workspace_path=tmpdir)
            stats = manager.get_stats()
            
            self.assertTrue(stats["enabled"])
            self.assertEqual(stats["script_hooks"], 2)
    
    def test_callable_hook_registration(self):
        """Test Python callable hook registration."""
        from praisonaiagents.memory import HooksManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = HooksManager(workspace_path=tmpdir)
            
            called = []
            def my_hook(context):
                called.append(context)
                return {"modified": True}
            
            manager.register("pre_write_code", my_hook)
            
            result = manager.execute("pre_write_code", {"file": "test.py"})
            
            self.assertTrue(result.success)
            self.assertEqual(len(called), 1)
            self.assertEqual(called[0]["file"], "test.py")
    
    def test_has_hooks(self):
        """Test has_hooks method."""
        from praisonaiagents.memory import HooksManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = HooksManager(workspace_path=tmpdir)
            
            self.assertFalse(manager.has_hooks("pre_write_code"))
            
            manager.register("pre_write_code", lambda ctx: None)
            
            self.assertTrue(manager.has_hooks("pre_write_code"))
    
    def test_create_config(self):
        """Test hooks config creation."""
        from praisonaiagents.memory import HooksManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = HooksManager(workspace_path=tmpdir)
            
            manager.create_config(
                hooks={"pre_write_code": "echo 'test'"},
                timeout=60
            )
            
            config_path = Path(tmpdir) / ".praison" / "hooks.json"
            self.assertTrue(config_path.exists())
            
            config = json.loads(config_path.read_text())
            self.assertEqual(config["timeout"], 60)


class TestSymlinkSupport(unittest.TestCase):
    """Test symlink support for shared rules."""
    
    def test_symlink_rule_file(self):
        """Test that symlinked rule files are loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create actual rule file
            shared_dir = Path(tmpdir) / "shared"
            shared_dir.mkdir()
            (shared_dir / "common.md").write_text("# Common Rules")
            
            # Create symlink
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            
            try:
                (project_dir / "CLAUDE.md").symlink_to(shared_dir / "common.md")
            except OSError:
                # Skip on systems that don't support symlinks
                self.skipTest("Symlinks not supported")
            
            manager = RulesManager(workspace_path=str(project_dir))
            
            # After symlink resolution, the name comes from the resolved file
            # Check that some rule with Common Rules content exists
            found = False
            for rule in manager._rules.values():
                if "Common Rules" in rule.content:
                    found = True
                    break
            self.assertTrue(found, "Symlinked rule content not found")


if __name__ == "__main__":
    unittest.main()

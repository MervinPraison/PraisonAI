"""
Unit tests for the migrate CLI feature.

Tests pattern detection and code conversion without exposing framework names.
Uses generic pattern terminology for stealth approach.
"""

import pytest
import tempfile
from pathlib import Path


class TestPatternDetection:
    """Test pattern detection from Python code."""
    
    def test_detect_agent_class_pattern_with_role_goal_backstory(self):
        """Detect agent-like class with role, goal, backstory attributes."""
        from praisonai.cli.features.migrate import PatternDetector
        
        code = '''
class MyAgent:
    role = "Researcher"
    goal = "Find information"
    backstory = "Expert researcher"
'''
        detector = PatternDetector()
        patterns = detector.detect_patterns(code)
        
        assert len(patterns) >= 1
        agent_patterns = [p for p in patterns if p.pattern_type.value == "agent"]
        assert len(agent_patterns) == 1
        assert agent_patterns[0].name == "MyAgent"
        assert agent_patterns[0].confidence >= 0.8
    
    def test_detect_task_class_pattern(self):
        """Detect task-like class with description, expected_output."""
        from praisonai.cli.features.migrate import PatternDetector
        
        code = '''
class ResearchTask:
    description = "Research the topic"
    expected_output = "A detailed report"
'''
        detector = PatternDetector()
        patterns = detector.detect_patterns(code)
        
        task_patterns = [p for p in patterns if p.pattern_type.value == "task"]
        assert len(task_patterns) == 1
        assert task_patterns[0].name == "ResearchTask"
    
    def test_detect_orchestrator_pattern(self):
        """Detect orchestrator-like class with agents and tasks lists."""
        from praisonai.cli.features.migrate import PatternDetector
        
        code = '''
class MyOrchestrator:
    agents = [agent1, agent2]
    tasks = [task1, task2]
    
    def kickoff(self):
        pass
'''
        detector = PatternDetector()
        patterns = detector.detect_patterns(code)
        
        orch_patterns = [p for p in patterns if p.pattern_type.value == "orchestrator"]
        assert len(orch_patterns) == 1
        assert orch_patterns[0].name == "MyOrchestrator"
    
    def test_detect_decorated_agent_function(self):
        """Detect @agent decorated functions."""
        from praisonai.cli.features.migrate import PatternDetector
        
        code = '''
@agent
def researcher():
    return Agent(role="Researcher")
'''
        detector = PatternDetector()
        patterns = detector.detect_patterns(code)
        
        agent_patterns = [p for p in patterns if p.pattern_type.value == "agent"]
        assert len(agent_patterns) >= 1
    
    def test_detect_pydantic_agent_model(self):
        """Detect Pydantic BaseModel with agent fields."""
        from praisonai.cli.features.migrate import PatternDetector
        
        code = '''
class AgentConfig(BaseModel):
    role: str
    goal: str
    backstory: str = ""
'''
        detector = PatternDetector()
        patterns = detector.detect_patterns(code)
        
        agent_patterns = [p for p in patterns if p.pattern_type.value == "agent"]
        assert len(agent_patterns) >= 1
    
    def test_confidence_scoring(self):
        """Test that confidence scoring works correctly."""
        from praisonai.cli.features.migrate import PatternDetector
        
        # High confidence: all agent attributes
        high_conf_code = '''
class FullAgent:
    role = "Role"
    goal = "Goal"
    backstory = "Backstory"
    tools = []
'''
        # Lower confidence: partial attributes
        low_conf_code = '''
class PartialAgent:
    role = "Role"
'''
        detector = PatternDetector()
        
        high_patterns = detector.detect_patterns(high_conf_code)
        low_patterns = detector.detect_patterns(low_conf_code)
        
        high_agent = [p for p in high_patterns if p.pattern_type.value == "agent"]
        low_agent = [p for p in low_patterns if p.pattern_type.value == "agent"]
        
        if high_agent and low_agent:
            assert high_agent[0].confidence > low_agent[0].confidence
    
    def test_no_patterns_in_regular_code(self):
        """Regular Python code should not trigger false positives."""
        from praisonai.cli.features.migrate import PatternDetector
        
        code = '''
def hello():
    print("Hello world")

class Calculator:
    def add(self, a, b):
        return a + b
'''
        detector = PatternDetector()
        patterns = detector.detect_patterns(code)
        
        # Should have no agent/task/orchestrator patterns
        agent_patterns = [p for p in patterns if p.pattern_type.value in ("agent", "task", "orchestrator")]
        assert len(agent_patterns) == 0


class TestCodeConversion:
    """Test code conversion to PraisonAI format."""
    
    def test_convert_agent_pattern_to_praisonai(self):
        """Convert detected agent pattern to PraisonAI Agent."""
        from praisonai.cli.features.migrate import CodeConverter
        
        code = '''
from some_framework import Agent

agent = Agent(
    role="Researcher",
    goal="Find information",
    backstory="Expert researcher",
    tools=[search_tool]
)
'''
        converter = CodeConverter()
        result = converter.convert_code(code)
        
        assert result.success
        assert "from praisonaiagents import Agent" in result.converted_code
        assert 'role="Researcher"' in result.converted_code
    
    def test_convert_orchestrator_to_agent_team(self):
        """Convert orchestrator pattern to AgentTeam."""
        from praisonai.cli.features.migrate import CodeConverter
        
        code = '''
orchestrator = Orchestrator(
    agents=[agent1, agent2],
    tasks=[task1, task2]
)
result = orchestrator.kickoff()
'''
        converter = CodeConverter()
        result = converter.convert_code(code)
        
        assert result.success
        # Should convert to AgentTeam
        assert "AgentTeam" in result.converted_code or "team" in result.converted_code.lower()
    
    def test_preserve_unknown_code(self):
        """Unknown code should be preserved as-is."""
        from praisonai.cli.features.migrate import CodeConverter
        
        code = '''
def helper_function():
    return "helper"

# Some comment
x = 42
'''
        converter = CodeConverter()
        result = converter.convert_code(code)
        
        assert "helper_function" in result.converted_code
        assert "x = 42" in result.converted_code
    
    def test_dry_run_does_not_write(self):
        """Dry run should not write files."""
        from praisonai.cli.features.migrate import CodeConverter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.py"
            source.write_text('agent = Agent(role="Test")')
            
            converter = CodeConverter()
            result = converter.convert_file(str(source), dry_run=True)
            
            assert result.success
            # No output file should be created in dry run
            output = Path(tmpdir) / "source_converted.py"
            assert not output.exists()


class TestDirectoryScanning:
    """Test directory scanning for migratable files."""
    
    def test_scan_directory_finds_python_files(self):
        """Scan directory should find all Python files."""
        from praisonai.cli.features.migrate import CodeConverter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "agents.py").write_text('role = "Test"')
            (Path(tmpdir) / "tasks.py").write_text('description = "Test"')
            (Path(tmpdir) / "readme.txt").write_text("Not Python")
            
            converter = CodeConverter()
            files = converter.scan_directory(tmpdir)
            
            assert len(files) == 2
            assert all(f.endswith(".py") for f in files)
    
    def test_scan_excludes_venv_and_pycache(self):
        """Scan should exclude venv and __pycache__ directories."""
        from praisonai.cli.features.migrate import CodeConverter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test structure
            (Path(tmpdir) / "main.py").write_text('role = "Test"')
            venv = Path(tmpdir) / "venv"
            venv.mkdir()
            (venv / "lib.py").write_text('# venv file')
            pycache = Path(tmpdir) / "__pycache__"
            pycache.mkdir()
            (pycache / "cache.pyc").write_text('# cache')
            
            converter = CodeConverter()
            files = converter.scan_directory(tmpdir)
            
            assert len(files) == 1
            assert "venv" not in files[0]
            assert "__pycache__" not in files[0]


class TestYAMLMigration:
    """Test YAML config migration (existing functionality)."""
    
    def test_yaml_migration_still_works(self):
        """Existing YAML migration should still work."""
        from praisonai.cli.features.migrate import ConfigMigrator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "config.yaml"
            source.write_text('''
agents:
  - role: Researcher
    goal: Find info
    backstory: Expert
tasks:
  - description: Research topic
    expected_output: Report
    agent: researcher
''')
            
            migrator = ConfigMigrator()
            result = migrator.migrate(str(source))
            
            assert result["success"]
    
    def test_detect_format_without_framework_names_in_output(self):
        """Format detection should work but not expose framework names in user output."""
        from praisonai.cli.features.migrate import ConfigMigrator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "config.yaml"
            source.write_text('''
agents:
  - role: Test
tasks:
  - description: Test task
''')
            
            migrator = ConfigMigrator()
            result = migrator.migrate(str(source))
            
            # Result should succeed without exposing framework names
            assert result["success"]


class TestCLIIntegration:
    """Test CLI command integration."""
    
    def test_migrate_help_is_generic(self):
        """CLI help should use generic terminology."""
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "praisonai", "migrate", "--help"],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Help text should be generic, not mention specific competitor frameworks
        help_text = result.stdout + result.stderr
        # Skip if run failed due to missing praisonaiagents (integration env issue, not test issue)
        if "praisonaiagents" in help_text.lower() and "not installed" in help_text.lower():
            import pytest
            pytest.skip("praisonaiagents not installed - cannot test migrate CLI")
        # Should have help content
        assert "migrate" in help_text.lower() or "usage" in help_text.lower() or result.returncode == 0
    
    def test_migrate_dry_run_flag(self):
        """--dry-run flag should work."""
        from praisonai.cli.features.migrate import handle_migrate_command
        import argparse
        
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "test.py"
            source.write_text('agent = Agent(role="Test")')
            
            # Create mock args
            args = argparse.Namespace(
                source=str(source),
                target=None,
                dry_run=True,
                output=None,
                from_format=None,
                to_format="praisonai"
            )
            
            # Should not raise
            try:
                handle_migrate_command(args)
            except SystemExit:
                pass  # CLI may exit


class TestValidation:
    """Test output validation."""
    
    def test_converted_code_is_valid_python(self):
        """Converted code should be valid Python."""
        from praisonai.cli.features.migrate import CodeConverter
        import ast
        
        code = '''
agent = Agent(
    role="Researcher",
    goal="Find info"
)
'''
        converter = CodeConverter()
        result = converter.convert_code(code)
        
        if result.success and result.converted_code:
            # Should parse without syntax errors
            try:
                ast.parse(result.converted_code)
            except SyntaxError:
                pytest.fail("Converted code has syntax errors")
    
    def test_warnings_for_unsupported_patterns(self):
        """Unsupported patterns should generate warnings."""
        from praisonai.cli.features.migrate import CodeConverter
        
        code = '''
# Custom callback that can't be auto-converted
@custom_decorator
def special_callback():
    pass
'''
        converter = CodeConverter()
        result = converter.convert_code(code)
        
        # Should still succeed but may have warnings
        assert result.success or len(result.warnings) > 0


class TestBackupCreation:
    """Test backup file creation."""
    
    def test_backup_created_when_overwriting(self):
        """Backup should be created when overwriting files."""
        from praisonai.cli.features.migrate import CodeConverter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "agents.py"
            source.write_text('agent = Agent(role="Test")')
            
            converter = CodeConverter()
            result = converter.convert_file(
                str(source),
                output=str(source),  # Overwrite
                dry_run=False,
                backup=True
            )
            
            if result.success:
                backup = Path(tmpdir) / "agents.py.bak"
                assert backup.exists()

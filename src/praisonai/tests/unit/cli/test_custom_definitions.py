"""
Tests for custom agent and command definitions discovery.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from praisonai.cli.features.custom_definitions import (
    CustomAgent,
    CustomCommand,
    CustomDefinitionsDiscovery,
    TemplateInterpolator,
    interpolate_command_template,
    load_agent_from_name,
)


class TestCustomDefinitionsDiscovery:
    """Test custom definitions discovery."""
    
    def test_parse_markdown_frontmatter(self):
        """Test parsing Markdown with YAML frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text("""---
model: gpt-4
role: Researcher
tools:
  - web_search
  - calculator
---

You are a helpful research assistant.
""")
            
            discovery = CustomDefinitionsDiscovery()
            frontmatter, body = discovery._parse_markdown_frontmatter(test_file)
            
            assert frontmatter["model"] == "gpt-4"
            assert frontmatter["role"] == "Researcher"
            assert "web_search" in frontmatter["tools"]
            assert body == "You are a helpful research assistant."
    
    def test_load_agent_from_yaml(self):
        """Test loading agent from YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            
            # Create test YAML agent
            agent_file = agents_dir / "researcher.yaml"
            agent_file.write_text("""
model: gpt-4
role: Research Specialist
goal: Find and analyze information
instructions: You are an expert researcher
tools:
  - web_search
  - file_reader
""")
            
            discovery = CustomDefinitionsDiscovery()
            agent = discovery._load_agent(agent_file, "test")
            
            assert agent is not None
            assert agent.name == "researcher"
            assert agent.model == "gpt-4"
            assert agent.role == "Research Specialist"
            assert agent.goal == "Find and analyze information"
            assert len(agent.tools) == 2
    
    def test_load_agent_from_markdown(self):
        """Test loading agent from Markdown file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            
            # Create test Markdown agent
            agent_file = agents_dir / "coder.md"
            agent_file.write_text("""---
model: gpt-4
role: Software Developer
goal: Write and review code
---

You are an expert software developer. Write clean, efficient code.
""")
            
            discovery = CustomDefinitionsDiscovery()
            agent = discovery._load_agent(agent_file, "test")
            
            assert agent is not None
            assert agent.name == "coder"
            assert agent.model == "gpt-4"
            assert agent.role == "Software Developer"
            assert "expert software developer" in agent.system_prompt
    
    def test_load_command(self):
        """Test loading command from Markdown file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            commands_dir = Path(tmpdir) / "commands"
            commands_dir.mkdir()
            
            # Create test command
            cmd_file = commands_dir / "summarize.md"
            cmd_file.write_text("""---
description: Summarize the provided text
---

Please summarize the following text concisely:

$ARGUMENTS
""")
            
            discovery = CustomDefinitionsDiscovery()
            command = discovery._load_command(cmd_file, "test")
            
            assert command is not None
            assert command.name == "summarize"
            assert command.description == "Summarize the provided text"
            assert "$ARGUMENTS" in command.template
    
    def test_discovery_precedence(self):
        """Test that project definitions override user definitions."""
        with tempfile.TemporaryDirectory() as user_dir, \
             tempfile.TemporaryDirectory() as project_dir:
            
            # Create user agent
            user_agents = Path(user_dir) / "agents"
            user_agents.mkdir()
            (user_agents / "test.yaml").write_text("model: gpt-3.5")
            
            # Create project agent (should override)
            project_agents = Path(project_dir) / "agents"
            project_agents.mkdir()
            (project_agents / "test.yaml").write_text("model: gpt-4")
            
            # Mock directory methods
            discovery = CustomDefinitionsDiscovery()
            with patch.object(discovery, '_get_user_dir', return_value=Path(user_dir)), \
                 patch.object(discovery, '_find_project_dirs', return_value=[Path(project_dir)]):
                
                discovery.discover()
                agent = discovery.get_agent("test")
                
                # Project should win
                assert agent is not None
                assert agent.model == "gpt-4"
                assert agent.source == "project"


class TestTemplateInterpolator:
    """Test template interpolation."""
    
    def test_arguments_interpolation(self):
        """Test $ARGUMENTS replacement."""
        template = "Process this: $ARGUMENTS"
        result = TemplateInterpolator.interpolate(template, "my input text")
        assert result == "Process this: my input text"
    
    def test_file_interpolation(self):
        """Test @file replacement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "data.txt"
            test_file.write_text("file contents")
            
            template = f"Data: @{test_file}"
            result = TemplateInterpolator.interpolate(template, working_dir=Path(tmpdir))
            assert result == "Data: file contents"
    
    def test_file_not_found(self):
        """Test @file with non-existent file."""
        template = "Data: @nonexistent.txt"
        result = TemplateInterpolator.interpolate(template)
        assert result == "Data: @nonexistent.txt"  # Should leave as-is
    
    def test_shell_substitution_escape(self):
        """Test escaping of shell command substitution."""
        template = "Run: $(dangerous command)"
        result = TemplateInterpolator.interpolate(template)
        assert result == "Run: \\$(dangerous command)"
    
    def test_complex_interpolation(self):
        """Test complex template with multiple patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "context.md"
            test_file.write_text("# Context\nImportant info")
            
            template = f"""Task: $ARGUMENTS

Context from file:
@{test_file}

Shell command: $(echo test)"""
            
            result = TemplateInterpolator.interpolate(
                template, 
                "Analyze this",
                working_dir=Path(tmpdir)
            )
            
            assert "Task: Analyze this" in result
            assert "# Context\nImportant info" in result
            assert "\\$(echo test)" in result


class TestIntegrationFunctions:
    """Test integration helper functions."""
    
    def test_load_agent_from_name(self):
        """Test loading agent configuration by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            
            # Create test agent
            (agents_dir / "helper.yaml").write_text("""
model: claude-3
role: Assistant
goal: Help users
""")
            
            discovery = CustomDefinitionsDiscovery()
            with patch.object(discovery, '_find_project_dirs', return_value=[Path(tmpdir)]):
                config = load_agent_from_name("helper")
                
                assert config is not None
                assert config["name"] == "helper"
                assert config["llm"] == "claude-3"
                assert config["role"] == "Assistant"
                assert config["goal"] == "Help users"
    
    def test_interpolate_command_template(self):
        """Test command template interpolation by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            commands_dir = Path(tmpdir) / "commands"
            commands_dir.mkdir()
            
            # Create test command
            (commands_dir / "greet.md").write_text("""---
description: Greeting command
---
Hello! $ARGUMENTS
""")
            
            discovery = CustomDefinitionsDiscovery()
            with patch.object(discovery, '_find_project_dirs', return_value=[Path(tmpdir)]):
                result = interpolate_command_template("greet", "How are you?")
                
                assert result == "Hello! How are you?"
    
    def test_command_not_found(self):
        """Test interpolating non-existent command."""
        result = interpolate_command_template("nonexistent", "args")
        assert result is None
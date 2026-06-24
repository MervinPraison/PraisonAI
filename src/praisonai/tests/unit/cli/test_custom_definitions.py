"""
Tests for custom agent and command definitions discovery.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from praisonai.cli.features.custom_definitions import (
    BUILTIN_PRESETS,
    CustomAgent,
    CustomCommand,
    CustomDefinitionsDiscovery,
    TemplateInterpolator,
    interpolate_command_template,
    load_agent_from_name,
    resolve_permission_config,
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


class TestPermissionResolution:
    """Test per-agent permission/mode resolution."""

    def test_mode_read_only_denies_mutations(self):
        """read-only mode denies edit/write/bash, allows read."""
        config = resolve_permission_config(mode="read-only")
        assert config["read:*"] == "allow"
        assert config["edit:*"] == "deny"
        assert config["write:*"] == "deny"
        assert config["bash:*"] == "deny"

    def test_review_mode_asks_before_bash(self):
        """review mode prompts (ask) before bash, never mutates files."""
        config = resolve_permission_config(mode="review")
        assert config["bash:*"] == "ask"
        assert config["edit:*"] == "deny"
        assert config["write:*"] == "deny"

    def test_unknown_mode_raises(self):
        """A typo'd mode fails closed instead of silently allowing everything."""
        with pytest.raises(ValueError):
            resolve_permission_config(mode="readonly")

    def test_invalid_action_raises(self):
        """An unknown permission action fails closed."""
        with pytest.raises(ValueError):
            resolve_permission_config(permission={"read": "maybe"})
        with pytest.raises(ValueError):
            resolve_permission_config(permission={"bash": {"git *": "sometimes"}})

    def test_action_normalised_case_insensitive(self):
        """Actions are normalised to lowercase."""
        config = resolve_permission_config(permission={"read": "ALLOW"})
        assert config["read:*"] == "allow"

    def test_mode_build_is_unrestricted(self):
        """build mode produces no restrictions."""
        assert resolve_permission_config(mode="build") is None

    def test_flat_permission_block(self):
        """Flat capability keys are normalised to glob patterns."""
        config = resolve_permission_config(permission={"read": "allow", "edit": "deny"})
        assert config["read:*"] == "allow"
        assert config["edit:*"] == "deny"

    def test_nested_permission_block(self):
        """Nested per-capability patterns are expanded."""
        config = resolve_permission_config(
            permission={"bash": {"git *": "ask", "*": "deny"}}
        )
        assert config["bash:git *"] == "ask"
        assert config["bash:*"] == "deny"

    def test_permission_overrides_mode(self):
        """Explicit permission rules override mode defaults."""
        config = resolve_permission_config(
            permission={"bash": "allow"}, mode="read-only"
        )
        # mode denies bash, but permission re-allows it
        assert config["bash:*"] == "allow"

    def test_empty_returns_none(self):
        """No mode and no permission yields None."""
        assert resolve_permission_config() is None


class TestPermissionDefinitionLoading:
    """Test that permission/mode are parsed from definitions."""

    def test_yaml_agent_parses_permission_and_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            (agents_dir / "reviewer.yaml").write_text("""
model: gpt-4o-mini
role: Reviewer
mode: read-only
permission:
  shell:
    "git *": ask
""")
            discovery = CustomDefinitionsDiscovery()
            agent = discovery._load_agent(agents_dir / "reviewer.yaml", "test")
            assert agent.mode == "read-only"
            assert agent.permission == {"shell": {"git *": "ask"}}

    def test_markdown_agent_parses_permission_and_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            (agents_dir / "reviewer.md").write_text("""---
model: gpt-4o-mini
mode: read-only
permission:
  read: allow
  edit: deny
---
You are a meticulous code reviewer.
""")
            discovery = CustomDefinitionsDiscovery()
            agent = discovery._load_agent(agents_dir / "reviewer.md", "test")
            assert agent.mode == "read-only"
            assert agent.permission["edit"] == "deny"

    def test_load_agent_from_name_includes_permissions(self):
        """A read-only agent gets a deny-by-default permission config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            (agents_dir / "reviewer.md").write_text("""---
model: gpt-4o-mini
mode: read-only
---
You are a reviewer.
""")
            with patch.object(
                CustomDefinitionsDiscovery, '_find_project_dirs', return_value=[Path(tmpdir)]
            ):
                config = load_agent_from_name("reviewer")
                assert config is not None
                assert "permissions" in config
                assert config["permissions"]["edit:*"] == "deny"
                assert config["permissions"]["bash:*"] == "deny"


class TestBuiltinPresets:
    """Test shipped, zero-config agent presets."""

    def test_builtin_presets_discoverable(self):
        """build/plan/review are discoverable with no YAML or flags."""
        discovery = CustomDefinitionsDiscovery()
        with patch.object(discovery, '_get_user_dir', return_value=Path("/nonexistent")), \
             patch.object(discovery, '_find_project_dirs', return_value=[]):
            discovery.discover(force=True)
            for name in ("build", "plan", "review"):
                agent = discovery.get_agent(name)
                assert agent is not None
                assert agent.source == "builtin"

    def test_plan_preset_is_read_only(self):
        """The plan preset is deny-by-default for mutating tools."""
        perms = resolve_permission_config(mode=BUILTIN_PRESETS["plan"]["mode"])
        assert perms["edit:*"] == "deny"
        assert perms["bash:*"] == "deny"

    def test_user_definition_overrides_builtin(self):
        """A user/project agent named 'plan' overrides the builtin preset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / "agents"
            agents_dir.mkdir()
            (agents_dir / "plan.yaml").write_text("model: custom-model\nmode: build\n")
            discovery = CustomDefinitionsDiscovery()
            with patch.object(discovery, '_get_user_dir', return_value=Path("/nonexistent")), \
                 patch.object(discovery, '_find_project_dirs', return_value=[Path(tmpdir)]):
                discovery.discover(force=True)
                agent = discovery.get_agent("plan")
                assert agent.source == "project"
                assert agent.model == "custom-model"


class TestRunCustomAgentPermissionMerge:
    """Test the runtime permission merge path in _run_custom_agent."""

    def _invoke(self, agent_permissions, invocation_permissions, approval=None):
        from praisonai.cli.commands import run as run_module

        captured = {}

        def fake_resolve_approval_config(backend_name, **kwargs):
            captured["backend_name"] = backend_name
            captured.update(kwargs)
            return object()

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                captured["agent_kwargs"] = kwargs

            def start(self, *args, **kwargs):
                return "ok"

        agent_config = {"instructions": "hi"}
        if agent_permissions is not None:
            agent_config["permissions"] = dict(agent_permissions)

        with patch(
            "praisonai.cli.features.approval.resolve_approval_config",
            side_effect=fake_resolve_approval_config,
        ), patch("praisonaiagents.Agent", FakeAgent):
            run_module._run_custom_agent(
                agent_config,
                "do something",
                model=None,
                verbose=False,
                approval=approval,
                invocation_permissions=invocation_permissions,
            )
        return captured

    def test_invocation_overrides_agent_permissions(self):
        """CLI --allow/--deny flags win over agent-definition permissions."""
        captured = self._invoke(
            agent_permissions={"bash:*": "deny", "read:*": "allow"},
            invocation_permissions={"bash:*": "allow"},
        )
        merged = captured["permissions_config"]
        assert merged["bash:*"] == "allow"  # invocation wins
        assert merged["read:*"] == "allow"  # agent default preserved

    def test_ask_rule_stays_interactive(self):
        """An ask rule keeps the backend interactive (non_interactive=False)."""
        captured = self._invoke(
            agent_permissions={"bash:*": "ask"},
            invocation_permissions=None,
        )
        assert captured["non_interactive"] is False

    def test_deny_only_is_non_interactive(self):
        """Deny-only configs default to non-interactive enforcement."""
        captured = self._invoke(
            agent_permissions={"bash:*": "deny"},
            invocation_permissions=None,
        )
        assert captured["non_interactive"] is True

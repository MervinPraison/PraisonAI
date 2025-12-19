"""
Tests for Slash Commands System.

Test-Driven Development approach:
1. Write tests first
2. Implement features to pass tests
3. Refactor while keeping tests green
"""

import pytest
from unittest.mock import MagicMock, patch
import time

from praisonai.cli.features.slash_commands import (
    SlashCommand,
    CommandContext,
    CommandKind,
    SlashCommandRegistry,
    SlashCommandParser,
    SlashCommandHandler,
    create_default_registry,
    cmd_help,
    cmd_cost,
    cmd_clear,
    cmd_model,
    cmd_tokens,
    cmd_plan,
    cmd_exit,
)


# ============================================================================
# SlashCommand Tests
# ============================================================================

class TestSlashCommand:
    """Tests for SlashCommand dataclass."""
    
    def test_create_basic_command(self):
        """Test creating a basic slash command."""
        cmd = SlashCommand(
            name="test",
            description="A test command"
        )
        assert cmd.name == "test"
        assert cmd.description == "A test command"
        assert cmd.action is None
        assert cmd.alt_names == []
        assert cmd.sub_commands == []
        assert cmd.kind == CommandKind.BUILT_IN
        assert cmd.auto_execute is True
    
    def test_create_command_with_action(self):
        """Test creating a command with an action."""
        def my_action(ctx, args):
            return {"result": "success"}
        
        cmd = SlashCommand(
            name="mycommand",
            description="My command",
            action=my_action
        )
        assert cmd.action is not None
        result = cmd.action(None, "")
        assert result == {"result": "success"}
    
    def test_create_command_with_aliases(self):
        """Test creating a command with aliases."""
        cmd = SlashCommand(
            name="help",
            description="Show help",
            alt_names=["h", "?"]
        )
        assert "h" in cmd.alt_names
        assert "?" in cmd.alt_names
    
    def test_create_command_with_subcommands(self):
        """Test creating a command with sub-commands."""
        sub1 = SlashCommand(name="sub1", description="Sub 1")
        sub2 = SlashCommand(name="sub2", description="Sub 2")
        
        cmd = SlashCommand(
            name="parent",
            description="Parent command",
            sub_commands=[sub1, sub2]
        )
        assert len(cmd.sub_commands) == 2
        assert cmd.sub_commands[0].name == "sub1"
    
    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Command name cannot be empty"):
            SlashCommand(name="", description="Empty name")
    
    def test_command_kinds(self):
        """Test different command kinds."""
        builtin = SlashCommand(name="builtin", description="Built-in", kind=CommandKind.BUILT_IN)
        custom = SlashCommand(name="custom", description="Custom", kind=CommandKind.CUSTOM)
        mcp = SlashCommand(name="mcp", description="MCP", kind=CommandKind.MCP)
        
        assert builtin.kind == CommandKind.BUILT_IN
        assert custom.kind == CommandKind.CUSTOM
        assert mcp.kind == CommandKind.MCP


# ============================================================================
# CommandContext Tests
# ============================================================================

class TestCommandContext:
    """Tests for CommandContext dataclass."""
    
    def test_create_default_context(self):
        """Test creating a default context."""
        ctx = CommandContext()
        assert ctx.agent is None
        assert ctx.config == {}
        assert ctx.session_id is None
        assert ctx.total_tokens == 0
        assert ctx.total_cost == 0.0
        assert ctx.prompt_count == 0
    
    def test_context_with_metrics(self):
        """Test context with metrics."""
        ctx = CommandContext(
            total_tokens=1500,
            total_cost=0.0045,
            prompt_count=3
        )
        assert ctx.total_tokens == 1500
        assert ctx.total_cost == 0.0045
        assert ctx.prompt_count == 3
    
    def test_context_with_session(self):
        """Test context with session info."""
        start_time = time.time()
        ctx = CommandContext(
            session_id="test-session-123",
            session_start_time=start_time
        )
        assert ctx.session_id == "test-session-123"
        assert ctx.session_start_time == start_time


# ============================================================================
# SlashCommandRegistry Tests
# ============================================================================

class TestSlashCommandRegistry:
    """Tests for SlashCommandRegistry."""
    
    def test_register_command(self):
        """Test registering a command."""
        registry = SlashCommandRegistry()
        cmd = SlashCommand(name="test", description="Test")
        
        registry.register(cmd)
        
        assert registry.get("test") is not None
        assert registry.get("test").name == "test"
    
    def test_register_command_with_aliases(self):
        """Test registering a command with aliases."""
        registry = SlashCommandRegistry()
        cmd = SlashCommand(
            name="help",
            description="Help",
            alt_names=["h", "?"]
        )
        
        registry.register(cmd)
        
        # Should be accessible by name and aliases
        assert registry.get("help") is not None
        assert registry.get("h") is not None
        assert registry.get("?") is not None
        
        # All should return the same command
        assert registry.get("help") == registry.get("h")
        assert registry.get("h") == registry.get("?")
    
    def test_get_nonexistent_command(self):
        """Test getting a non-existent command."""
        registry = SlashCommandRegistry()
        assert registry.get("nonexistent") is None
    
    def test_unregister_command(self):
        """Test unregistering a command."""
        registry = SlashCommandRegistry()
        cmd = SlashCommand(name="test", description="Test", alt_names=["t"])
        
        registry.register(cmd)
        assert registry.get("test") is not None
        
        result = registry.unregister("test")
        assert result is True
        assert registry.get("test") is None
        assert registry.get("t") is None  # Alias should also be removed
    
    def test_unregister_nonexistent(self):
        """Test unregistering a non-existent command."""
        registry = SlashCommandRegistry()
        result = registry.unregister("nonexistent")
        assert result is False
    
    def test_get_all_commands(self):
        """Test getting all commands."""
        registry = SlashCommandRegistry()
        registry.register(SlashCommand(name="cmd1", description="Cmd 1"))
        registry.register(SlashCommand(name="cmd2", description="Cmd 2"))
        registry.register(SlashCommand(name="cmd3", description="Cmd 3"))
        
        all_cmds = registry.get_all()
        assert len(all_cmds) == 3
        names = [cmd.name for cmd in all_cmds]
        assert "cmd1" in names
        assert "cmd2" in names
        assert "cmd3" in names
    
    def test_get_names(self):
        """Test getting all command names including aliases."""
        registry = SlashCommandRegistry()
        registry.register(SlashCommand(name="help", description="Help", alt_names=["h"]))
        registry.register(SlashCommand(name="exit", description="Exit", alt_names=["q", "quit"]))
        
        names = registry.get_names()
        assert "help" in names
        assert "h" in names
        assert "exit" in names
        assert "q" in names
        assert "quit" in names


# ============================================================================
# SlashCommandParser Tests
# ============================================================================

class TestSlashCommandParser:
    """Tests for SlashCommandParser."""
    
    @pytest.fixture
    def parser(self):
        """Create a parser with test commands."""
        registry = SlashCommandRegistry()
        registry.register(SlashCommand(name="help", description="Help", alt_names=["h"]))
        registry.register(SlashCommand(name="cost", description="Cost"))
        registry.register(SlashCommand(
            name="memory",
            description="Memory",
            sub_commands=[
                SlashCommand(name="add", description="Add memory"),
                SlashCommand(name="list", description="List memories"),
            ]
        ))
        return SlashCommandParser(registry)
    
    def test_is_slash_command(self, parser):
        """Test slash command detection."""
        assert parser.is_slash_command("/help") is True
        assert parser.is_slash_command("/cost") is True
        assert parser.is_slash_command("help") is False
        assert parser.is_slash_command("") is False
    
    def test_is_not_code_comment(self, parser):
        """Test that code comments are not detected as commands."""
        assert parser.is_slash_command("// This is a comment") is False
        assert parser.is_slash_command("/* Block comment */") is False
    
    def test_parse_simple_command(self, parser):
        """Test parsing a simple command."""
        result = parser.parse("/help")
        
        assert result.command is not None
        assert result.command.name == "help"
        assert result.args == ""
        assert result.canonical_path == ["help"]
        assert result.error is None
    
    def test_parse_command_with_args(self, parser):
        """Test parsing a command with arguments."""
        result = parser.parse("/help model")
        
        assert result.command is not None
        assert result.command.name == "help"
        assert result.args == "model"
    
    def test_parse_command_by_alias(self, parser):
        """Test parsing a command by alias."""
        result = parser.parse("/h")
        
        assert result.command is not None
        assert result.command.name == "help"
    
    def test_parse_subcommand(self, parser):
        """Test parsing a sub-command."""
        result = parser.parse("/memory add some data")
        
        assert result.command is not None
        assert result.command.name == "add"
        assert result.args == "some data"
        assert result.canonical_path == ["memory", "add"]
    
    def test_parse_unknown_command(self, parser):
        """Test parsing an unknown command."""
        result = parser.parse("/unknown")
        
        assert result.command is None
        assert result.canonical_path == []
    
    def test_parse_empty_command(self, parser):
        """Test parsing empty command."""
        result = parser.parse("/")
        
        assert result.error == "Empty command"
    
    def test_parse_not_slash_command(self, parser):
        """Test parsing non-slash command."""
        result = parser.parse("regular text")
        
        assert result.error == "Not a slash command"


# ============================================================================
# Built-in Command Tests
# ============================================================================

class TestBuiltinCommands:
    """Tests for built-in commands."""
    
    @pytest.fixture
    def context(self):
        """Create a test context."""
        ctx = CommandContext(
            total_tokens=1000,
            total_cost=0.003,
            prompt_count=5,
            session_start_time=time.time() - 120  # 2 minutes ago
        )
        ctx.config["command_registry"] = create_default_registry()
        return ctx
    
    def test_cmd_help_general(self, context):
        """Test general help command."""
        with patch('rich.console.Console.print'):
            result = cmd_help(context, "")
        
        assert result["type"] == "help"
    
    def test_cmd_help_specific(self, context):
        """Test help for specific command."""
        with patch('rich.console.Console.print'):
            result = cmd_help(context, "cost")
        
        assert result["type"] == "help"
        assert result["command"] == "cost"
    
    def test_cmd_help_unknown(self, context):
        """Test help for unknown command."""
        with patch('rich.console.Console.print'):
            result = cmd_help(context, "unknown_cmd")
        
        assert result["type"] == "error"
    
    def test_cmd_cost(self, context):
        """Test cost command."""
        with patch('rich.console.Console.print'):
            result = cmd_cost(context, "")
        
        assert result["type"] == "stats"
        assert result["tokens"] == 1000
        assert result["cost"] == 0.003
        assert result["prompts"] == 5
    
    def test_cmd_clear(self, context):
        """Test clear command."""
        mock_agent = MagicMock()
        context.agent = mock_agent
        
        with patch('rich.console.Console.print'):
            result = cmd_clear(context, "")
        
        assert result["type"] == "clear"
        mock_agent.clear_history.assert_called_once()
    
    def test_cmd_model_show(self, context):
        """Test model command without args (show current)."""
        mock_agent = MagicMock()
        mock_agent.llm = MagicMock(model="gpt-4o")
        context.agent = mock_agent
        
        with patch('rich.console.Console.print'):
            result = cmd_model(context, "")
        
        assert result["type"] == "model_info"
        assert result["model"] == "gpt-4o"
    
    def test_cmd_model_change(self, context):
        """Test model command with args (change model)."""
        mock_agent = MagicMock()
        context.agent = mock_agent
        
        with patch('rich.console.Console.print'):
            result = cmd_model(context, "gpt-4o-mini")
        
        assert result["type"] == "model_change"
        assert result["model"] == "gpt-4o-mini"
    
    def test_cmd_tokens(self, context):
        """Test tokens command."""
        with patch('rich.console.Console.print'):
            result = cmd_tokens(context, "")
        
        assert result["type"] == "tokens"
        assert result["total"] == 1000
    
    def test_cmd_plan_with_args(self, context):
        """Test plan command with task."""
        with patch('rich.console.Console.print'):
            result = cmd_plan(context, "build a REST API")
        
        assert result["type"] == "submit_prompt"
        assert "build a REST API" in result["content"]
    
    def test_cmd_plan_without_args(self, context):
        """Test plan command without task."""
        with patch('rich.console.Console.print'):
            result = cmd_plan(context, "")
        
        assert result["type"] == "help"
    
    def test_cmd_exit(self, context):
        """Test exit command."""
        with patch('rich.console.Console.print'):
            result = cmd_exit(context, "")
        
        assert result["type"] == "exit"


# ============================================================================
# SlashCommandHandler Tests
# ============================================================================

class TestSlashCommandHandler:
    """Tests for SlashCommandHandler."""
    
    def test_handler_creation(self):
        """Test handler creation."""
        handler = SlashCommandHandler()
        assert handler.registry is not None
        assert handler.parser is not None
    
    def test_is_command(self):
        """Test command detection."""
        handler = SlashCommandHandler()
        
        assert handler.is_command("/help") is True
        assert handler.is_command("/cost") is True
        assert handler.is_command("regular text") is False
    
    def test_execute_help(self):
        """Test executing help command."""
        handler = SlashCommandHandler()
        
        with patch('rich.console.Console.print'):
            result = handler.execute("/help")
        
        assert result is not None
        assert result["type"] == "help"
    
    def test_execute_unknown_command(self):
        """Test executing unknown command."""
        handler = SlashCommandHandler()
        
        result = handler.execute("/unknown_command_xyz")
        
        assert result is not None
        assert result["type"] == "error"
    
    def test_execute_non_command(self):
        """Test executing non-command text."""
        handler = SlashCommandHandler()
        
        result = handler.execute("regular text")
        
        assert result is None
    
    def test_register_custom_command(self):
        """Test registering a custom command."""
        handler = SlashCommandHandler()
        
        def custom_action(ctx, args):
            return {"type": "custom", "args": args}
        
        handler.register_command(SlashCommand(
            name="custom",
            description="Custom command",
            action=custom_action
        ))
        
        result = handler.execute("/custom test args")
        
        assert result is not None
        assert result["type"] == "custom"
        assert result["args"] == "test args"
    
    def test_get_completions(self):
        """Test command completions."""
        handler = SlashCommandHandler()
        
        completions = handler.get_completions("/he")
        assert "/help" in completions
        
        completions = handler.get_completions("/co")
        assert "/cost" in completions
        assert "/commit" in completions
        
        completions = handler.get_completions("regular")
        assert completions == []
    
    def test_set_context(self):
        """Test setting context."""
        handler = SlashCommandHandler()
        ctx = CommandContext(total_tokens=500)
        
        handler.set_context(ctx)
        
        assert handler._context is ctx
        assert "command_registry" in ctx.config


# ============================================================================
# Default Registry Tests
# ============================================================================

class TestDefaultRegistry:
    """Tests for default command registry."""
    
    def test_default_registry_has_core_commands(self):
        """Test that default registry has core commands."""
        registry = create_default_registry()
        
        # Core commands should exist
        assert registry.get("help") is not None
        assert registry.get("cost") is not None
        assert registry.get("clear") is not None
        assert registry.get("model") is not None
        assert registry.get("tokens") is not None
        assert registry.get("plan") is not None
        assert registry.get("exit") is not None
    
    def test_default_registry_aliases(self):
        """Test that default registry has aliases."""
        registry = create_default_registry()
        
        # Help aliases
        assert registry.get("h") is not None
        assert registry.get("?") is not None
        
        # Exit aliases
        assert registry.get("q") is not None
        assert registry.get("quit") is not None
        
        # Cost aliases
        assert registry.get("usage") is not None
        assert registry.get("stats") is not None


# ============================================================================
# Integration Tests (require real execution)
# ============================================================================

class TestSlashCommandsIntegration:
    """Integration tests for slash commands."""
    
    def test_full_command_flow(self):
        """Test full command execution flow."""
        handler = SlashCommandHandler(verbose=True)
        
        # Set up context
        ctx = CommandContext(
            total_tokens=2500,
            total_cost=0.0075,
            prompt_count=10,
            session_start_time=time.time() - 300
        )
        handler.set_context(ctx)
        
        # Execute commands
        with patch('rich.console.Console.print'):
            help_result = handler.execute("/help")
            cost_result = handler.execute("/cost")
            tokens_result = handler.execute("/tokens")
        
        assert help_result["type"] == "help"
        assert cost_result["type"] == "stats"
        assert cost_result["tokens"] == 2500
        assert tokens_result["type"] == "tokens"
    
    def test_command_with_special_characters(self):
        """Test commands with special characters in args."""
        handler = SlashCommandHandler()
        
        with patch('rich.console.Console.print'):
            result = handler.execute("/plan Build a REST API with /users endpoint")
        
        assert result is not None
        assert result["type"] == "submit_prompt"
        assert "/users" in result["content"]

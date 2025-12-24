"""
Unit tests for the Hooks module.

Tests cover:
- HookRegistry registration and lookup
- HookRunner execution (function and command hooks)
- Event types and inputs
- Decision handling (allow, deny, block)
"""

import pytest
import asyncio
import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

# Import hook types
from praisonaiagents.hooks.types import (
    HookEvent, HookResult, HookInput, HookOutput,
    HookDefinition, CommandHook, FunctionHook, HookExecutionResult
)
from praisonaiagents.hooks.events import (
    BeforeToolInput, AfterToolInput, BeforeAgentInput,
    AfterAgentInput, SessionStartInput, SessionEndInput
)
from praisonaiagents.hooks.registry import HookRegistry, get_default_registry
from praisonaiagents.hooks.runner import HookRunner


# =============================================================================
# HookResult Tests
# =============================================================================

class TestHookResult:
    """Tests for HookResult class."""
    
    def test_allow_result(self):
        """Test creating an allow result."""
        result = HookResult.allow("Allowed by policy")
        assert result.decision == "allow"
        assert result.reason == "Allowed by policy"
        assert result.is_allowed()
        assert not result.is_denied()
    
    def test_deny_result(self):
        """Test creating a deny result."""
        result = HookResult.deny("Blocked by policy")
        assert result.decision == "deny"
        assert result.reason == "Blocked by policy"
        assert not result.is_allowed()
        assert result.is_denied()
    
    def test_block_result(self):
        """Test creating a block result."""
        result = HookResult.block("Security violation")
        assert result.decision == "block"
        assert result.reason == "Security violation"
        assert result.is_denied()
    
    def test_ask_result(self):
        """Test creating an ask result."""
        result = HookResult.ask("Requires confirmation")
        assert result.decision == "ask"
        assert result.reason == "Requires confirmation"
    
    def test_default_result(self):
        """Test default result is allow."""
        result = HookResult()
        assert result.decision == "allow"
        assert result.is_allowed()


# =============================================================================
# HookDefinition Tests
# =============================================================================

class TestHookDefinition:
    """Tests for HookDefinition class."""
    
    def test_definition_creation(self):
        """Test creating a hook definition."""
        hook = HookDefinition(
            event=HookEvent.BEFORE_TOOL,
            name="test_hook",
            matcher="write_*"
        )
        assert hook.event == HookEvent.BEFORE_TOOL
        assert hook.name == "test_hook"
        assert hook.matcher == "write_*"
        assert hook.enabled
    
    def test_matcher_regex(self):
        """Test regex matching."""
        hook = HookDefinition(matcher="write_.*")
        assert hook.matches("write_file")
        assert hook.matches("write_data")
        assert not hook.matches("read_file")
    
    def test_matcher_none(self):
        """Test that None matcher matches everything."""
        hook = HookDefinition(matcher=None)
        assert hook.matches("anything")
        assert hook.matches("write_file")
    
    def test_command_hook(self):
        """Test CommandHook creation."""
        hook = CommandHook(
            event=HookEvent.BEFORE_TOOL,
            command="python validator.py",
            env={"API_KEY": "test"}
        )
        assert hook.command == "python validator.py"
        assert hook.env == {"API_KEY": "test"}
        assert hook.shell
    
    def test_function_hook(self):
        """Test FunctionHook creation."""
        def my_hook(data):
            return HookResult.allow()
        
        hook = FunctionHook(
            event=HookEvent.BEFORE_TOOL,
            func=my_hook
        )
        assert hook.func == my_hook
        assert hook.name == "my_hook"


# =============================================================================
# HookRegistry Tests
# =============================================================================

class TestHookRegistry:
    """Tests for HookRegistry class."""
    
    def test_registry_creation(self):
        """Test creating a registry."""
        registry = HookRegistry()
        assert registry.enabled
        assert len(registry) == 0
    
    def test_register_function(self):
        """Test registering a function hook."""
        registry = HookRegistry()
        
        def my_hook(data):
            return HookResult.allow()
        
        hook_id = registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=my_hook,
            name="my_hook"
        )
        
        assert hook_id is not None
        assert len(registry) == 1
        
        hooks = registry.get_hooks(HookEvent.BEFORE_TOOL)
        assert len(hooks) == 1
        assert hooks[0].name == "my_hook"
    
    def test_register_command(self):
        """Test registering a command hook."""
        registry = HookRegistry()
        
        hook_id = registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command="python validator.py",
            name="validator"
        )
        
        assert hook_id is not None
        hooks = registry.get_hooks(HookEvent.BEFORE_TOOL)
        assert len(hooks) == 1
        assert isinstance(hooks[0], CommandHook)
    
    def test_decorator_registration(self):
        """Test decorator-based registration."""
        registry = HookRegistry()
        
        @registry.on(HookEvent.BEFORE_TOOL)
        def validate_tool(data):
            return HookResult.allow()
        
        hooks = registry.get_hooks(HookEvent.BEFORE_TOOL)
        assert len(hooks) == 1
        assert hooks[0].name == "validate_tool"
    
    def test_unregister(self):
        """Test unregistering a hook."""
        registry = HookRegistry()
        
        hook_id = registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command="echo test"
        )
        
        assert len(registry) == 1
        assert registry.unregister(hook_id)
        assert len(registry) == 0
    
    def test_get_hooks_with_matcher(self):
        """Test getting hooks filtered by target."""
        registry = HookRegistry()
        
        registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=lambda d: HookResult.allow(),
            matcher="write_.*",
            name="write_hook"
        )
        
        registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=lambda d: HookResult.allow(),
            matcher="read_.*",
            name="read_hook"
        )
        
        write_hooks = registry.get_hooks(HookEvent.BEFORE_TOOL, "write_file")
        assert len(write_hooks) == 1
        assert write_hooks[0].name == "write_hook"
        
        read_hooks = registry.get_hooks(HookEvent.BEFORE_TOOL, "read_file")
        assert len(read_hooks) == 1
        assert read_hooks[0].name == "read_hook"
    
    def test_disable_enable_hook(self):
        """Test disabling and enabling hooks."""
        registry = HookRegistry()
        
        hook_id = registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command="echo test"
        )
        
        assert len(registry.get_hooks(HookEvent.BEFORE_TOOL)) == 1
        
        registry.disable_hook(hook_id)
        assert len(registry.get_hooks(HookEvent.BEFORE_TOOL)) == 0
        
        registry.enable_hook(hook_id)
        assert len(registry.get_hooks(HookEvent.BEFORE_TOOL)) == 1
    
    def test_clear_hooks(self):
        """Test clearing hooks."""
        registry = HookRegistry()
        
        registry.register_command(HookEvent.BEFORE_TOOL, "echo 1")
        registry.register_command(HookEvent.AFTER_TOOL, "echo 2")
        
        assert len(registry) == 2
        
        registry.clear(HookEvent.BEFORE_TOOL)
        assert len(registry) == 1
        
        registry.clear()
        assert len(registry) == 0
    
    def test_list_hooks(self):
        """Test listing all hooks."""
        registry = HookRegistry()
        
        registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command="echo test",
            name="test_hook"
        )
        
        hooks_list = registry.list_hooks()
        assert "before_tool" in hooks_list
        assert len(hooks_list["before_tool"]) == 1
        assert hooks_list["before_tool"][0]["name"] == "test_hook"


# =============================================================================
# Event Input Tests
# =============================================================================

class TestEventInputs:
    """Tests for event-specific input classes."""
    
    def test_before_tool_input(self):
        """Test BeforeToolInput."""
        input_data = BeforeToolInput(
            session_id="test-session",
            cwd="/tmp",
            event_name="before_tool",
            timestamp="2024-01-01T00:00:00",
            tool_name="write_file",
            tool_input={"path": "/tmp/test.txt", "content": "hello"}
        )
        
        assert input_data.tool_name == "write_file"
        assert input_data.tool_input["path"] == "/tmp/test.txt"
        
        data_dict = input_data.to_dict()
        assert data_dict["tool_name"] == "write_file"
    
    def test_after_tool_input(self):
        """Test AfterToolInput."""
        input_data = AfterToolInput(
            session_id="test-session",
            cwd="/tmp",
            event_name="after_tool",
            timestamp="2024-01-01T00:00:00",
            tool_name="write_file",
            tool_output="File written successfully",
            execution_time_ms=100.5
        )
        
        assert input_data.tool_output == "File written successfully"
        assert input_data.execution_time_ms == 100.5
    
    def test_before_agent_input(self):
        """Test BeforeAgentInput."""
        input_data = BeforeAgentInput(
            session_id="test-session",
            cwd="/tmp",
            event_name="before_agent",
            timestamp="2024-01-01T00:00:00",
            prompt="Write a file",
            tools_available=["write_file", "read_file"]
        )
        
        assert input_data.prompt == "Write a file"
        assert "write_file" in input_data.tools_available
    
    def test_session_start_input(self):
        """Test SessionStartInput."""
        input_data = SessionStartInput(
            session_id="test-session",
            cwd="/tmp",
            event_name="session_start",
            timestamp="2024-01-01T00:00:00",
            source="startup"
        )
        
        assert input_data.source == "startup"


# =============================================================================
# HookRunner Tests
# =============================================================================

class TestHookRunner:
    """Tests for HookRunner class."""
    
    def _create_sample_input(self):
        """Create sample input data."""
        return BeforeToolInput(
            session_id="test-session",
            cwd="/tmp",
            event_name="before_tool",
            timestamp="2024-01-01T00:00:00",
            tool_name="write_file",
            tool_input={"path": "/tmp/test.txt"}
        )
    
    @pytest.mark.asyncio
    async def test_execute_function_hook_allow(self):
        """Test executing a function hook that allows."""
        registry = HookRegistry()
        
        def allow_hook(data):
            return HookResult.allow("Allowed")
        
        registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=allow_hook
        )
        
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert results[0].success
        assert results[0].output.is_allowed()
    
    @pytest.mark.asyncio
    async def test_execute_function_hook_deny(self):
        """Test executing a function hook that denies."""
        registry = HookRegistry()
        
        def deny_hook(data):
            return HookResult.deny("Not allowed")
        
        registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=deny_hook
        )
        
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert results[0].success
        assert results[0].output.is_denied()
        assert HookRunner.is_blocked(results)
    
    @pytest.mark.asyncio
    async def test_execute_async_function_hook(self):
        """Test executing an async function hook."""
        registry = HookRegistry()
        
        async def async_hook(data):
            await asyncio.sleep(0.01)
            return HookResult.allow("Async allowed")
        
        registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=async_hook,
            is_async=True
        )
        
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert results[0].success
    
    @pytest.mark.asyncio
    async def test_execute_multiple_hooks_parallel(self):
        """Test executing multiple hooks in parallel."""
        registry = HookRegistry()
        call_order = []
        
        def hook1(data):
            call_order.append(1)
            return HookResult.allow()
        
        def hook2(data):
            call_order.append(2)
            return HookResult.allow()
        
        registry.register_function(HookEvent.BEFORE_TOOL, hook1, sequential=False)
        registry.register_function(HookEvent.BEFORE_TOOL, hook2, sequential=False)
        
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 2
        assert all(r.success for r in results)
    
    @pytest.mark.asyncio
    async def test_execute_sequential_hooks(self):
        """Test executing hooks sequentially."""
        registry = HookRegistry()
        call_order = []
        
        def hook1(data):
            call_order.append(1)
            return HookResult.allow()
        
        def hook2(data):
            call_order.append(2)
            return HookResult.allow()
        
        registry.register_function(HookEvent.BEFORE_TOOL, hook1, sequential=True)
        registry.register_function(HookEvent.BEFORE_TOOL, hook2, sequential=True)
        
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 2
        assert call_order == [1, 2]
    
    @pytest.mark.asyncio
    async def test_sequential_stops_on_deny(self):
        """Test that sequential execution stops on deny."""
        registry = HookRegistry()
        call_order = []
        
        def hook1(data):
            call_order.append(1)
            return HookResult.deny("Blocked")
        
        def hook2(data):
            call_order.append(2)
            return HookResult.allow()
        
        registry.register_function(HookEvent.BEFORE_TOOL, hook1, sequential=True)
        registry.register_function(HookEvent.BEFORE_TOOL, hook2, sequential=True)
        
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1  # Only first hook executed
        assert call_order == [1]
        assert HookRunner.is_blocked(results)
    
    @pytest.mark.asyncio
    async def test_hook_timeout(self):
        """Test hook timeout handling."""
        registry = HookRegistry()
        
        async def slow_hook(data):
            await asyncio.sleep(10)  # Very slow
            return HookResult.allow()
        
        registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=slow_hook,
            is_async=True,
            timeout=0.1  # 100ms timeout
        )
        
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert not results[0].success
        assert "timed out" in results[0].error
    
    @pytest.mark.asyncio
    async def test_hook_exception_handling(self):
        """Test hook exception handling."""
        registry = HookRegistry()
        
        def failing_hook(data):
            raise ValueError("Hook failed")
        
        registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=failing_hook
        )
        
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert not results[0].success
        assert "Hook failed" in results[0].error
    
    @pytest.mark.asyncio
    async def test_no_hooks_returns_empty(self):
        """Test that no hooks returns empty list."""
        registry = HookRegistry()
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        assert results == []
    
    @pytest.mark.asyncio
    async def test_disabled_registry(self):
        """Test that disabled registry returns no hooks."""
        registry = HookRegistry()
        registry.register_function(
            event=HookEvent.BEFORE_TOOL,
            func=lambda d: HookResult.allow()
        )
        
        registry.enabled = False
        runner = HookRunner(registry)
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert results == []
    
    def test_is_blocked_helper(self):
        """Test is_blocked helper method."""
        allow_result = HookExecutionResult(
            hook_id="1",
            hook_name="test",
            event=HookEvent.BEFORE_TOOL,
            success=True,
            output=HookResult.allow()
        )
        
        deny_result = HookExecutionResult(
            hook_id="2",
            hook_name="test",
            event=HookEvent.BEFORE_TOOL,
            success=True,
            output=HookResult.deny("Blocked")
        )
        
        assert not HookRunner.is_blocked([allow_result])
        assert HookRunner.is_blocked([deny_result])
        assert HookRunner.is_blocked([allow_result, deny_result])
    
    def test_get_blocking_reason(self):
        """Test get_blocking_reason helper method."""
        deny_result = HookExecutionResult(
            hook_id="1",
            hook_name="test",
            event=HookEvent.BEFORE_TOOL,
            success=True,
            output=HookResult.deny("Security violation")
        )
        
        reason = HookRunner.get_blocking_reason([deny_result])
        assert reason == "Security violation"
    
    def test_aggregate_context(self):
        """Test aggregate_context helper method."""
        result1 = HookExecutionResult(
            hook_id="1",
            hook_name="test1",
            event=HookEvent.BEFORE_TOOL,
            success=True,
            output=HookResult(additional_context="Context 1")
        )
        
        result2 = HookExecutionResult(
            hook_id="2",
            hook_name="test2",
            event=HookEvent.BEFORE_TOOL,
            success=True,
            output=HookResult(additional_context="Context 2")
        )
        
        context = HookRunner.aggregate_context([result1, result2])
        assert "Context 1" in context
        assert "Context 2" in context


# =============================================================================
# Command Hook Tests
# =============================================================================

class TestCommandHooks:
    """Tests for command hook execution."""
    
    def _create_sample_input(self):
        return BeforeToolInput(
            session_id="test-session",
            cwd="/tmp",
            event_name="before_tool",
            timestamp="2024-01-01T00:00:00",
            tool_name="write_file",
            tool_input={"path": "/tmp/test.txt"}
        )
    
    @pytest.mark.asyncio
    async def test_command_hook_success(self):
        """Test successful command hook execution."""
        registry = HookRegistry()
        registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command='echo \'{"decision": "allow"}\'',
            name="allow_hook"
        )
        
        runner = HookRunner(registry, cwd="/tmp")
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert results[0].success
        assert results[0].output.decision == "allow"
    
    @pytest.mark.asyncio
    async def test_command_hook_deny(self):
        """Test command hook that denies."""
        registry = HookRegistry()
        registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command='echo \'{"decision": "deny", "reason": "Blocked"}\''
        )
        
        runner = HookRunner(registry, cwd="/tmp")
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert results[0].output.decision == "deny"
        assert results[0].output.reason == "Blocked"
    
    @pytest.mark.asyncio
    async def test_command_hook_exit_code_2(self):
        """Test command hook with blocking exit code."""
        registry = HookRegistry()
        registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command="exit 2"
        )
        
        runner = HookRunner(registry, cwd="/tmp")
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert results[0].exit_code == 2
        assert results[0].output.decision == "deny"
    
    @pytest.mark.asyncio
    async def test_command_hook_timeout(self):
        """Test command hook timeout."""
        registry = HookRegistry()
        registry.register_command(
            event=HookEvent.BEFORE_TOOL,
            command="sleep 10",
            timeout=0.1
        )
        
        runner = HookRunner(registry, cwd="/tmp")
        sample_input = self._create_sample_input()
        results = await runner.execute(HookEvent.BEFORE_TOOL, sample_input)
        
        assert len(results) == 1
        assert not results[0].success
        assert "timed out" in results[0].error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

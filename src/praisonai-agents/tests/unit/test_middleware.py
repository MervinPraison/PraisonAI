"""
TDD Tests for Middleware System (wrap_model_call, wrap_tool_call).

These tests are written FIRST before implementation.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from dataclasses import dataclass
from typing import Any, Dict, Optional


class TestMiddlewareTypes:
    """Test middleware type definitions."""
    
    def test_invocation_context_exists(self):
        """InvocationContext dataclass should exist with required fields."""
        from praisonaiagents.hooks.middleware import InvocationContext
        
        ctx = InvocationContext(
            agent_id="agent-123",
            run_id="run-456",
            session_id="session-789"
        )
        assert ctx.agent_id == "agent-123"
        assert ctx.run_id == "run-456"
        assert ctx.session_id == "session-789"
    
    def test_invocation_context_optional_fields(self):
        """InvocationContext should have optional tool_name, model_name, metadata."""
        from praisonaiagents.hooks.middleware import InvocationContext
        
        ctx = InvocationContext(
            agent_id="a",
            run_id="r",
            session_id="s",
            tool_name="my_tool",
            model_name="gpt-4o",
            metadata={"key": "value"}
        )
        assert ctx.tool_name == "my_tool"
        assert ctx.model_name == "gpt-4o"
        assert ctx.metadata == {"key": "value"}
    
    def test_model_request_exists(self):
        """ModelRequest dataclass for before_model hooks."""
        from praisonaiagents.hooks.middleware import ModelRequest
        
        req = ModelRequest(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4o",
            temperature=0.7,
            context=Mock()
        )
        assert req.messages == [{"role": "user", "content": "Hello"}]
        assert req.model == "gpt-4o"
        assert req.temperature == 0.7
    
    def test_model_response_exists(self):
        """ModelResponse dataclass for after_model hooks."""
        from praisonaiagents.hooks.middleware import ModelResponse
        
        resp = ModelResponse(
            content="Hello back!",
            model="gpt-4o",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            context=Mock()
        )
        assert resp.content == "Hello back!"
        assert resp.model == "gpt-4o"
    
    def test_tool_request_exists(self):
        """ToolRequest dataclass for before_tool hooks."""
        from praisonaiagents.hooks.middleware import ToolRequest
        
        req = ToolRequest(
            tool_name="get_weather",
            arguments={"city": "Paris"},
            context=Mock()
        )
        assert req.tool_name == "get_weather"
        assert req.arguments == {"city": "Paris"}
    
    def test_tool_response_exists(self):
        """ToolResponse dataclass for after_tool hooks."""
        from praisonaiagents.hooks.middleware import ToolResponse
        
        resp = ToolResponse(
            tool_name="get_weather",
            result="Sunny, 22°C",
            error=None,
            context=Mock()
        )
        assert resp.result == "Sunny, 22°C"
        assert resp.error is None


class TestMiddlewareDecorators:
    """Test middleware decorator functions."""
    
    def test_before_model_decorator_exists(self):
        """before_model decorator should exist and tag functions."""
        from praisonaiagents.hooks import before_model
        
        @before_model
        def my_hook(request):
            return request
        
        assert hasattr(my_hook, '_hook_type')
        assert my_hook._hook_type == 'before_model'
    
    def test_after_model_decorator_exists(self):
        """after_model decorator should exist and tag functions."""
        from praisonaiagents.hooks import after_model
        
        @after_model
        def my_hook(response):
            return response
        
        assert hasattr(my_hook, '_hook_type')
        assert my_hook._hook_type == 'after_model'
    
    def test_wrap_model_call_decorator_exists(self):
        """wrap_model_call decorator should exist and tag functions."""
        from praisonaiagents.hooks import wrap_model_call
        
        @wrap_model_call
        def my_middleware(request, call_next):
            return call_next(request)
        
        assert hasattr(my_middleware, '_hook_type')
        assert my_middleware._hook_type == 'wrap_model_call'
    
    def test_before_tool_decorator_exists(self):
        """before_tool decorator should exist and tag functions."""
        from praisonaiagents.hooks import before_tool
        
        @before_tool
        def my_hook(request):
            return request
        
        assert hasattr(my_hook, '_hook_type')
        assert my_hook._hook_type == 'before_tool'
    
    def test_after_tool_decorator_exists(self):
        """after_tool decorator should exist and tag functions."""
        from praisonaiagents.hooks import after_tool
        
        @after_tool
        def my_hook(response):
            return response
        
        assert hasattr(my_hook, '_hook_type')
        assert my_hook._hook_type == 'after_tool'
    
    def test_wrap_tool_call_decorator_exists(self):
        """wrap_tool_call decorator should exist and tag functions."""
        from praisonaiagents.hooks import wrap_tool_call
        
        @wrap_tool_call
        def my_middleware(request, call_next):
            return call_next(request)
        
        assert hasattr(my_middleware, '_hook_type')
        assert my_middleware._hook_type == 'wrap_tool_call'


class TestMiddlewareChaining:
    """Test middleware chain composition."""
    
    def test_wrap_model_call_chain_order(self):
        """wrap_model_call hooks should compose in registration order."""
        from praisonaiagents.hooks.middleware import MiddlewareChain
        
        calls = []
        
        def mw1(req, call_next):
            calls.append("mw1_before")
            result = call_next(req)
            calls.append("mw1_after")
            return result
        
        def mw2(req, call_next):
            calls.append("mw2_before")
            result = call_next(req)
            calls.append("mw2_after")
            return result
        
        def final_handler(req):
            calls.append("final")
            return "response"
        
        chain = MiddlewareChain([mw1, mw2])
        result = chain.execute({"test": True}, final_handler)
        
        assert calls == ["mw1_before", "mw2_before", "final", "mw2_after", "mw1_after"]
        assert result == "response"
    
    def test_empty_middleware_chain(self):
        """Empty middleware chain should just call final handler."""
        from praisonaiagents.hooks.middleware import MiddlewareChain
        
        def final_handler(req):
            return "direct"
        
        chain = MiddlewareChain([])
        result = chain.execute({"test": True}, final_handler)
        assert result == "direct"
    
    def test_middleware_can_modify_request(self):
        """Middleware should be able to modify request before passing on."""
        from praisonaiagents.hooks.middleware import MiddlewareChain
        
        def add_context(req, call_next):
            req["extra"] = "added"
            return call_next(req)
        
        def final_handler(req):
            return req.get("extra")
        
        chain = MiddlewareChain([add_context])
        result = chain.execute({"original": True}, final_handler)
        assert result == "added"
    
    def test_middleware_can_modify_response(self):
        """Middleware should be able to modify response after call_next."""
        from praisonaiagents.hooks.middleware import MiddlewareChain
        
        def uppercase_response(req, call_next):
            result = call_next(req)
            return result.upper()
        
        def final_handler(req):
            return "hello"
        
        chain = MiddlewareChain([uppercase_response])
        result = chain.execute({}, final_handler)
        assert result == "HELLO"
    
    def test_middleware_can_short_circuit(self):
        """Middleware can return early without calling call_next."""
        from praisonaiagents.hooks.middleware import MiddlewareChain
        
        def block_middleware(req, call_next):
            if req.get("block"):
                return "blocked"
            return call_next(req)
        
        def final_handler(req):
            return "reached"
        
        chain = MiddlewareChain([block_middleware])
        
        # Should be blocked
        result = chain.execute({"block": True}, final_handler)
        assert result == "blocked"
        
        # Should pass through
        result = chain.execute({"block": False}, final_handler)
        assert result == "reached"


class TestMiddlewareRetry:
    """Test retry logic in middleware."""
    
    def test_wrap_tool_call_retry_on_error(self):
        """wrap_tool_call should support retry patterns."""
        from praisonaiagents.hooks.middleware import MiddlewareChain
        
        attempt_count = [0]
        
        def retry_middleware(req, call_next):
            last_error = None
            for i in range(3):
                try:
                    return call_next(req)
                except Exception as e:
                    last_error = e
            raise last_error
        
        def flaky_handler(req):
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise RuntimeError("flaky")
            return "success"
        
        chain = MiddlewareChain([retry_middleware])
        result = chain.execute({}, flaky_handler)
        assert result == "success"
        assert attempt_count[0] == 3


class TestAsyncMiddleware:
    """Test async middleware support."""
    
    @pytest.mark.asyncio
    async def test_async_wrap_model_call(self):
        """Async middleware should work with async handlers."""
        from praisonaiagents.hooks.middleware import AsyncMiddlewareChain
        
        calls = []
        
        async def async_mw(req, call_next):
            calls.append("before")
            result = await call_next(req)
            calls.append("after")
            return result
        
        async def async_handler(req):
            calls.append("handler")
            return "async_result"
        
        chain = AsyncMiddlewareChain([async_mw])
        result = await chain.execute({}, async_handler)
        
        assert calls == ["before", "handler", "after"]
        assert result == "async_result"
    
    @pytest.mark.asyncio
    async def test_async_middleware_chain_order(self):
        """Async middleware should maintain order."""
        from praisonaiagents.hooks.middleware import AsyncMiddlewareChain
        
        order = []
        
        async def mw1(req, call_next):
            order.append(1)
            result = await call_next(req)
            order.append(-1)
            return result
        
        async def mw2(req, call_next):
            order.append(2)
            result = await call_next(req)
            order.append(-2)
            return result
        
        async def handler(req):
            order.append(0)
            return "done"
        
        chain = AsyncMiddlewareChain([mw1, mw2])
        await chain.execute({}, handler)
        
        assert order == [1, 2, 0, -2, -1]


class TestAgentMiddlewareIntegration:
    """Test middleware integration with Agent class."""
    
    def test_agent_accepts_hooks_parameter(self):
        """Agent should accept hooks parameter."""
        from praisonaiagents import Agent
        from praisonaiagents.hooks import before_model
        
        @before_model
        def my_hook(req):
            return req
        
        # Should not raise
        agent = Agent(
            name="Test",
            instructions="Test agent",
            hooks=[my_hook]
        )
        assert agent is not None
    
    def test_agent_hooks_empty_by_default(self):
        """Agent should have empty hooks by default."""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test", instructions="Test")
        # Should have no hooks or empty hooks list
        hooks = getattr(agent, '_hooks', None) or getattr(agent, 'hooks', [])
        assert hooks is None or len(hooks) == 0


class TestMiddlewareZeroOverhead:
    """Test that middleware has zero overhead when not used."""
    
    def test_no_hooks_fast_path(self):
        """When no hooks registered, should take fast path."""
        from praisonaiagents.hooks.middleware import MiddlewareChain
        
        # Empty chain should be essentially a no-op
        chain = MiddlewareChain([])
        
        call_count = [0]
        def handler(req):
            call_count[0] += 1
            return "result"
        
        result = chain.execute({}, handler)
        assert result == "result"
        assert call_count[0] == 1
    
    def test_middleware_chain_is_none_check(self):
        """Should handle None middleware list gracefully."""
        from praisonaiagents.hooks.middleware import MiddlewareChain
        
        chain = MiddlewareChain(None)
        result = chain.execute({}, lambda r: "ok")
        assert result == "ok"

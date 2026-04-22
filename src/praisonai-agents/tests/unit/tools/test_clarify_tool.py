"""
Tests for the clarify tool functionality.

Tests the clarify tool, handlers, and integration patterns.
"""

import pytest
from unittest.mock import Mock, AsyncMock
import asyncio

from praisonaiagents.tools.clarify import (
    ClarifyTool, 
    ClarifyHandler, 
    clarify,
    create_cli_clarify_handler,
    create_bot_clarify_handler
)


def test_clarify_tool_basic():
    """Test basic clarify tool functionality."""
    
    # Create a mock handler
    mock_handler = Mock()
    mock_handler.ask = AsyncMock(return_value="test answer")
    
    tool = ClarifyTool(handler=mock_handler)
    
    assert tool.name == "clarify"
    assert "clarifying question" in tool.description
    
    # Test schema
    schema = tool.get_schema()
    assert schema["function"]["name"] == "clarify"
    assert "question" in schema["function"]["parameters"]["properties"]
    assert "choices" in schema["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_clarify_tool_run():
    """Test running the clarify tool."""
    
    # Create a mock handler
    mock_handler = Mock()
    mock_handler.ask = AsyncMock(return_value="user response")
    
    tool = ClarifyTool(handler=mock_handler)
    
    result = await tool.run(question="What is your choice?", choices=["A", "B", "C"])
    
    assert result == "user response"
    mock_handler.ask.assert_called_once_with("What is your choice?", ["A", "B", "C"])


@pytest.mark.asyncio  
async def test_clarify_tool_with_context_handler():
    """Test clarify tool using handler from context."""
    
    # Create context with clarify handler
    context_handler = Mock()
    context_handler.ask = AsyncMock(return_value="context response")
    
    ctx = {"clarify_handler": context_handler}
    
    tool = ClarifyTool()  # No handler provided
    
    result = await tool.run(question="Context question?", ctx=ctx)
    
    assert result == "context response"
    context_handler.ask.assert_called_once_with("Context question?", None)


@pytest.mark.asyncio
async def test_clarify_tool_with_callable_context():
    """Test clarify tool with callable context handler."""
    
    async def context_handler(question, choices):
        return f"Answered: {question}"
    
    ctx = {"clarify_handler": context_handler}
    
    tool = ClarifyTool()
    
    result = await tool.run(question="Test question?", ctx=ctx)
    
    assert result == "Answered: Test question?"


@pytest.mark.asyncio
async def test_clarify_tool_fallback():
    """Test clarify tool fallback when no handler available."""
    
    tool = ClarifyTool()  # No handler
    
    result = await tool.run(question="Fallback question?")
    
    assert "No interactive channel available" in result
    assert "Fallback question?" in result


def test_clarify_handler_basic():
    """Test basic ClarifyHandler functionality."""
    
    def mock_ask(question, choices):
        return f"Mock answer to: {question}"
    
    handler = ClarifyHandler(ask_callback=mock_ask)
    
    # Test sync callback
    result = asyncio.run(handler.ask("Test question?"))
    
    assert result == "Mock answer to: Test question?"


@pytest.mark.asyncio
async def test_clarify_handler_async_callback():
    """Test ClarifyHandler with async callback."""
    
    async def mock_ask(question, choices):
        return f"Async answer to: {question}"
    
    handler = ClarifyHandler(ask_callback=mock_ask)
    
    result = await handler.ask("Async question?")
    
    assert result == "Async answer to: Async question?"


@pytest.mark.asyncio
async def test_clarify_handler_no_callback():
    """Test ClarifyHandler fallback when no callback provided."""
    
    handler = ClarifyHandler()  # No callback
    
    result = await handler.ask("No callback question?")
    
    assert "No interactive channel available" in result
    assert "No callback question?" in result


@pytest.mark.asyncio
async def test_clarify_handler_callback_exception():
    """Test ClarifyHandler when callback raises exception."""
    
    def failing_callback(question, choices):
        raise ValueError("Callback failed")
    
    handler = ClarifyHandler(ask_callback=failing_callback)
    
    result = await handler.ask("Failing question?")
    
    # Should fall back gracefully
    assert "No interactive channel available" in result


def test_create_cli_clarify_handler():
    """Test creating a CLI clarify handler."""
    
    handler = create_cli_clarify_handler()
    
    assert isinstance(handler, ClarifyHandler)
    assert handler.ask_callback is not None


def test_create_bot_clarify_handler():
    """Test creating a bot clarify handler."""
    
    send_message_fn = AsyncMock()
    wait_for_reply_fn = AsyncMock(return_value="bot reply")
    
    handler = create_bot_clarify_handler(send_message_fn, wait_for_reply_fn)
    
    assert isinstance(handler, ClarifyHandler)
    assert handler.ask_callback is not None


@pytest.mark.asyncio
async def test_bot_clarify_handler_usage():
    """Test using the bot clarify handler."""
    
    send_message_fn = AsyncMock()
    wait_for_reply_fn = AsyncMock(return_value="user choice")
    
    handler = create_bot_clarify_handler(send_message_fn, wait_for_reply_fn)
    
    result = await handler.ask("Bot question?", ["Option 1", "Option 2"])
    
    assert result == "user choice"
    send_message_fn.assert_called_once()
    wait_for_reply_fn.assert_called_once()
    
    # Check that message contains the question and choices
    sent_message = send_message_fn.call_args[0][0]
    assert "Bot question?" in sent_message
    assert "Option 1" in sent_message
    assert "Option 2" in sent_message


@pytest.mark.asyncio
async def test_bot_clarify_handler_choice_selection():
    """Test bot clarify handler with numeric choice selection."""
    
    send_message_fn = AsyncMock()
    wait_for_reply_fn = AsyncMock(return_value="2")  # Select second choice
    
    handler = create_bot_clarify_handler(send_message_fn, wait_for_reply_fn)
    
    result = await handler.ask("Choose:", ["First", "Second", "Third"])
    
    assert result == "Second"  # Should convert "2" to "Second"


def test_default_clarify_instance():
    """Test that the default clarify instance is available."""
    
    # Test the module-level clarify instance
    assert clarify is not None
    assert isinstance(clarify, ClarifyTool)
    assert clarify.name == "clarify"


@pytest.mark.asyncio
async def test_real_agentic_clarify():
    """Real agentic test - clarify tool should work end-to-end."""
    
    # Create a mock handler that simulates user interaction
    responses = ["python"]  # Simulated user response
    
    async def mock_ask(question, choices):
        return responses.pop(0) if responses else "no answer"
    
    # Create tool with handler
    tool = ClarifyTool(ClarifyHandler(ask_callback=mock_ask))
    
    # Simulate agent calling the tool
    result = await tool.run(
        question="Which programming language should I use?",
        choices=["python", "javascript", "rust"]
    )
    
    assert result == "python"
    
    print(f"✅ Clarify tool test passed: {result}")


if __name__ == "__main__":
    pytest.main([__file__])
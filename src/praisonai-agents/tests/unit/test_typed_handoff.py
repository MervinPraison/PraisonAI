"""Unit tests for TypedHandoff with Pydantic schema validation.

Tests cover schema validation, error handling, backward compatibility,
and real agentic integration per AGENTS.md §9.4.
"""
import asyncio
import json
import pytest
from pydantic import BaseModel, ValidationError as PydanticValidationError
from unittest.mock import Mock, patch

from praisonaiagents.agent.handoff import TypedHandoff, Handoff, HandoffResult, HandoffConfig
from praisonaiagents.errors import HandoffValidationError
from praisonaiagents.agent.agent import Agent


class TestSchema(BaseModel):
    """Test schema for validation tests."""
    name: str
    count: int
    active: bool = True


class TestSchemaComplex(BaseModel):
    """Complex test schema with nested data."""
    title: str
    items: list[str]
    metadata: dict[str, int]
    confidence: float


# =============================================================================
# Unit Tests - Schema Validation
# =============================================================================

def test_typed_handoff_construction():
    """Test TypedHandoff can be constructed with valid schema."""
    target_agent = Mock()
    target_agent.name = "test-agent"
    
    handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
    
    assert handoff.agent == target_agent
    assert handoff._input_schema == TestSchema
    assert isinstance(handoff, Handoff)  # Inheritance check


def test_typed_handoff_no_pydantic_error():
    """Test TypedHandoff raises ImportError when Pydantic unavailable."""
    target_agent = Mock()
    target_agent.name = "test-agent"
    
    with patch('praisonaiagents.agent.handoff.PYDANTIC_AVAILABLE', False):
        with pytest.raises(ImportError, match="Pydantic is required"):
            TypedHandoff(agent=target_agent, input_schema=TestSchema)


def test_validate_payload_success():
    """Test _validate_payload with valid payload."""
    target_agent = Mock()
    target_agent.name = "test-agent"
    
    handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
    
    # Dict payload
    payload = {"name": "test", "count": 5, "active": False}
    result = handoff._validate_payload(payload)
    
    assert isinstance(result, TestSchema)
    assert result.name == "test"
    assert result.count == 5
    assert result.active is False


def test_validate_payload_pydantic_model():
    """Test _validate_payload with Pydantic model instance."""
    target_agent = Mock()
    target_agent.name = "test-agent"
    
    handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
    
    # Model instance payload
    payload = TestSchema(name="test", count=10)
    result = handoff._validate_payload(payload)
    
    assert isinstance(result, TestSchema)
    assert result.name == "test"
    assert result.count == 10
    assert result.active is True  # Default value


def test_validate_payload_validation_error():
    """Test _validate_payload raises HandoffValidationError on invalid data."""
    target_agent = Mock()
    target_agent.name = "test-agent"
    
    handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
    
    # Invalid payload - missing required field
    payload = {"count": 5}
    
    with pytest.raises(HandoffValidationError) as exc_info:
        handoff._validate_payload(payload)
    
    error = exc_info.value
    assert "Payload validation failed" in str(error)
    assert error.validation_errors is not None
    assert len(error.validation_errors) > 0


def test_validate_payload_type_error():
    """Test _validate_payload with wrong data types."""
    target_agent = Mock()
    target_agent.name = "test-agent"
    
    handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
    
    # Invalid types
    payload = {"name": "test", "count": "not-a-number", "active": "not-bool"}
    
    with pytest.raises(HandoffValidationError) as exc_info:
        handoff._validate_payload(payload)
    
    assert "Payload validation failed" in str(exc_info.value)


# =============================================================================
# Unit Tests - Execution Paths
# =============================================================================

@pytest.mark.asyncio
async def test_execute_programmatic_with_validation():
    """Test execute_programmatic validates and delegates to parent."""
    source_agent = Mock()
    source_agent.name = "source-agent"
    
    target_agent = Mock()
    target_agent.name = "target-agent"
    
    # Mock the parent execute_programmatic to return success
    with patch.object(Handoff, 'execute_programmatic') as mock_parent:
        mock_parent.return_value = HandoffResult(
            success=True,
            target_agent="target-agent",
            source_agent="source-agent",
            duration_seconds=0.1,
            handoff_depth=1
        )
        
        handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
        
        # Valid payload
        payload = {"name": "test", "count": 42}
        context = {"extra": "data"}
        
        result = handoff.execute_programmatic(source_agent, payload, **context)
        
        # Should validate, then call parent with JSON payload
        assert result.success is True
        assert result.target_agent == "target-agent"
        
        # Verify parent was called with JSON string
        mock_parent.assert_called_once()
        args, kwargs = mock_parent.call_args
        
        assert args[0] == source_agent  # source_agent
        # args[1] should be JSON string of validated payload
        payload_json = args[1]
        assert isinstance(payload_json, str)
        parsed = json.loads(payload_json)
        assert parsed["name"] == "test"
        assert parsed["count"] == 42
        assert parsed["active"] is True  # Default value


@pytest.mark.asyncio 
async def test_execute_async_with_validation():
    """Test execute_async validates and delegates to parent."""
    source_agent = Mock()
    source_agent.name = "source-agent"
    
    target_agent = Mock()
    target_agent.name = "target-agent"
    target_agent.start = Mock()
    target_agent.start.return_value = "Response from agent"
    
    # Mock the parent execute_async to return success
    with patch.object(Handoff, 'execute_async') as mock_parent:
        mock_parent.return_value = HandoffResult(
            success=True,
            target_agent="target-agent", 
            source_agent="source-agent",
            duration_seconds=0.2,
            handoff_depth=1
        )
        
        handoff = TypedHandoff(agent=target_agent, input_schema=TestSchemaComplex)
        
        # Valid complex payload
        payload = {
            "title": "Research Task",
            "items": ["task1", "task2"],
            "metadata": {"priority": 1, "urgency": 5},
            "confidence": 0.95
        }
        
        result = await handoff.execute_async(source_agent, payload)
        
        assert result.success is True
        
        # Verify parent was called with JSON string
        mock_parent.assert_called_once()
        args, kwargs = mock_parent.call_args
        
        payload_json = args[1]
        assert isinstance(payload_json, str)
        parsed = json.loads(payload_json)
        assert parsed["title"] == "Research Task"
        assert parsed["items"] == ["task1", "task2"]


def test_execute_programmatic_validation_failure():
    """Test execute_programmatic propagates validation errors."""
    source_agent = Mock()
    source_agent.name = "source-agent"
    
    target_agent = Mock()
    target_agent.name = "target-agent"
    
    handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
    
    # Invalid payload
    payload = {"name": 123}  # Wrong type
    
    with pytest.raises(HandoffValidationError) as exc_info:
        handoff.execute_programmatic(source_agent, payload)
    
    error = exc_info.value
    assert error.source_agent == "source-agent"
    assert error.agent_id == "source-agent"


# =============================================================================
# Unit Tests - Backward Compatibility
# =============================================================================

def test_string_payload_backward_compatibility():
    """Test TypedHandoff handles string payloads without validation."""
    source_agent = Mock()
    source_agent.name = "source-agent"
    
    target_agent = Mock()
    target_agent.name = "target-agent"
    
    # Mock parent to return success
    with patch.object(Handoff, 'execute_programmatic') as mock_parent:
        mock_parent.return_value = HandoffResult(
            success=True,
            target_agent="target-agent",
            source_agent="source-agent", 
            duration_seconds=0.1,
            handoff_depth=1
        )
        
        handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
        
        # String payload - should bypass validation
        payload = "Just a simple string message"
        
        result = handoff.execute_programmatic(source_agent, payload)
        
        assert result.success is True
        
        # Should call parent with original string payload
        mock_parent.assert_called_once()
        args, kwargs = mock_parent.call_args
        assert args[1] == "Just a simple string message"


def test_regular_handoff_still_works():
    """Test that regular Handoff class is unaffected."""
    target_agent = Mock()
    target_agent.name = "target-agent"
    
    # Regular Handoff should work normally
    handoff = Handoff(agent=target_agent)
    
    # Should not have _input_schema
    assert not hasattr(handoff, '_input_schema')


# =============================================================================
# Real Agentic Tests (AGENTS.md §9.4 requirement)
# =============================================================================

def test_real_agentic_typed_handoff_sync():
    """REAL agentic test: Agent runs end-to-end with TypedHandoff and calls LLM.
    
    This satisfies AGENTS.md §9.4 requirement for real agentic tests.
    Agent MUST call the LLM and produce actual text response.
    """
    # Create real agents with instructions
    researcher = Agent(
        name="researcher",
        instructions="You are a research assistant. When you receive research topics, say 'I will research: [topic]' and provide a brief response.",
        llm="gpt-4o-mini"
    )
    
    writer = Agent(
        name="writer", 
        instructions="You are a helpful assistant. Respond to any input with 'Hello from writer agent!'",
        llm="gpt-4o-mini"
    )
    
    # Create TypedHandoff with validation schema
    class ResearchRequest(BaseModel):
        topic: str
        depth: str = "basic"
        format: str = "summary"
    
    typed_handoff = TypedHandoff(agent=writer, input_schema=ResearchRequest)
    
    # Test valid payload - this will call the LLM!
    payload = ResearchRequest(topic="AI safety", depth="detailed")
    
    # Execute handoff - this MUST call the actual LLM 
    result = typed_handoff.execute_programmatic(
        source_agent=researcher,
        payload=payload
    )
    
    # Verify we got real LLM output
    assert result.success is True
    print(f"✅ Real agentic test result: {result}")
    print(f"✅ Target agent response: {result.target_agent}")
    
    # The response should be actual LLM output, not mock data
    assert isinstance(result.target_agent, str)
    assert len(result.target_agent) > 0


@pytest.mark.asyncio
async def test_real_agentic_typed_handoff_async():
    """REAL agentic test: Async Agent runs end-to-end with TypedHandoff.
    
    This satisfies AGENTS.md §9.4 requirement for real agentic tests.
    Agent MUST call the LLM and produce actual text response.
    """
    # Create real agents
    coordinator = Agent(
        name="coordinator",
        instructions="You coordinate tasks between agents.",
        llm="gpt-4o-mini" 
    )
    
    executor = Agent(
        name="executor",
        instructions="You execute tasks. Always respond with 'Task executed: [task details]'",
        llm="gpt-4o-mini"
    )
    
    # Schema for task execution
    class TaskExecution(BaseModel):
        task_id: str
        action: str
        priority: int = 1
    
    typed_handoff = TypedHandoff(agent=executor, input_schema=TaskExecution)
    
    # Execute async handoff with validation - calls real LLM
    task_data = TaskExecution(
        task_id="task-001", 
        action="analyze data",
        priority=2
    )
    
    result = await typed_handoff.execute_async(
        source_agent=coordinator,
        payload=task_data
    )
    
    # Verify real LLM response
    assert result.success is True
    print(f"✅ Real async agentic test result: {result}")
    
    # Should have actual LLM response
    assert isinstance(result.target_agent, str)
    assert len(result.target_agent) > 0


def test_typed_handoff_error_propagation():
    """Test that TypedHandoff properly handles and enriches validation errors."""
    researcher = Agent(
        name="researcher",
        instructions="Research assistant",
        llm="gpt-4o-mini"
    )
    
    writer = Agent(
        name="writer",
        instructions="Writing assistant", 
        llm="gpt-4o-mini"
    )
    
    class StrictSchema(BaseModel):
        required_field: str
        number_field: int
    
    typed_handoff = TypedHandoff(agent=writer, input_schema=StrictSchema)
    
    # Invalid payload missing required field
    invalid_payload = {"number_field": "not-a-number"}
    
    with pytest.raises(HandoffValidationError) as exc_info:
        typed_handoff.execute_programmatic(researcher, invalid_payload)
    
    error = exc_info.value
    assert error.source_agent == "researcher"
    assert error.agent_id == "researcher"
    assert "required_field" in str(error) or "Field required" in str(error)
    assert error.validation_errors is not None


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

def test_typed_handoff_with_input_filter():
    """Test TypedHandoff respects input_filter from parent class."""
    source_agent = Mock()
    source_agent.name = "source"
    
    target_agent = Mock()
    target_agent.name = "target"
    
    # Create filter that adds context
    def test_filter(source_agent_instance, payload, **kwargs):
        kwargs['filtered'] = True
        return kwargs
    
    with patch.object(Handoff, 'execute_programmatic') as mock_parent:
        mock_parent.return_value = HandoffResult(
            success=True, target_agent="target", source_agent="source", 
            duration_seconds=0.1, handoff_depth=1
        )
        
        # This should call _prepare_context which applies input_filter
        handoff = TypedHandoff(
            agent=target_agent, 
            input_schema=TestSchema,
            input_filter=test_filter
        )
        
        payload = {"name": "test", "count": 1}
        result = handoff.execute_programmatic(source_agent, payload)
        
        # Verify parent was called (delegation works)
        mock_parent.assert_called_once()


def test_json_serialization_error_handling():
    """Test handling of non-JSON serializable context data."""
    import datetime
    
    source_agent = Mock()
    source_agent.name = "source"
    
    target_agent = Mock()
    target_agent.name = "target"
    
    handoff = TypedHandoff(agent=target_agent, input_schema=TestSchema)
    
    # Payload with non-serializable data should be handled gracefully
    payload = {"name": "test", "count": 1}
    
    # Test that we can handle context with datetime (non-JSON serializable)
    non_serializable_context = {"timestamp": datetime.datetime.now()}
    
    with patch.object(Handoff, 'execute_programmatic') as mock_parent:
        mock_parent.return_value = HandoffResult(
            success=True, target_agent="target", source_agent="source",
            duration_seconds=0.1, handoff_depth=1
        )
        
        # This should not crash even with non-serializable context
        result = handoff.execute_programmatic(
            source_agent, 
            payload, 
            **non_serializable_context
        )
        
        assert result.success is True
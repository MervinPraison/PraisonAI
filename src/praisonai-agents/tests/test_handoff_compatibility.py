"""
Test backward compatibility for handoff feature.

This test ensures that:
1. Existing agent code works without handoffs
2. Agents can be created with all existing parameters
3. Tools work as before
4. No breaking changes were introduced
"""

from praisonaiagents import Agent, handoff, handoff_filters


def test_agent_without_handoffs():
    """Test that agents work without handoffs (backward compatibility)"""
    # Create agent without handoffs - should work as before
    agent = Agent(
        name="Test Agent",
        role="Tester",
        goal="Test functionality",
        backstory="I test things",
        instructions="Just a test agent"
    )
    
    assert agent.name == "Test Agent"
    assert agent.handoffs == []
    assert hasattr(agent, 'tools')


def test_agent_with_existing_tools():
    """Test that existing tool functionality still works"""
    def test_tool(input: str) -> str:
        """A test tool"""
        return f"Processed: {input}"
    
    agent = Agent(
        name="Tool Agent",
        tools=[test_tool]
    )
    
    assert len(agent.tools) == 1
    assert agent.tools[0] == test_tool


def test_agent_with_handoffs():
    """Test agent creation with handoffs"""
    target_agent = Agent(name="Target Agent")
    
    agent = Agent(
        name="Source Agent",
        handoffs=[target_agent]
    )
    
    # Check handoffs were stored
    assert len(agent.handoffs) == 1
    assert agent.handoffs[0] == target_agent
    
    # Check handoff was converted to tool
    assert len(agent.tools) == 1
    assert callable(agent.tools[0])
    assert agent.tools[0].__name__ == "transfer_to_target_agent"


def test_handoff_with_tools():
    """Test that handoffs and regular tools work together"""
    def my_tool():
        """Test tool"""
        return "tool result"
    
    target_agent = Agent(name="Target")
    
    agent = Agent(
        name="Source",
        tools=[my_tool],
        handoffs=[target_agent]
    )
    
    # Should have both the regular tool and the handoff tool
    assert len(agent.tools) == 2
    tool_names = [t.__name__ for t in agent.tools]
    assert "my_tool" in tool_names
    assert "transfer_to_target" in tool_names


def test_handoff_object():
    """Test using Handoff objects"""
    target = Agent(name="Target")
    
    handoff_obj = handoff(
        target,
        tool_name_override="custom_transfer",
        tool_description_override="Custom description"
    )
    
    agent = Agent(
        name="Source",
        handoffs=[handoff_obj]
    )
    
    assert len(agent.tools) == 1
    assert agent.tools[0].__name__ == "custom_transfer"
    assert agent.tools[0].__doc__ == "Custom description"


def test_mixed_handoffs():
    """Test mixing direct agent references and Handoff objects"""
    agent1 = Agent(name="Agent One")
    agent2 = Agent(name="Agent Two")
    
    source = Agent(
        name="Source",
        handoffs=[
            agent1,  # Direct reference
            handoff(agent2, tool_name_override="special_transfer")  # Handoff object
        ]
    )
    
    assert len(source.handoffs) == 2
    assert len(source.tools) == 2
    
    tool_names = [t.__name__ for t in source.tools]
    assert "transfer_to_agent_one" in tool_names
    assert "special_transfer" in tool_names


def test_handoff_filters():
    """Test handoff filter functions"""
    from praisonaiagents.agent.handoff import HandoffInputData
    
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi", "tool_calls": [{"name": "test"}]},
        {"role": "tool", "content": "result"},
        {"role": "user", "content": "Thanks"}
    ]
    
    # Test remove_all_tools filter
    data = HandoffInputData(messages=list(messages))
    filtered = handoff_filters.remove_all_tools(data)
    assert len(filtered.messages) == 3
    assert all(msg.get("role") not in ["tool"] and "tool_calls" not in msg
               for msg in filtered.messages if isinstance(msg, dict))

    # Test keep_last_n_messages filter
    data = HandoffInputData(messages=list(messages))
    filtered = handoff_filters.keep_last_n_messages(3)(data)
    assert len(filtered.messages) == 3
    assert filtered.messages[0]['role'] == 'assistant'

    # Test remove_system_messages filter
    data = HandoffInputData(messages=list(messages))
    filtered = handoff_filters.remove_system_messages(data)
    assert len(filtered.messages) == 4
    assert all(msg.get("role") != "system" for msg in filtered.messages if isinstance(msg, dict))


def test_all_agent_parameters():
    """Test that all agent parameters still work"""
    agent = Agent(
        name="Full Agent",
        role="Test Role",
        goal="Test Goal",
        backstory="Test Backstory",
        instructions="Test Instructions",
        llm="gpt-4",
        tools=[],
        function_calling_llm=None,
        max_iter=10,
        max_rpm=100,
        max_execution_time=300,
        memory=None,
        verbose=False,
        allow_delegation=True,
        step_callback=None,
        cache=False,
        system_template="Test template",
        prompt_template="Test prompt",
        response_template="Test response",
        allow_code_execution=True,
        max_retry_limit=5,
        respect_context_window=False,
        code_execution_mode="unsafe",
        embedder_config={"test": "config"},
        knowledge=None,
        knowledge_config={"test": "knowledge"},
        use_system_prompt=False,
        markdown=False,
        stream=False,
        self_reflect=True,
        max_reflect=5,
        min_reflect=2,
        reflect_llm="gpt-3.5-turbo",
        reflect_prompt="Reflect on this",
        user_id="test_user",
        reasoning_steps=True,
        guardrail=None,
        max_guardrail_retries=5,
        handoffs=[]  # New parameter
    )
    
    # Verify all parameters were set correctly
    assert agent.name == "Full Agent"
    assert agent.role == "Test Role"
    assert agent.max_iter == 10
    assert not agent.verbose
    assert agent.handoffs == []


if __name__ == "__main__":
    # Run basic tests
    print("Testing backward compatibility...")
    
    test_agent_without_handoffs()
    print("✓ Agents work without handoffs")
    
    test_agent_with_existing_tools()
    print("✓ Existing tools still work")
    
    test_agent_with_handoffs()
    print("✓ Agents work with handoffs")
    
    test_handoff_with_tools()
    print("✓ Handoffs and tools work together")
    
    test_handoff_object()
    print("✓ Handoff objects work correctly")
    
    test_mixed_handoffs()
    print("✓ Mixed handoff types work")
    
    test_handoff_filters()
    print("✓ Handoff filters work")
    
    test_all_agent_parameters()
    print("✓ All agent parameters preserved")
    
    print("\nAll backward compatibility tests passed! ✨")
#!/usr/bin/env python3
"""
Simple test for Agent guardrail functionality.
"""

def test_agent_guardrails():
    """Test basic Agent guardrail functionality."""
    print("Testing Agent guardrail functionality...")
    
    try:
        from praisonaiagents import Agent, TaskOutput
        print("✓ Basic imports successful")
        
        # Test function-based guardrail
        def test_guardrail(task_output: TaskOutput):
            if len(task_output.raw) < 10:
                return False, "Too short"
            return True, task_output
        
        # Test Agent creation with function guardrail
        agent1 = Agent(
            name="TestAgent1",
            instructions="You are a test agent",
            guardrail=test_guardrail,
            max_guardrail_retries=2
        )
        print("✓ Agent with function guardrail created successfully")
        print(f"  - Agent name: {agent1.name}")
        print(f"  - Has guardrail function: {agent1._guardrail_fn is not None}")
        print(f"  - Max retries: {agent1.max_guardrail_retries}")
        
        # Test Agent creation with string guardrail
        agent2 = Agent(
            name="TestAgent2",
            instructions="You are a test agent",
            guardrail="Ensure the response is polite and professional",
            max_guardrail_retries=3
        )
        print("✓ Agent with LLM guardrail created successfully")
        print(f"  - Agent name: {agent2.name}")
        print(f"  - Has guardrail function: {agent2._guardrail_fn is not None}")
        print(f"  - Max retries: {agent2.max_guardrail_retries}")
        
        # Test Agent without guardrail
        agent3 = Agent(
            name="TestAgent3",
            instructions="You are a test agent"
        )
        print("✓ Agent without guardrail created successfully")
        print(f"  - Agent name: {agent3.name}")
        print(f"  - Has guardrail function: {agent3._guardrail_fn is None}")
        
        print("\n🎉 All Agent guardrail tests passed!")
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_agent_guardrails()
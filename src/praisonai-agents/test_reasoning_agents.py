#!/usr/bin/env python3
"""Test script for ReasoningAgent and DualBrainAgent implementations."""

import os
import sys
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

from praisonaiagents import Agent, ReasoningAgent, DualBrainAgent, ReasoningConfig, ActionState

def test_reasoning_agent():
    """Test basic ReasoningAgent functionality."""
    print("=== Testing ReasoningAgent ===")
    
    try:
        # Test basic initialization
        agent = ReasoningAgent(
            name="TestReasoningAgent",
            reasoning_config=ReasoningConfig(
                min_steps=2,
                max_steps=5,
                style="analytical"
            )
        )
        print("✓ ReasoningAgent initialization successful")
        
        # Test reasoning summary
        summary = agent.get_reasoning_summary()
        print(f"✓ Initial reasoning summary: {summary}")
        
        # Test trace start
        task_id = agent.start_reasoning_trace("Test problem")
        print(f"✓ Started reasoning trace: {task_id}")
        
        print("ReasoningAgent tests passed!\n")
        return True
        
    except Exception as e:
        print(f"✗ ReasoningAgent test failed: {e}")
        return False

def test_dual_brain_agent():
    """Test basic DualBrainAgent functionality."""
    print("=== Testing DualBrainAgent ===")
    
    try:
        # Test basic initialization  
        agent = DualBrainAgent(
            name="TestDualBrainAgent",
            llm="gpt-4o-mini",  # Use lighter model for testing
            reasoning_llm="gpt-4o-mini",  # Use same model for testing
            reasoning_config={
                "style": "analytical",
                "min_confidence": 0.7
            }
        )
        print("✓ DualBrainAgent initialization successful")
        
        # Test brain status
        status = agent.get_brain_status()
        print(f"✓ Brain status: {status}")
        
        # Test LLM switching
        agent.switch_reasoning_llm("gpt-4o", {"temperature": 0.2})
        print("✓ LLM switching successful")
        
        print("DualBrainAgent tests passed!\n")
        return True
        
    except Exception as e:
        print(f"✗ DualBrainAgent test failed: {e}")
        return False

def test_reasoning_module():
    """Test reasoning module components."""
    print("=== Testing Reasoning Module ===")
    
    try:
        from praisonaiagents.reasoning import reason_step, ActionState, ReasoningStep
        
        # Create a mock agent for testing
        class MockAgent:
            def __init__(self):
                self.reasoning_trace = None
                
            def add_reasoning_step(self, step):
                pass
        
        mock_agent = MockAgent()
        
        # Test reason_step function
        step = reason_step(
            agent=mock_agent,
            thought="This is a test thought",
            action="This is a test action",
            confidence=0.8,
            state=ActionState.CONTINUE
        )
        print(f"✓ Created reasoning step: {step.title} (confidence: {step.confidence})")
        
        # Test ActionState enum
        states = [ActionState.CONTINUE, ActionState.VALIDATE, ActionState.RESET, ActionState.FINAL_ANSWER]
        print(f"✓ ActionState values: {[s.value for s in states]}")
        
        print("Reasoning module tests passed!\n")
        return True
        
    except Exception as e:
        print(f"✗ Reasoning module test failed: {e}")
        return False

def test_imports():
    """Test that all classes can be imported properly."""
    print("=== Testing Imports ===")
    
    try:
        # Test main package imports
        from praisonaiagents import ReasoningAgent, DualBrainAgent
        from praisonaiagents import ReasoningConfig, ReasoningStep, ReasoningTrace, ActionState, reason_step
        print("✓ All main package imports successful")
        
        # Test agent module imports  
        from praisonaiagents.agent import ReasoningAgent, DualBrainAgent
        print("✓ Agent module imports successful")
        
        # Test reasoning module imports
        from praisonaiagents.reasoning import ReasoningConfig, ActionState
        print("✓ Reasoning module imports successful")
        
        print("Import tests passed!\n")
        return True
        
    except Exception as e:
        print(f"✗ Import test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing ReasoningAgent and DualBrainAgent implementations...\n")
    
    all_passed = True
    
    # Run all tests
    tests = [
        test_imports,
        test_reasoning_module,
        test_reasoning_agent,
        test_dual_brain_agent
    ]
    
    for test_func in tests:
        if not test_func():
            all_passed = False
    
    if all_passed:
        print("🎉 All tests passed! Implementation looks good.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please check the implementation.")
        sys.exit(1)
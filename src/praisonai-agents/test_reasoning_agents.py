#!/usr/bin/env python3
"""
Test script for ReasoningAgent and DualBrainAgent implementations.

This script tests the new reasoning capabilities to ensure they work correctly
and maintain backward compatibility with the existing Agent class.
"""

import os
import sys
import logging

# Add the praisonaiagents directory to the path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

# Test imports
print("Testing imports...")
try:
    from praisonaiagents import Agent, ReasoningAgent, DualBrainAgent
    from praisonaiagents import ReasoningConfig, ReasoningFlow, ActionState
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Set up logging for testing
logging.basicConfig(level=logging.INFO)

def test_basic_agent_compatibility():
    """Test that basic Agent functionality still works."""
    print("\n=== Testing Basic Agent Compatibility ===")
    
    try:
        agent = Agent(
            name="TestAgent",
            role="Tester",
            goal="Test basic functionality",
            llm="gpt-4o-mini"
        )
        
        # Test basic chat (without API call for now)
        print("✓ Basic Agent creation successful")
        print(f"  - Agent name: {agent.name}")
        print(f"  - Agent role: {agent.role}")
        print(f"  - Agent goal: {agent.goal}")
        
        return True
        
    except Exception as e:
        print(f"✗ Basic Agent test failed: {e}")
        return False

def test_reasoning_agent_creation():
    """Test ReasoningAgent creation and configuration."""
    print("\n=== Testing ReasoningAgent Creation ===")
    
    try:
        # Test with default configuration
        agent1 = ReasoningAgent(
            name="ReasoningAgent1",
            role="Problem Solver",
            llm="gpt-4o-mini"
        )
        
        print("✓ ReasoningAgent with defaults created successfully")
        print(f"  - Reasoning enabled: {agent1.reasoning_enabled}")
        print(f"  - Min confidence: {agent1.min_confidence}")
        print(f"  - Reasoning steps: {agent1.reasoning_steps}")
        print(f"  - Self reflection: {agent1.self_reflect}")
        
        # Test with custom ReasoningConfig
        config = ReasoningConfig(
            min_steps=3,
            max_steps=8,
            style="analytical",
            confidence_threshold=0.8
        )
        
        agent2 = ReasoningAgent(
            name="ReasoningAgent2",
            role="Analytical Solver",
            reasoning_config=config,
            min_confidence=0.85,
            llm="gpt-4o-mini"
        )
        
        print("✓ ReasoningAgent with custom config created successfully")
        print(f"  - Min steps: {agent2.reasoning_config.min_steps}")
        print(f"  - Max steps: {agent2.reasoning_config.max_steps}")
        print(f"  - Style: {agent2.reasoning_config.style}")
        print(f"  - Confidence threshold: {agent2.reasoning_config.confidence_threshold}")
        
        # Test with dictionary config
        agent3 = ReasoningAgent(
            name="ReasoningAgent3",
            role="Creative Solver",
            reasoning_config={
                "min_steps": 2,
                "max_steps": 6,
                "style": "creative",
                "confidence_threshold": 0.7
            },
            llm="gpt-4o-mini"
        )
        
        print("✓ ReasoningAgent with dict config created successfully")
        print(f"  - Style: {agent3.reasoning_config.style}")
        
        return True
        
    except Exception as e:
        print(f"✗ ReasoningAgent creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dual_brain_agent_creation():
    """Test DualBrainAgent creation and configuration."""
    print("\n=== Testing DualBrainAgent Creation ===")
    
    try:
        # Test with default models
        agent1 = DualBrainAgent(
            name="DualBrainAgent1",
            role="Dual Model Solver"
        )
        
        print("✓ DualBrainAgent with defaults created successfully")
        model_info = agent1.get_model_info()
        print(f"  - Conversational model: {model_info['conversational_model']}")
        print(f"  - Reasoning model: {model_info['reasoning_model']}")
        
        # Test with specified models
        agent2 = DualBrainAgent(
            name="DualBrainAgent2",
            role="Specialized Solver",
            llm="gpt-4o-mini",
            reasoning_llm="gpt-4o-mini",
            llm_config={"temperature": 0.7},
            reasoning_config={
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "system_prompt": "You are a step-by-step analytical reasoner"
            }
        )
        
        print("✓ DualBrainAgent with custom models created successfully")
        model_info = agent2.get_model_info()
        print(f"  - Conversational model: {model_info['conversational_model']}")
        print(f"  - Reasoning model: {model_info['reasoning_model']}")
        print(f"  - LLM config: {model_info['llm_config']}")
        
        return True
        
    except Exception as e:
        print(f"✗ DualBrainAgent creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_reasoning_engine():
    """Test the reasoning engine functionality."""
    print("\n=== Testing Reasoning Engine ===")
    
    try:
        config = ReasoningConfig(min_steps=2, max_steps=5)
        flow = ReasoningFlow()
        
        agent = ReasoningAgent(
            name="EngineTestAgent",
            reasoning_config=config,
            reasoning_flow=flow,
            llm="gpt-4o-mini"
        )
        
        # Test reasoning engine methods
        engine = agent.reasoning_engine
        
        # Create test steps
        step1 = engine.create_step(
            title="Analysis",
            action="Analyze the problem",
            thought="This is a test thought",
            confidence=0.8
        )
        
        step2 = engine.create_step(
            title="Solution",
            action="Generate solution",
            thought="This is a solution thought",
            confidence=0.9
        )
        
        print("✓ Reasoning steps created successfully")
        print(f"  - Step 1 ID: {step1.id}")
        print(f"  - Step 2 ID: {step2.id}")
        
        # Test validation
        is_valid = engine.validate_step(step1)
        print(f"  - Step 1 validation: {is_valid}")
        
        # Test action state determination
        action_state = engine.should_continue()
        print(f"  - Next action state: {action_state}")
        
        # Test reasoning trace
        trace = engine.get_reasoning_trace()
        print(f"  - Reasoning trace length: {len(trace)}")
        
        # Test summary
        summary = engine.get_reasoning_summary()
        print(f"  - Total steps: {summary['total_steps']}")
        print(f"  - Avg confidence: {summary['avg_confidence']:.2f}")
        
        return True
        
    except Exception as e:
        print(f"✗ Reasoning engine test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_backward_compatibility():
    """Test that existing Agent usage patterns still work."""
    print("\n=== Testing Backward Compatibility ===")
    
    try:
        # Test that ReasoningAgent can be used like a regular Agent
        reasoning_agent = ReasoningAgent(
            name="CompatibilityAgent",
            role="Test Agent",
            reasoning=False,  # Disable reasoning to test regular Agent behavior
            llm="gpt-4o-mini"
        )
        
        # Should behave like regular Agent when reasoning is disabled
        print("✓ ReasoningAgent with reasoning disabled created successfully")
        print(f"  - Reasoning enabled: {reasoning_agent.reasoning_enabled}")
        
        # Test DualBrainAgent with single model (should work like regular agent)
        dual_agent = DualBrainAgent(
            name="CompatibilityDualAgent",
            role="Test Agent",
            llm="gpt-4o-mini",
            reasoning_llm="gpt-4o-mini",  # Same model for both
            reasoning=False
        )
        
        print("✓ DualBrainAgent with same models created successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Backward compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_configuration_classes():
    """Test the configuration classes."""
    print("\n=== Testing Configuration Classes ===")
    
    try:
        # Test ReasoningConfig
        config = ReasoningConfig(
            min_steps=3,
            max_steps=10,
            style="systematic",
            confidence_threshold=0.8
        )
        
        print("✓ ReasoningConfig created successfully")
        print(f"  - Min steps: {config.min_steps}")
        print(f"  - Max steps: {config.max_steps}")
        print(f"  - Style: {config.style}")
        
        # Test ReasoningFlow
        def custom_validator(step):
            return step.confidence > 0.7
            
        def custom_reset_condition(step):
            return step.retries > 2
            
        flow = ReasoningFlow(
            on_validate=custom_validator,
            on_reset=custom_reset_condition,
            auto_validate_critical=True
        )
        
        print("✓ ReasoningFlow created successfully")
        print(f"  - Auto validate critical: {flow.auto_validate_critical}")
        
        # Test ActionState enum
        states = [ActionState.CONTINUE, ActionState.VALIDATE, ActionState.RESET, ActionState.FINAL_ANSWER]
        print("✓ ActionState enum accessible")
        print(f"  - Available states: {[state.value for state in states]}")
        
        return True
        
    except Exception as e:
        print(f"✗ Configuration classes test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_all_tests():
    """Run all tests and report results."""
    print("Starting ReasoningAgent and DualBrainAgent Tests...\n")
    
    tests = [
        ("Basic Agent Compatibility", test_basic_agent_compatibility),
        ("ReasoningAgent Creation", test_reasoning_agent_creation),
        ("DualBrainAgent Creation", test_dual_brain_agent_creation),
        ("Reasoning Engine", test_reasoning_engine),
        ("Backward Compatibility", test_backward_compatibility),
        ("Configuration Classes", test_configuration_classes),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"✗ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)
    
    passed = 0
    failed = 0
    
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{status:>6}: {test_name}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Implementation appears to be working correctly.")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Review the errors above.")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
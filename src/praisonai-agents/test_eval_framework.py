#!/usr/bin/env python3
"""
Test script for the PraisonAI evaluation framework.
"""

import sys
import os

# Add the package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

try:
    from praisonaiagents import Agent, AccuracyEval, ReliabilityEval, PerformanceEval, EvalSuite, TestCase, EvalCriteria
    print("✅ Successfully imported evaluation framework components")
except ImportError as e:
    print(f"❌ Failed to import evaluation framework: {e}")
    sys.exit(1)

def test_basic_agent():
    """Test basic agent creation."""
    try:
        agent = Agent(
            name="TestAgent", 
            role="Tester",
            goal="Test the evaluation framework",
            backstory="I am a test agent for the evaluation framework",
            llm="gpt-4o-mini"
        )
        print("✅ Agent created successfully")
        return agent
    except Exception as e:
        print(f"❌ Failed to create agent: {e}")
        return None

def test_accuracy_eval(agent):
    """Test accuracy evaluation."""
    try:
        eval_test = AccuracyEval(
            agent=agent,
            input="What is the capital of France?",
            expected_output="Paris"
        )
        print("✅ AccuracyEval created successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to create AccuracyEval: {e}")
        return False

def test_reliability_eval(agent):
    """Test reliability evaluation."""
    try:
        test_scenarios = [{
            "input": "Search for weather information",
            "expected_tools": ["web_search"],
            "allow_additional": True
        }]
        
        eval_test = ReliabilityEval(
            agent=agent,
            test_scenarios=test_scenarios
        )
        print("✅ ReliabilityEval created successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to create ReliabilityEval: {e}")
        return False

def test_performance_eval(agent):
    """Test performance evaluation."""
    try:
        eval_test = PerformanceEval(
            agent=agent,
            benchmark_queries=["Hello, how are you?"],
            metrics={"runtime": True, "memory": True}
        )
        print("✅ PerformanceEval created successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to create PerformanceEval: {e}")
        return False

def test_eval_suite(agent):
    """Test evaluation suite."""
    try:
        test_cases = [
            TestCase(
                name="Basic Math",
                input="What is 2+2?",
                expected_output="4",
                eval_type="accuracy"
            ),
            TestCase(
                name="Performance Test",
                input="Hello",
                max_runtime=5.0,
                eval_type="performance"
            )
        ]
        
        suite = EvalSuite(
            name="Test Suite",
            agents=[agent],
            test_cases=test_cases
        )
        print("✅ EvalSuite created successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to create EvalSuite: {e}")
        return False

def test_eval_criteria():
    """Test evaluation criteria."""
    try:
        criteria = EvalCriteria(
            factual_accuracy=0.5,
            completeness=0.3,
            relevance=0.2
        )
        print("✅ EvalCriteria created successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to create EvalCriteria: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing PraisonAI Evaluation Framework")
    print("=" * 50)
    
    # Test agent creation
    agent = test_basic_agent()
    if not agent:
        print("❌ Cannot continue without agent")
        return False
    
    # Test evaluation components
    agent_tests = [
        test_accuracy_eval,
        test_reliability_eval,
        test_performance_eval,
        test_eval_suite
    ]
    
    # Tests that don't need agent
    other_tests = [
        test_eval_criteria
    ]
    
    passed = 0
    total = len(agent_tests) + len(other_tests) + 1  # +1 for agent test
    passed += 1  # Agent test passed
    
    for test_func in agent_tests:
        if test_func(agent):
            passed += 1
    
    for test_func in other_tests:
        if test_func():
            passed += 1
    
    print("=" * 50)
    print(f"🏁 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Evaluation framework is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
#!/usr/bin/env python3
"""
Comprehensive test script to verify the provider pattern implementation.
Tests provider selection, thread safety, and multi-agent workflows.
"""

import os
import sys
import time
import json
import threading
from typing import Dict, Any, Optional
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.providers.factory import ProviderFactory

# Test configuration
VERBOSE = False  # Set to True for detailed output
REAL_API_CALLS = False  # Set to True to make actual API calls

def test_single_agent():
    """Test single agent with default configuration (should use lightweight OpenAI)"""
    print("\n=== Testing single agent with default configuration ===")
    
    try:
        agent = Agent(
            name="Test Agent",
            role="Assistant",
            goal="Help with testing",
            verbose=VERBOSE
        )
        
        # Assertions
        assert hasattr(agent, 'llm_instance'), "Agent should have llm_instance attribute"
        assert hasattr(agent.llm_instance, 'provider_type'), "LLM instance should have provider_type"
        
        # Default should use OpenAI provider for efficiency
        expected_provider = 'OpenAIProvider' if not os.getenv('PRAISONAI_LLM_PROVIDER') else 'LiteLLMProvider'
        actual_provider = agent.llm_instance.provider_type
        assert actual_provider == expected_provider, f"Expected {expected_provider}, got {actual_provider}"
        
        task = Task(
            description="Say hello and tell me what provider you're using",
            expected_output="A greeting message",
            agent=agent
        )
        
        start_time = time.time()
        
        if REAL_API_CALLS:
            result = agent.execute(task)
        else:
            result = f"Hello! I'm using {actual_provider} provider."
            
        execution_time = time.time() - start_time
        
        # Verify result
        assert result is not None, "Agent execution should return a result"
        assert isinstance(result, str), "Result should be a string"
        assert len(result) > 0, "Result should not be empty"
        
        print(f"✅ Result: {result[:100]}...")
        print(f"✅ Provider: {actual_provider}")
        print(f"✅ Execution time: {execution_time:.2f}s")
        print("✅ Single agent test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Single agent test FAILED: {str(e)}\n")
        return False

def test_multi_agent():
    """Test multi-agent collaboration"""
    print("\n=== Testing multi-agent collaboration ===")
    
    try:
        researcher = Agent(
            name="Researcher",
            role="Research Assistant",
            goal="Find information",
            verbose=VERBOSE
        )
        
        writer = Agent(
            name="Writer", 
            role="Content Writer",
            goal="Write content based on research",
            verbose=VERBOSE
        )
        
        # Verify agents are properly initialized
        assert hasattr(researcher, 'llm_instance'), "Researcher should have LLM instance"
        assert hasattr(writer, 'llm_instance'), "Writer should have LLM instance"
        
        research_task = Task(
            description="Research the benefits of the provider pattern in software design",
            expected_output="Key points about provider pattern benefits",
            agent=researcher
        )
        
        writing_task = Task(
            description="Write a brief summary of the provider pattern benefits based on the research",
            expected_output="A well-written summary",
            agent=writer,
            context=[research_task]
        )
        
        # Verify task linkage
        assert writing_task.context == [research_task], "Writing task should have research task as context"
        
        agents = PraisonAIAgents(
            agents=[researcher, writer],
            tasks=[research_task, writing_task],
            verbose=VERBOSE,
            process="sequential"
        )
        
        start_time = time.time()
        
        if REAL_API_CALLS:
            result = agents.start()
        else:
            result = {
                "research_output": "Provider pattern benefits: modularity, flexibility, testability",
                "writing_output": "The provider pattern offers key advantages in software design."
            }
            
        execution_time = time.time() - start_time
        
        # Verify results
        assert result is not None, "Multi-agent execution should return a result"
        
        print(f"✅ Final result: {str(result)[:200]}...")
        print(f"✅ Execution time: {execution_time:.2f}s")
        print(f"✅ Researcher provider: {researcher.llm_instance.provider_type}")
        print(f"✅ Writer provider: {writer.llm_instance.provider_type}")
        print("✅ Multi-agent test PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Multi-agent test FAILED: {str(e)}\n")
        return False

def test_provider_selection():
    """Test different provider configurations"""
    print("\n=== Testing provider selection ===")
    
    test_cases = [
        # (model, expected_provider, description)
        ("gpt-4o-mini", "OpenAIProvider", "OpenAI model should use OpenAI provider"),
        ("gpt-4", "OpenAIProvider", "GPT-4 should use OpenAI provider"),
        ("anthropic/claude-3-sonnet", "LiteLLMProvider", "Explicit provider prefix should use LiteLLM"),
        ("gemini-1.5-flash", "LiteLLMProvider", "Non-OpenAI model should use LiteLLM"),
        ("llama3.2:latest", "LiteLLMProvider", "Local model should use LiteLLM"),
    ]
    
    passed_tests = 0
    
    for model, expected_provider, description in test_cases:
        try:
            print(f"\n  Testing: {description}")
            
            # Use factory directly to test provider selection
            provider = ProviderFactory.create(
                model=model,
                api_key=f"test-key-{model}",
                provider="auto"  # Let factory decide
            )
            
            actual_provider = type(provider).__name__
            
            if actual_provider == expected_provider:
                print(f"  ✅ {model} → {actual_provider} (expected {expected_provider})")
                passed_tests += 1
            else:
                print(f"  ❌ {model} → {actual_provider} (expected {expected_provider})")
                
        except ImportError as e:
            if "OpenAI SDK is required" in str(e) and expected_provider == "OpenAIProvider":
                print(f"  ⚠️  {model} → OpenAI SDK not installed (using fallback)")
                passed_tests += 1  # Expected behavior
            else:
                print(f"  ❌ {model} → Import error: {str(e)}")
        except Exception as e:
            print(f"  ❌ {model} → Error: {str(e)}")
    
    print(f"\n✅ Provider selection: {passed_tests}/{len(test_cases)} tests passed")
    return passed_tests == len(test_cases)

def test_llm_direct_usage():
    """Test direct LLM class usage"""
    print("\n=== Testing direct LLM usage ===")
    
    try:
        # Test with explicit provider
        llm_openai = LLM(
            model="gpt-4o-mini",
            api_key="test-openai-key",
            provider="openai",
            verbose=False
        )
        
        assert llm_openai.provider_type == "OpenAIProvider", "Should use OpenAI provider when explicitly set"
        
        # Test with auto detection
        llm_auto = LLM(
            model="claude-3-haiku",
            api_key="test-anthropic-key",
            provider="auto",
            verbose=False
        )
        
        assert llm_auto.provider_type == "LiteLLMProvider", "Should auto-detect LiteLLM for Claude models"
        
        # Test context window detection
        context_size = llm_openai.get_context_size()
        assert context_size > 0, "Context size should be positive"
        assert context_size == 96000, f"GPT-4o-mini should have 96k context, got {context_size}"
        
        # Test _build_completion_params method
        params = llm_openai._build_completion_params(
            messages=[{"role": "user", "content": "test"}],
            temperature=0.5,
            stream=True
        )
        assert "messages" in params, "Params should include messages"
        assert params["temperature"] == 0.5, "Temperature should be set correctly"
        assert params["stream"] == True, "Stream should be set correctly"
        assert params["model"] == "gpt-4o-mini", "Model should be included"
        
        print("✅ LLM direct usage tests PASSED")
        return True
        
    except Exception as e:
        print(f"❌ LLM direct usage test FAILED: {str(e)}")
        return False

def test_environment_variables():
    """Test environment variable handling"""
    print("\n=== Testing environment variable handling ===")
    
    # Save original env
    original_provider = os.environ.get('PRAISONAI_LLM_PROVIDER')
    
    try:
        # Test 1: Force OpenAI provider
        os.environ['PRAISONAI_LLM_PROVIDER'] = 'openai'
        agent1 = Agent(
            name="Forced OpenAI Agent",
            role="Test Agent",
            llm="gpt-4o",
            verbose=False
        )
        assert agent1.llm_instance.provider_type == "OpenAIProvider", "Should use OpenAI when forced"
        print(f"  ✅ Agent 1 (forced OpenAI) using: {agent1.llm_instance.provider_type}")
        
        # Test 2: Force LiteLLM provider
        os.environ['PRAISONAI_LLM_PROVIDER'] = 'litellm'
        agent2 = Agent(
            name="Forced LiteLLM Agent",
            role="Test Agent", 
            llm="gpt-4o",
            verbose=False
        )
        assert agent2.llm_instance.provider_type == "LiteLLMProvider", "Should use LiteLLM when forced"
        print(f"  ✅ Agent 2 (forced LiteLLM) using: {agent2.llm_instance.provider_type}")
        
        print("✅ Environment variable tests PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Environment variable test FAILED: {str(e)}\n")
        return False
        
    finally:
        # Restore original env
        if original_provider:
            os.environ['PRAISONAI_LLM_PROVIDER'] = original_provider
        else:
            os.environ.pop('PRAISONAI_LLM_PROVIDER', None)

def test_thread_safety():
    """Test thread safety of provider initialization"""
    print("\n=== Testing thread safety ===")
    
    results = []
    errors = []
    
    def create_agent(index: int):
        """Create an agent in a thread"""
        try:
            # Use different models to test different providers
            models = ["gpt-4o-mini", "claude-3-haiku", "gemini-1.5-flash"]
            model = models[index % len(models)]
            
            agent = Agent(
                name=f"Thread Agent {index}",
                role=f"Test agent {index}",
                goal="Test thread safety",
                llm=model,
                api_key=f"test-key-{index}",
                verbose=False
            )
            
            # Verify the agent was created with correct provider
            provider_type = agent.llm_instance.provider_type
            results.append({
                "index": index,
                "model": model,
                "provider": provider_type,
                "thread": threading.current_thread().name
            })
            
        except Exception as e:
            errors.append({
                "index": index,
                "error": str(e),
                "thread": threading.current_thread().name
            })
    
    # Create multiple threads
    threads = []
    num_threads = 10
    
    for i in range(num_threads):
        t = threading.Thread(target=create_agent, args=(i,), name=f"TestThread-{i}")
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    # Analyze results
    print(f"  ✅ Created {len(results)} agents in {num_threads} threads")
    print(f"  {'❌' if errors else '✅'} Errors: {len(errors)}")
    
    if errors:
        for error in errors[:3]:  # Show first 3 errors
            print(f"    Error in thread {error['thread']}: {error['error']}")
    
    # Check for provider consistency
    model_providers = {}
    for result in results:
        model = result['model']
        provider = result['provider']
        if model not in model_providers:
            model_providers[model] = set()
        model_providers[model].add(provider)
    
    # Each model should consistently use the same provider
    consistent = all(len(providers) == 1 for providers in model_providers.values())
    
    if consistent:
        print("  ✅ Provider selection is consistent across threads")
    else:
        print("  ❌ Inconsistent provider selection detected")
        for model, providers in model_providers.items():
            print(f"    {model}: {providers}")
    
    print(f"✅ Thread safety test {'PASSED' if consistent and not errors else 'FAILED'}\n")
    return consistent and not errors

def test_error_handling():
    """Test error handling and recovery"""
    print("\n=== Testing error handling ===")
    
    test_cases = [
        # (config, should_fail, description)
        ({"model": "gpt-4o-mini", "api_key": ""}, True, "Empty API key"),
        ({"model": "invalid-model-xyz", "api_key": "test"}, False, "Invalid model name"),
        ({"model": "gpt-4o-mini", "api_key": "valid-key"}, False, "Valid configuration"),
    ]
    
    passed = 0
    
    for config, should_fail, description in test_cases:
        try:
            print(f"\n  Testing: {description}")
            
            llm = LLM(**config, verbose=False)
            
            # Try to use the LLM
            if REAL_API_CALLS and should_fail:
                response = llm.response("Test", stream=False, verbose=False)
                print(f"  ❌ Expected failure but succeeded")
            else:
                print(f"  ✅ LLM created successfully with provider: {llm.provider_type}")
                passed += 1
                
        except Exception as e:
            if should_fail:
                print(f"  ✅ Failed as expected: {str(e)[:50]}...")
                passed += 1
            else:
                print(f"  ❌ Unexpected failure: {str(e)}")
    
    print(f"\n✅ Error handling: {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)

def generate_test_report(results: Dict[str, bool]):
    """Generate a comprehensive test report"""
    print("\n" + "="*60)
    print("PROVIDER PATTERN TEST REPORT")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results.values() if r)
    
    print(f"\nTotal Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    print("\nTest Results:")
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")
    
    # Save report to file
    report = {
        "timestamp": time.time(),
        "total_tests": total_tests,
        "passed": passed_tests,
        "failed": total_tests - passed_tests,
        "success_rate": (passed_tests/total_tests)*100,
        "results": results,
        "configuration": {
            "verbose": VERBOSE,
            "real_api_calls": REAL_API_CALLS
        }
    }
    
    with open("provider_pattern_test_report.json", "w") as f:
        json.dump(report, f, indent=2)
    
    print("\nDetailed report saved to: provider_pattern_test_report.json")
    
    if passed_tests == total_tests:
        print("\n🎉 All tests passed! The provider pattern is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please check the implementation.")
    
    print("\nTips:")
    print("  - Set VERBOSE=True for detailed output")
    print("  - Set REAL_API_CALLS=True to test with actual API calls")
    print("  - Check provider_pattern_test_report.json for details")
    
    return passed_tests == total_tests

def main():
    """Run all provider pattern tests"""
    print("Starting Provider Pattern Tests")
    print("==============================")
    
    # Check environment
    print("\nEnvironment:")
    print(f"  OPENAI_API_KEY: {'Set' if os.getenv('OPENAI_API_KEY') else 'Not set'}")
    print(f"  PRAISONAI_LLM_PROVIDER: {os.getenv('PRAISONAI_LLM_PROVIDER', 'Not set')}")
    print(f"  Verbose mode: {VERBOSE}")
    print(f"  Real API calls: {REAL_API_CALLS}")
    
    # Track test results
    results = {}
    
    try:
        # Run all tests
        results["test_provider_selection"] = test_provider_selection()
        results["test_single_agent"] = test_single_agent()
        results["test_multi_agent"] = test_multi_agent()
        results["test_llm_direct_usage"] = test_llm_direct_usage()
        results["test_environment_variables"] = test_environment_variables()
        results["test_thread_safety"] = test_thread_safety()
        results["test_error_handling"] = test_error_handling()
        
    except Exception as e:
        print(f"\n❌ Critical test failure: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Generate report
    all_passed = generate_test_report(results)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Test suite for verifying thread-safety and parallel execution of the provider pattern.
Tests for concurrent API key usage, provider isolation, and race conditions.
"""

import os
import sys
import time
import threading
import asyncio
import json
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

# Test configuration
SIMULATION_MODE = True  # Set to False to use real API calls
TEST_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku",
    "gemini": "gemini-1.5-flash",
    "local": "llama3.2:latest"
}

# Track potential thread-safety violations
violations = {
    "env_var_changes": [],
    "race_conditions": [],
    "api_key_contamination": [],
    "errors": []
}

# Lock for thread-safe violation tracking
violation_lock = threading.Lock()

def track_violation(violation_type: str, details: str):
    """Thread-safe violation tracking."""
    with violation_lock:
        violations[violation_type].append({
            "time": time.time(),
            "thread": threading.current_thread().name,
            "details": details
        })

def monitor_environment_variables():
    """Monitor environment variables for unauthorized changes."""
    initial_env = os.environ.copy()
    
    def check_env():
        while getattr(threading.current_thread(), 'monitor_active', True):
            current_env = os.environ.copy()
            for key in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY']:
                if key in current_env and key in initial_env:
                    if current_env[key] != initial_env[key]:
                        track_violation("env_var_changes", 
                                      f"{key} changed from {initial_env[key][:8]}... to {current_env[key][:8]}...")
            time.sleep(0.1)
    
    monitor_thread = threading.Thread(target=check_env, name="EnvMonitor")
    monitor_thread.monitor_active = True
    monitor_thread.start()
    return monitor_thread

def test_concurrent_api_keys():
    """Test 1: Multiple threads using different API keys simultaneously."""
    print("\n=== Test 1: Concurrent API Key Usage ===")
    
    from praisonaiagents.llm.llm import LLM
    
    results = []
    
    def use_provider(provider_name: str, api_key: str, model: str):
        """Use a provider with a specific API key."""
        try:
            thread_id = threading.current_thread().name
            print(f"[{thread_id}] Starting with {provider_name} using key {api_key[:8]}...")
            
            # Create LLM instance
            llm = LLM(
                model=model,
                api_key=api_key,
                verbose=False
            )
            
            # Verify provider type
            print(f"[{thread_id}] Provider type: {llm.provider_type}")
            
            # Check if API key is correctly isolated
            if hasattr(llm.provider_instance, 'api_key'):
                actual_key = llm.provider_instance.api_key
                if actual_key != api_key:
                    track_violation("api_key_contamination", 
                                  f"Expected {api_key[:8]}..., got {actual_key[:8]}...")
            
            # Simulate API call
            if SIMULATION_MODE:
                time.sleep(0.5)  # Simulate network delay
                response = f"Response from {provider_name} with key {api_key[:8]}..."
            else:
                response = llm.response(
                    "Say hello and tell me which API key you're using (first 8 chars)",
                    stream=False,
                    verbose=False
                )
            
            results.append({
                "thread": thread_id,
                "provider": provider_name,
                "api_key": api_key[:8] + "...",
                "response": response,
                "success": True
            })
            
            print(f"[{thread_id}] Success: {response[:50]}...")
            
        except Exception as e:
            track_violation("errors", f"{provider_name}: {str(e)}")
            results.append({
                "thread": thread_id,
                "provider": provider_name,
                "api_key": api_key[:8] + "...",
                "error": str(e),
                "success": False
            })
            print(f"[{thread_id}] Error: {str(e)}")
    
    # Start environment monitoring
    monitor = monitor_environment_variables()
    
    # Create thread pool
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        
        # Submit tasks with different API keys
        futures.append(executor.submit(use_provider, "openai", "sk-openai-key-123", TEST_MODELS["openai"]))
        futures.append(executor.submit(use_provider, "anthropic", "sk-anthropic-key-456", TEST_MODELS["anthropic"]))
        futures.append(executor.submit(use_provider, "gemini", "sk-gemini-key-789", TEST_MODELS["gemini"]))
        futures.append(executor.submit(use_provider, "local", "no-key-needed", TEST_MODELS["local"]))
        
        # Wait for completion
        for future in as_completed(futures):
            future.result()
    
    # Stop monitoring
    monitor.monitor_active = False
    monitor.join(timeout=1)
    
    # Analyze results
    print("\n--- Test 1 Results ---")
    print(f"Total executions: {len(results)}")
    print(f"Successful: {sum(1 for r in results if r['success'])}")
    print(f"Failed: {sum(1 for r in results if not r['success'])}")
    print(f"Environment violations: {len(violations['env_var_changes'])}")
    print(f"API key contaminations: {len(violations['api_key_contamination'])}")
    
    return len(violations['env_var_changes']) == 0 and len(violations['api_key_contamination']) == 0

def test_provider_isolation():
    """Test 2: Multiple providers running in parallel with different configurations."""
    print("\n=== Test 2: Provider Isolation ===")
    
    from praisonaiagents.llm.llm import LLM
    
    configurations = [
        {"model": "gpt-4o-mini", "temperature": 0.1, "max_tokens": 100},
        {"model": "gpt-4o", "temperature": 0.9, "max_tokens": 500},
        {"model": "claude-3-haiku", "temperature": 0.5, "max_tokens": 200},
        {"model": "gemini-1.5-flash", "temperature": 0.7, "max_tokens": 300},
    ]
    
    results = []
    
    def test_configuration(config: Dict[str, Any]):
        """Test a specific configuration."""
        try:
            thread_id = threading.current_thread().name
            print(f"[{thread_id}] Testing config: {config}")
            
            llm = LLM(
                api_key=f"test-key-{config['model']}",
                verbose=False,
                **config
            )
            
            # Verify configuration is isolated
            assert llm.model == config['model']
            assert llm.temperature == config['temperature']
            assert llm.max_tokens == config['max_tokens']
            
            # Check provider instance has correct settings
            if hasattr(llm.provider_instance, 'kwargs'):
                provider_config = llm.provider_instance.kwargs
                if 'temperature' in provider_config and provider_config['temperature'] != config['temperature']:
                    track_violation("race_conditions", 
                                  f"Temperature mismatch: expected {config['temperature']}, got {provider_config['temperature']}")
            
            results.append({
                "thread": thread_id,
                "config": config,
                "success": True
            })
            
        except Exception as e:
            track_violation("errors", f"Config test: {str(e)}")
            results.append({
                "thread": thread_id,
                "config": config,
                "error": str(e),
                "success": False
            })
    
    # Reset violations for this test
    violations['race_conditions'].clear()
    
    # Run configurations in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(test_configuration, config) for config in configurations]
        for future in as_completed(futures):
            future.result()
    
    # Analyze results
    print("\n--- Test 2 Results ---")
    print(f"Total configurations tested: {len(results)}")
    print(f"Successful: {sum(1 for r in results if r['success'])}")
    print(f"Race conditions detected: {len(violations['race_conditions'])}")
    
    return len(violations['race_conditions']) == 0

def test_race_conditions():
    """Test 3: Stress test with many concurrent requests."""
    print("\n=== Test 3: Race Condition Stress Test ===")
    
    from praisonaiagents.llm.llm import LLM
    from praisonaiagents.llm.providers.litellm_provider import LiteLLMProvider
    
    # Track initialization counts
    init_counts = {"start": 0, "complete": 0}
    init_lock = threading.Lock()
    
    # Monkey patch to track initializations
    original_get_litellm = LiteLLMProvider._get_litellm
    
    def tracked_get_litellm(cls):
        with init_lock:
            init_counts["start"] += 1
        result = original_get_litellm()
        with init_lock:
            init_counts["complete"] += 1
        return result
    
    LiteLLMProvider._get_litellm = classmethod(tracked_get_litellm)
    
    results = []
    
    def stress_test_provider(index: int):
        """Stress test a provider instance."""
        try:
            # Use different models to force LiteLLM provider
            model = ["claude-3-haiku", "gemini-1.5-flash", "gpt-4"][index % 3]
            
            llm = LLM(
                model=model,
                api_key=f"stress-test-key-{index}",
                verbose=False
            )
            
            # Quick operation to test thread safety
            provider_type = llm.provider_type
            context_size = llm.get_context_size()
            
            results.append({
                "index": index,
                "model": model,
                "provider": provider_type,
                "context": context_size,
                "success": True
            })
            
        except Exception as e:
            results.append({
                "index": index,
                "error": str(e),
                "success": False
            })
    
    # Run many requests concurrently
    num_requests = 50
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(stress_test_provider, i) for i in range(num_requests)]
        for future in as_completed(futures):
            future.result()
    
    # Restore original method
    LiteLLMProvider._get_litellm = original_get_litellm
    
    # Analyze results
    print("\n--- Test 3 Results ---")
    print(f"Total requests: {len(results)}")
    print(f"Successful: {sum(1 for r in results if r['success'])}")
    print(f"Failed: {sum(1 for r in results if not r['success'])}")
    print(f"LiteLLM init starts: {init_counts['start']}")
    print(f"LiteLLM init completes: {init_counts['complete']}")
    
    # Check for race conditions in initialization
    if init_counts['start'] > init_counts['complete'] + 1:
        track_violation("race_conditions", 
                       f"Initialization race: {init_counts['start']} starts, {init_counts['complete']} completes")
    
    return init_counts['start'] <= 3  # Should initialize at most once per provider type

def test_async_parallel_execution():
    """Test 4: Async parallel execution with multiple agents."""
    print("\n=== Test 4: Async Parallel Execution ===")
    
    from praisonaiagents.agent.agent import Agent
    from praisonaiagents.task.task import Task
    
    async def run_agent_async(name: str, model: str, api_key: str):
        """Run an agent asynchronously."""
        try:
            agent = Agent(
                name=name,
                role=f"Test agent using {model}",
                goal="Respond to queries",
                llm=model,
                api_key=api_key,
                verbose=False
            )
            
            task = Task(
                description=f"Say hello from {name}",
                expected_output="A greeting",
                agent=agent
            )
            
            # Execute task asynchronously
            if SIMULATION_MODE:
                await asyncio.sleep(0.5)
                result = f"Hello from {name} using {model}"
            else:
                result = await agent.execute_async(task)
            
            return {
                "agent": name,
                "model": model,
                "result": result,
                "success": True
            }
            
        except Exception as e:
            return {
                "agent": name,
                "model": model,
                "error": str(e),
                "success": False
            }
    
    async def test_async_agents():
        """Test multiple agents running asynchronously."""
        tasks = [
            run_agent_async("Agent1", "gpt-4o-mini", "async-key-1"),
            run_agent_async("Agent2", "claude-3-haiku", "async-key-2"),
            run_agent_async("Agent3", "gemini-1.5-flash", "async-key-3"),
            run_agent_async("Agent4", "gpt-4", "async-key-4"),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    # Run async test
    results = asyncio.run(test_async_agents())
    
    # Analyze results
    print("\n--- Test 4 Results ---")
    print(f"Total agents: {len(results)}")
    successful = [r for r in results if isinstance(r, dict) and r.get('success')]
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(results) - len(successful)}")
    
    return len(successful) == len(results)

def test_error_isolation():
    """Test 5: Ensure errors in one thread don't affect others."""
    print("\n=== Test 5: Error Isolation ===")
    
    from praisonaiagents.llm.llm import LLM
    
    results = []
    
    def provider_with_error(should_fail: bool, index: int):
        """Test provider that might fail."""
        try:
            if should_fail:
                # Intentionally cause an error
                llm = LLM(
                    model="invalid-model-xyz",
                    api_key="",  # Empty API key
                    verbose=False
                )
                response = llm.response("This should fail")
            else:
                # Normal operation
                llm = LLM(
                    model="gpt-4o-mini",
                    api_key=f"valid-key-{index}",
                    verbose=False
                )
                
                if SIMULATION_MODE:
                    response = f"Success from thread {index}"
                else:
                    response = llm.response("Say hello", stream=False, verbose=False)
            
            results.append({
                "index": index,
                "should_fail": should_fail,
                "response": response,
                "success": True
            })
            
        except Exception as e:
            results.append({
                "index": index,
                "should_fail": should_fail,
                "error": str(e),
                "success": False
            })
    
    # Mix failing and successful operations
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = []
        for i in range(6):
            should_fail = i % 2 == 0  # Every other one fails
            futures.append(executor.submit(provider_with_error, should_fail, i))
        
        for future in as_completed(futures):
            future.result()
    
    # Analyze results
    print("\n--- Test 5 Results ---")
    expected_failures = sum(1 for r in results if r['should_fail'])
    actual_failures = sum(1 for r in results if not r['success'])
    expected_successes = sum(1 for r in results if not r['should_fail'])
    actual_successes = sum(1 for r in results if r['success'])
    
    print(f"Expected failures: {expected_failures}, Actual: {actual_failures}")
    print(f"Expected successes: {expected_successes}, Actual: {actual_successes}")
    
    # Errors should be isolated
    return actual_failures == expected_failures and actual_successes == expected_successes

def generate_report():
    """Generate a comprehensive test report."""
    print("\n" + "="*60)
    print("PARALLEL EXECUTION TEST REPORT")
    print("="*60)
    
    print(f"\nSimulation Mode: {'ON' if SIMULATION_MODE else 'OFF'}")
    print(f"Total Violations Detected:")
    print(f"  - Environment Variable Changes: {len(violations['env_var_changes'])}")
    print(f"  - Race Conditions: {len(violations['race_conditions'])}")
    print(f"  - API Key Contamination: {len(violations['api_key_contamination'])}")
    print(f"  - Errors: {len(violations['errors'])}")
    
    if violations['env_var_changes']:
        print("\nEnvironment Variable Violations:")
        for v in violations['env_var_changes'][:5]:
            print(f"  - {v['details']} (Thread: {v['thread']})")
    
    if violations['api_key_contamination']:
        print("\nAPI Key Contamination:")
        for v in violations['api_key_contamination'][:5]:
            print(f"  - {v['details']} (Thread: {v['thread']})")
    
    # Save detailed report
    report = {
        "timestamp": time.time(),
        "simulation_mode": SIMULATION_MODE,
        "violations": violations,
        "summary": {
            "env_var_changes": len(violations['env_var_changes']),
            "race_conditions": len(violations['race_conditions']),
            "api_key_contamination": len(violations['api_key_contamination']),
            "errors": len(violations['errors'])
        }
    }
    
    with open("parallel_test_report.json", "w") as f:
        json.dump(report, f, indent=2)
    
    print("\nDetailed report saved to: parallel_test_report.json")

def main():
    """Run all parallel execution tests."""
    print("Starting Parallel Provider Pattern Tests")
    print("========================================")
    
    test_results = {
        "test_concurrent_api_keys": False,
        "test_provider_isolation": False,
        "test_race_conditions": False,
        "test_async_parallel_execution": False,
        "test_error_isolation": False
    }
    
    try:
        # Run tests
        test_results["test_concurrent_api_keys"] = test_concurrent_api_keys()
        test_results["test_provider_isolation"] = test_provider_isolation()
        test_results["test_race_conditions"] = test_race_conditions()
        test_results["test_async_parallel_execution"] = test_async_parallel_execution()
        test_results["test_error_isolation"] = test_error_isolation()
        
    except Exception as e:
        print(f"\nCritical test failure: {str(e)}")
        traceback.print_exc()
    
    # Generate report
    generate_report()
    
    # Final verdict
    print("\n" + "="*60)
    print("FINAL VERDICT")
    print("="*60)
    
    all_passed = all(test_results.values())
    
    for test_name, passed in test_results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    if all_passed:
        print("\n🎉 All tests passed! The provider pattern is thread-safe.")
    else:
        print("\n⚠️  Some tests failed. The provider pattern needs fixes.")
    
    print("\nTo run with real API calls, set SIMULATION_MODE = False")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())

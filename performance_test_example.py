"""
Performance test example demonstrating the impact of optimizations
This shows potential speedups from caching and parallel execution
"""

import time
import asyncio
from typing import List, Dict, Any

# Simulate API call delays
SIMULATED_LLM_DELAY = 0.5  # 500ms per LLM call
SIMULATED_TOOL_DELAY = 0.3  # 300ms per tool call

class PerformanceTest:
    def __init__(self):
        self.cache = {}
    
    # Original sequential implementation
    def execute_task_sequential(self, prompt: str, tools: List[str]) -> Dict[str, Any]:
        """Original sequential execution"""
        start_time = time.time()
        
        # LLM call
        response = self._simulate_llm_call(prompt)
        
        # Execute tools one by one
        tool_results = []
        for tool in tools:
            result = self._simulate_tool_call(tool)
            tool_results.append(result)
        
        end_time = time.time()
        return {
            "response": response,
            "tool_results": tool_results,
            "execution_time": end_time - start_time
        }
    
    # Optimized with caching
    def execute_task_with_cache(self, prompt: str, tools: List[str]) -> Dict[str, Any]:
        """Execution with caching"""
        start_time = time.time()
        
        # Check cache for LLM response
        cache_key = f"{prompt}:{','.join(tools)}"
        if cache_key in self.cache:
            response = self.cache[cache_key]["response"]
            tool_results = self.cache[cache_key]["tool_results"]
            print("  [CACHE HIT] Returning cached result")
        else:
            # LLM call
            response = self._simulate_llm_call(prompt)
            
            # Execute tools
            tool_results = []
            for tool in tools:
                result = self._simulate_tool_call(tool)
                tool_results.append(result)
            
            # Store in cache
            self.cache[cache_key] = {
                "response": response,
                "tool_results": tool_results
            }
        
        end_time = time.time()
        return {
            "response": response,
            "tool_results": tool_results,
            "execution_time": end_time - start_time
        }
    
    # Optimized with parallel execution
    async def execute_task_parallel(self, prompt: str, tools: List[str]) -> Dict[str, Any]:
        """Parallel execution of tools"""
        start_time = time.time()
        
        # LLM call
        response = await self._async_simulate_llm_call(prompt)
        
        # Execute tools in parallel
        tool_tasks = [self._async_simulate_tool_call(tool) for tool in tools]
        tool_results = await asyncio.gather(*tool_tasks)
        
        end_time = time.time()
        return {
            "response": response,
            "tool_results": tool_results,
            "execution_time": end_time - start_time
        }
    
    # Fully optimized with both caching and parallel execution
    async def execute_task_optimized(self, prompt: str, tools: List[str]) -> Dict[str, Any]:
        """Fully optimized execution"""
        start_time = time.time()
        
        # Check cache
        cache_key = f"{prompt}:{','.join(tools)}"
        if cache_key in self.cache:
            response = self.cache[cache_key]["response"]
            tool_results = self.cache[cache_key]["tool_results"]
            print("  [CACHE HIT] Returning cached result")
        else:
            # LLM call
            response = await self._async_simulate_llm_call(prompt)
            
            # Execute tools in parallel
            tool_tasks = [self._async_simulate_tool_call(tool) for tool in tools]
            tool_results = await asyncio.gather(*tool_tasks)
            
            # Store in cache
            self.cache[cache_key] = {
                "response": response,
                "tool_results": tool_results
            }
        
        end_time = time.time()
        return {
            "response": response,
            "tool_results": tool_results,
            "execution_time": end_time - start_time
        }
    
    def _simulate_llm_call(self, prompt: str) -> str:
        """Simulate LLM API call with delay"""
        time.sleep(SIMULATED_LLM_DELAY)
        return f"Response to: {prompt}"
    
    def _simulate_tool_call(self, tool: str) -> str:
        """Simulate tool execution with delay"""
        time.sleep(SIMULATED_TOOL_DELAY)
        return f"Result from {tool}"
    
    async def _async_simulate_llm_call(self, prompt: str) -> str:
        """Async simulate LLM API call"""
        await asyncio.sleep(SIMULATED_LLM_DELAY)
        return f"Response to: {prompt}"
    
    async def _async_simulate_tool_call(self, tool: str) -> str:
        """Async simulate tool execution"""
        await asyncio.sleep(SIMULATED_TOOL_DELAY)
        return f"Result from {tool}"


async def run_performance_tests():
    """Run performance comparison tests"""
    test = PerformanceTest()
    prompt = "Analyze the data and create a report"
    tools = ["web_search", "calculator", "file_reader", "data_analyzer"]
    
    print("PraisonAI Agents Performance Test")
    print("=" * 50)
    print(f"Test scenario: 1 LLM call + {len(tools)} tool calls")
    print(f"Simulated LLM delay: {SIMULATED_LLM_DELAY}s")
    print(f"Simulated tool delay: {SIMULATED_TOOL_DELAY}s per tool")
    print("=" * 50)
    
    # Test 1: Original sequential execution
    print("\n1. ORIGINAL (Sequential execution):")
    result1 = test.execute_task_sequential(prompt, tools)
    print(f"  Execution time: {result1['execution_time']:.2f}s")
    
    # Test 2: With caching (first call)
    print("\n2. WITH CACHING (First call - cache miss):")
    result2 = test.execute_task_with_cache(prompt, tools)
    print(f"  Execution time: {result2['execution_time']:.2f}s")
    
    # Test 3: With caching (second call)
    print("\n3. WITH CACHING (Second call - cache hit):")
    result3 = test.execute_task_with_cache(prompt, tools)
    print(f"  Execution time: {result3['execution_time']:.2f}s")
    print(f"  Speedup: {result1['execution_time'] / result3['execution_time']:.1f}x faster")
    
    # Test 4: Parallel execution
    print("\n4. PARALLEL EXECUTION (No cache):")
    result4 = await test.execute_task_parallel(prompt, tools)
    print(f"  Execution time: {result4['execution_time']:.2f}s")
    print(f"  Speedup: {result1['execution_time'] / result4['execution_time']:.1f}x faster")
    
    # Test 5: Fully optimized (parallel + cache, first call)
    print("\n5. FULLY OPTIMIZED (Parallel + Cache, first call):")
    test.cache.clear()  # Clear cache for fair comparison
    result5 = await test.execute_task_optimized(prompt, tools)
    print(f"  Execution time: {result5['execution_time']:.2f}s")
    
    # Test 6: Fully optimized (parallel + cache, cached)
    print("\n6. FULLY OPTIMIZED (Parallel + Cache, cache hit):")
    result6 = await test.execute_task_optimized(prompt, tools)
    print(f"  Execution time: {result6['execution_time']:.2f}s")
    print(f"  Speedup: {result1['execution_time'] / result6['execution_time']:.1f}x faster")
    
    # Summary
    print("\n" + "=" * 50)
    print("PERFORMANCE SUMMARY:")
    print("=" * 50)
    theoretical_sequential = SIMULATED_LLM_DELAY + (SIMULATED_TOOL_DELAY * len(tools))
    theoretical_parallel = SIMULATED_LLM_DELAY + SIMULATED_TOOL_DELAY
    
    print(f"Theoretical sequential time: {theoretical_sequential:.2f}s")
    print(f"Theoretical parallel time: {theoretical_parallel:.2f}s")
    print(f"Theoretical speedup from parallelization: {theoretical_sequential / theoretical_parallel:.1f}x")
    print(f"\nActual results:")
    print(f"  - Caching alone: {result1['execution_time'] / result3['execution_time']:.1f}x speedup")
    print(f"  - Parallel alone: {result1['execution_time'] / result4['execution_time']:.1f}x speedup")
    print(f"  - Both optimizations: {result1['execution_time'] / result6['execution_time']:.1f}x speedup")
    
    # Real-world impact
    print("\n" + "=" * 50)
    print("REAL-WORLD IMPACT:")
    print("=" * 50)
    print("For a workflow with 10 similar tasks:")
    workflow_original = result1['execution_time'] * 10
    workflow_optimized = result5['execution_time'] + (result6['execution_time'] * 9)  # 1 miss + 9 hits
    
    print(f"  - Original time: {workflow_original:.1f}s")
    print(f"  - Optimized time: {workflow_optimized:.1f}s")
    print(f"  - Time saved: {workflow_original - workflow_optimized:.1f}s ({(1 - workflow_optimized/workflow_original) * 100:.0f}%)")
    print(f"  - Overall speedup: {workflow_original / workflow_optimized:.1f}x faster")


if __name__ == "__main__":
    asyncio.run(run_performance_tests())
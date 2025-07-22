"""
Async Agent with Performance Monitoring - Example 4

Demonstrates performance monitoring for asynchronous agent operations:
- Async function execution timing
- Concurrent task performance
- Async API call tracking
- Parallel operation analysis

Shows how to monitor performance in async/await workflows.
"""

import asyncio
import time
from praisonaiagents import Agent
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, get_performance_report,
    get_function_stats, visualize_execution_flow
)

@monitor_function("async_data_processing")
async def process_data_async(data_id: int):
    """Async data processing with performance monitoring."""
    print(f"⚙️ Processing data {data_id} asynchronously...")
    await asyncio.sleep(0.1)  # Simulate async processing
    return f"Processed data {data_id}"

@monitor_function("async_api_call")
async def simulate_api_call(endpoint: str, delay: float = 0.2):
    """Simulate async API call with performance monitoring."""
    print(f"🌐 Calling API endpoint: {endpoint}")
    await asyncio.sleep(delay)  # Simulate network delay
    return f"Response from {endpoint}"

@monitor_function("batch_processing")
async def process_batch(batch_size: int = 3):
    """Process multiple items concurrently with monitoring."""
    print(f"📦 Processing batch of {batch_size} items...")
    
    # Create concurrent tasks
    tasks = []
    for i in range(batch_size):
        tasks.append(process_data_async(i + 1))
    
    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks)
    print(f"✅ Batch processing completed: {len(results)} items processed")
    return results

@monitor_function("async_agent_execution")
async def run_async_agent(query: str):
    """Run agent with async operations and monitoring."""
    
    # Create agent
    agent = Agent(
        instructions="You are an efficient AI assistant that processes requests quickly",
        llm="gpt-4o-mini"
    )
    
    # Track the agent execution
    with track_api_call("async_agent_request"):
        print(f"🚀 Running async agent for query: {query}")
        
        # For demo purposes, we simulate async agent execution
        # In real scenarios, you'd use agent.astart() or similar async method when available
        await asyncio.sleep(0.1)  # Simulate async processing time
        result = agent.start(query)
        
        # Simulate some async post-processing
        await asyncio.sleep(0.05)
        
        return result

@monitor_function("concurrent_agents")
async def run_concurrent_agents():
    """Run multiple agents concurrently with monitoring."""
    print("🔄 Running multiple agents concurrently...")
    
    queries = [
        "What is machine learning?",
        "Explain quantum computing",
        "How does blockchain work?"
    ]
    
    # Create concurrent agent tasks
    agent_tasks = []
    for i, query in enumerate(queries):
        task = run_async_agent(query)
        agent_tasks.append(task)
    
    # Execute all agents concurrently  
    results = await asyncio.gather(*agent_tasks)
    return results

async def main():
    """Main async function demonstrating async agent performance monitoring."""
    print("=" * 70)
    print("EXAMPLE 4: Async Agent Performance Monitoring")
    print("=" * 70)
    
    start_time = time.time()
    
    # Run async operations with monitoring
    print("\n📊 Phase 1: Batch Processing")
    batch_results = await process_batch(3)
    
    print("\n🌐 Phase 2: API Calls")
    api_tasks = [
        simulate_api_call("user-service", 0.1),
        simulate_api_call("data-service", 0.15),
        simulate_api_call("analytics-service", 0.2)
    ]
    api_results = await asyncio.gather(*api_tasks)
    
    print("\n🤖 Phase 3: Concurrent Agents")
    agent_results = await run_concurrent_agents()
    
    total_time = time.time() - start_time
    
    # Performance Analysis
    print("\n" + "=" * 70)
    print("📊 ASYNC PERFORMANCE ANALYSIS")
    print("=" * 70)
    
    print(f"\n⏱️ Total Execution Time: {total_time:.3f}s")
    
    # Function statistics
    print("\n📈 Function Performance:")
    stats = get_function_stats()
    for func_name, data in stats.items():
        avg_time = data['total_time'] / data['call_count'] if data['call_count'] > 0 else 0
        print(f"  {func_name}:")
        print(f"    Calls: {data['call_count']}")
        print(f"    Avg Time: {avg_time:.3f}s")
        print(f"    Total Time: {data['total_time']:.3f}s")
    
    # Execution flow visualization
    print("\n🔄 Execution Flow:")
    try:
        flow_viz = visualize_execution_flow()
        print("  Flow visualization generated successfully")
        print(f"  Flow data length: {len(str(flow_viz))}")
    except Exception as e:
        print(f"  Flow visualization: {str(e)}")
    
    # Performance report
    print("\n📋 Performance Report:")
    report = get_performance_report()
    print(report[:300] + "..." if len(report) > 300 else report)
    
    # Results summary
    print(f"\n✅ Results Summary:")
    print(f"  Batch items processed: {len(batch_results)}")
    print(f"  API calls completed: {len(api_results)}")
    print(f"  Agent queries processed: {len(agent_results)}")
    
    return {
        'batch_results': batch_results,
        'api_results': api_results,
        'agent_results': agent_results,
        'total_time': total_time
    }

if __name__ == "__main__":
    # Run the async main function
    result = asyncio.run(main())
    print(f"\n🎉 Async monitoring example completed successfully!")
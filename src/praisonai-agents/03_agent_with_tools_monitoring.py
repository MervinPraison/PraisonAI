"""
Agent with Tools Performance Monitoring - Example 3

Demonstrates performance monitoring for agents using tools:
- Tool execution timing
- Search operation performance
- Tool call success/failure tracking
- Tool usage analysis

Shows how to monitor agent performance when using external tools.
"""

from praisonaiagents import Agent
from praisonaiagents.tools import duckduckgo, wikipedia
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, get_api_stats,
    get_slowest_functions, performance_monitor
)
import time

@monitor_function("search_with_duckduckgo")
def perform_web_search(query):
    """Perform web search with performance monitoring."""
    print(f"🔍 Searching web for: {query}")
    with track_api_call("duckduckgo_search"):
        # Simulate search time
        time.sleep(0.2)
        return f"Search results for: {query}"

@monitor_function("wikipedia_lookup") 
def perform_wikipedia_search(topic):
    """Perform Wikipedia search with performance monitoring."""
    print(f"📚 Looking up Wikipedia for: {topic}")
    with track_api_call("wikipedia_search"):
        # Simulate Wikipedia lookup
        time.sleep(0.15)
        return f"Wikipedia information about: {topic}"

@monitor_function("agent_with_tools_execution")
def main():
    """Main function demonstrating agent with tools and performance monitoring."""
    print("=" * 70)
    print("EXAMPLE 3: Agent with Tools Performance Monitoring")
    print("=" * 70)
    
    # Create agent with tools
    agent = Agent(
        instructions="""You are a research assistant that helps find information.
        Use the available tools to search for information and provide comprehensive answers.
        Be thorough in your research and cite your sources.""",
        llm="gpt-5-nano",
        tools=[duckduckgo, wikipedia]  # Add search tools
    )
    
    # Test queries to demonstrate tool performance monitoring
    queries = [
        "What are the latest developments in artificial intelligence?",
        "Tell me about renewable energy innovations in 2024",
        "How do neural networks work?"
    ]
    
    results = []
    
    for i, query in enumerate(queries, 1):
        print(f"\n🎯 Query {i}: {query}")
        
        # Monitor the search operations
        perform_web_search(query)
        perform_wikipedia_search(query)
        
        # Track the full agent execution
        with track_api_call(f"agent_query_{i}"):
            print(f"\n🚀 Processing with agent...")
            
            # Note: In a real implementation, the agent would use the tools automatically
            # For demo purposes, we're simulating the tool usage
            result = agent.start(f"Research and answer: {query}")
            results.append(result)
            
            print(f"📝 Agent Response: {result[:200]}..." if len(result) > 200 else f"📝 Agent Response: {result}")
    
    # Performance Analysis
    print("\n" + "=" * 70)
    print("📊 TOOLS PERFORMANCE ANALYSIS")
    print("=" * 70)
    
    # API call statistics
    print("\n📈 API Call Performance:")
    api_stats = get_api_stats()
    for api_name, stats in api_stats.items():
        print(f"  {api_name}:")
        print(f"    Total Calls: {stats['call_count']}")
        print(f"    Avg Response Time: {stats['total_time']/stats['call_count']:.3f}s")
        print(f"    Success Rate: {stats['success_count']/stats['call_count']*100:.1f}%")
        print(f"    Total Time: {stats['total_time']:.3f}s")
    
    # Slowest functions analysis
    print("\n🐌 Slowest Functions:")
    slowest = get_slowest_functions()
    for func_name, avg_time in slowest:
        print(f"  {func_name}: {avg_time:.3f}s average")
    
    # Real-time performance data
    print("\n⚡ Real-time Performance Data:")
    current_stats = performance_monitor.get_function_performance()
    print(f"  Functions Monitored: {len(current_stats)}")
    
    total_function_calls = sum(stats['call_count'] for stats in current_stats.values())
    total_execution_time = sum(stats['total_time'] for stats in current_stats.values())
    
    print(f"  Total Function Calls: {total_function_calls}")
    print(f"  Total Execution Time: {total_execution_time:.3f}s")
    print(f"  Average Time per Call: {total_execution_time/total_function_calls:.3f}s" if total_function_calls > 0 else "  No calls recorded")
    
    return results

if __name__ == "__main__":
    results = main()
    print(f"\n✅ Tool monitoring example completed! Processed {len(results)} queries.")
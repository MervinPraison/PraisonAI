"""
Custom Tools with Performance Monitoring - Example 8

Demonstrates performance monitoring for agents using custom tools:
- Custom tool execution timing
- Tool creation and registration performance
- Tool usage pattern analysis
- Tool efficiency optimization

Shows how to monitor performance with custom-built tools.
"""

import time
import json
import random
from praisonaiagents import Agent, tool
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, get_function_stats,
    get_slowest_functions, performance_monitor
)

# Custom Tool 1: Data Processor
@tool
@monitor_function("data_processor_tool")
def process_data(data: str, operation: str = "analyze") -> str:
    """
    Process data with specified operation.
    
    Args:
        data: The data to process
        operation: Type of operation (analyze, transform, validate)
    """
    print(f"🔧 Processing data with operation: {operation}")
    
    # Simulate different processing times based on operation
    processing_times = {
        "analyze": 0.15,
        "transform": 0.2, 
        "validate": 0.1
    }
    
    time.sleep(processing_times.get(operation, 0.12))
    
    return f"Data processed with {operation}: {data[:50]}{'...' if len(data) > 50 else ''}"

# Custom Tool 2: API Simulator
@tool
@monitor_function("api_simulator_tool")
def call_external_api(endpoint: str, method: str = "GET", payload: str = "") -> str:
    """
    Simulate calling an external API.
    
    Args:
        endpoint: API endpoint to call
        method: HTTP method (GET, POST, PUT, DELETE)
        payload: Request payload for POST/PUT
    """
    print(f"🌐 Calling API: {method} {endpoint}")
    
    # Simulate variable API response times
    base_time = 0.1
    if method == "POST":
        base_time += 0.05
    if payload:
        base_time += len(payload) * 0.001
    
    # Add random variation
    response_time = base_time + random.uniform(0, 0.1)
    time.sleep(response_time)
    
    # Simulate occasional API failures
    if random.random() < 0.1:  # 10% failure rate
        raise Exception(f"API call to {endpoint} failed")
    
    return f"API Response from {endpoint}: {{'status': 'success', 'method': '{method}'}}"

# Custom Tool 3: Database Simulator
@tool 
@monitor_function("database_simulator_tool")
def query_database(query: str, database: str = "main") -> str:
    """
    Simulate database query execution.
    
    Args:
        query: SQL query to execute
        database: Database name to query
    """
    print(f"🗄️ Executing database query on {database}")
    
    # Simulate query complexity based on keywords
    complexity_keywords = {
        "JOIN": 0.08,
        "GROUP BY": 0.06,
        "ORDER BY": 0.04,
        "WHERE": 0.03
    }
    
    query_time = 0.05  # Base query time
    for keyword, additional_time in complexity_keywords.items():
        if keyword in query.upper():
            query_time += additional_time
    
    time.sleep(query_time)
    
    return f"Query executed on {database}: Found {random.randint(1, 100)} results"

# Custom Tool 4: File Operations
@tool
@monitor_function("file_operations_tool")  
def file_operation(operation: str, filename: str, content: str = "") -> str:
    """
    Simulate file operations.
    
    Args:
        operation: Operation type (read, write, delete, copy)
        filename: Target filename
        content: Content for write operations
    """
    print(f"📁 File operation: {operation} on {filename}")
    
    # Simulate different operation times
    operation_times = {
        "read": 0.03,
        "write": 0.05,
        "delete": 0.02,
        "copy": 0.07
    }
    
    time.sleep(operation_times.get(operation, 0.04))
    
    if operation == "write" and content:
        time.sleep(len(content) * 0.0001)  # Simulate write time based on content size
    
    return f"File {operation} completed for {filename}"

@monitor_function("tool_performance_test")
def test_tool_performance():
    """Test individual tool performance."""
    print("🧪 Testing individual tool performance...")
    
    # Test each tool multiple times
    tools_results = []
    
    # Test data processor
    for op in ["analyze", "transform", "validate"]:
        result = process_data("Sample data for testing", op)
        tools_results.append(f"DataProcessor[{op}]: {result}")
    
    # Test API simulator
    for method in ["GET", "POST"]:
        try:
            result = call_external_api("/api/test", method, "test payload" if method == "POST" else "")
            tools_results.append(f"APISimulator[{method}]: {result}")
        except Exception as e:
            tools_results.append(f"APISimulator[{method}]: Failed - {e}")
    
    # Test database operations
    queries = [
        "SELECT * FROM users",
        "SELECT COUNT(*) FROM orders WHERE date > '2024-01-01'",
        "SELECT u.name, COUNT(o.id) FROM users u JOIN orders o GROUP BY u.id"
    ]
    
    for query in queries:
        result = query_database(query)
        tools_results.append(f"Database: {result}")
    
    # Test file operations
    for op in ["read", "write", "copy"]:
        result = file_operation(op, "test_file.txt", "Test content" if op == "write" else "")
        tools_results.append(f"FileOps[{op}]: {result}")
    
    return tools_results

@monitor_function("agent_with_custom_tools")
def run_agent_with_custom_tools():
    """Run agent using custom tools with performance monitoring."""
    
    # Create agent with custom tools
    agent = Agent(
        instructions="""You are a technical assistant with access to various tools.
        Use the appropriate tools to help with data processing, API calls, database queries,
        and file operations. Always explain what tools you're using and why.""",
        llm="gpt-4o-mini",
        tools=[process_data, call_external_api, query_database, file_operation]
    )
    
    # Test scenarios for the agent
    scenarios = [
        "I need to analyze some customer data and store the results",
        "Please fetch user information from the API and save it to a file",
        "Query the database for recent orders and process the results"
    ]
    
    results = []
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n🎯 Scenario {i}: {scenario}")
        
        with track_api_call(f"custom_tools_scenario_{i}"):
            try:
                result = agent.start(scenario)
                results.append(result)
                print(f"✅ Scenario {i} completed")
            except Exception as e:
                print(f"❌ Scenario {i} failed: {e}")
                results.append(f"Failed: {e}")
    
    return results

def main():
    """Main function demonstrating custom tools performance monitoring."""
    print("=" * 70)
    print("EXAMPLE 8: Custom Tools Performance Monitoring")
    print("=" * 70)
    
    # Phase 1: Individual tool performance testing
    print("\n🔧 Phase 1: Individual Tool Performance Testing")
    tool_test_results = test_tool_performance()
    
    print(f"\n📊 Tool Test Summary:")
    print(f"  Total tool operations: {len(tool_test_results)}")
    for result in tool_test_results[:5]:  # Show first 5 results
        print(f"  - {result}")
    if len(tool_test_results) > 5:
        print(f"  ... and {len(tool_test_results) - 5} more")
    
    # Phase 2: Agent using custom tools
    print("\n🤖 Phase 2: Agent with Custom Tools")
    agent_results = run_agent_with_custom_tools()
    
    # Performance Analysis
    print("\n" + "=" * 70)
    print("📊 CUSTOM TOOLS PERFORMANCE ANALYSIS")
    print("=" * 70)
    
    # Tool-specific performance
    print("\n🔧 Tool Performance Breakdown:")
    stats = get_function_stats()
    tool_functions = {k: v for k, v in stats.items() if 'tool' in k.lower()}
    
    for tool_name, data in tool_functions.items():
        avg_time = data['total_time'] / data['call_count'] if data['call_count'] > 0 else 0
        print(f"  {tool_name}:")
        print(f"    Calls: {data['call_count']}")
        print(f"    Avg Time: {avg_time:.3f}s")
        print(f"    Total Time: {data['total_time']:.3f}s")
        if data['error_count'] > 0:
            print(f"    Errors: {data['error_count']}")
    
    # Tool efficiency ranking
    print("\n🏆 Tool Efficiency Ranking (by average execution time):")
    tool_efficiency = []
    for tool_name, data in tool_functions.items():
        if data['call_count'] > 0:
            avg_time = data['total_time'] / data['call_count']
            tool_efficiency.append((tool_name, avg_time))
    
    tool_efficiency.sort(key=lambda x: x[1])
    
    for rank, (tool_name, avg_time) in enumerate(tool_efficiency, 1):
        print(f"  {rank}. {tool_name}: {avg_time:.3f}s")
    
    # Slowest operations
    print("\n🐌 Slowest Tool Operations:")
    slowest = get_slowest_functions()
    tool_slowest = [(name, time) for name, time in slowest if 'tool' in name.lower()]
    
    for tool_name, avg_time in tool_slowest[:3]:
        print(f"  {tool_name}: {avg_time:.3f}s")
    
    # Usage patterns
    total_tool_calls = sum(data['call_count'] for data in tool_functions.values())
    total_tool_time = sum(data['total_time'] for data in tool_functions.values())
    
    print(f"\n📈 Tool Usage Summary:")
    print(f"  Total Tool Calls: {total_tool_calls}")
    print(f"  Total Tool Execution Time: {total_tool_time:.3f}s")
    print(f"  Average Time per Tool Call: {total_tool_time/total_tool_calls:.3f}s" if total_tool_calls > 0 else "  No tool calls")
    
    # Tool reliability
    total_tool_errors = sum(data['error_count'] for data in tool_functions.values())
    reliability = ((total_tool_calls - total_tool_errors) / total_tool_calls * 100) if total_tool_calls > 0 else 100
    
    print(f"  Tool Reliability: {reliability:.1f}%")
    if total_tool_errors > 0:
        print(f"  Total Errors: {total_tool_errors}")
    
    # Optimization recommendations
    print(f"\n💡 Custom Tools Optimization Recommendations:")
    
    if tool_efficiency:
        slowest_tool = tool_efficiency[-1]
        if slowest_tool[1] > 0.2:
            print(f"  - Optimize {slowest_tool[0]} (slowest at {slowest_tool[1]:.3f}s)")
    
    if total_tool_errors > 0:
        print(f"  - Investigate {total_tool_errors} tool errors for stability improvements")
    
    if total_tool_calls > 20:
        print("  - Consider tool caching for frequently used operations")
    
    print("  - Monitor tool usage patterns for optimization opportunities")
    
    return {
        'tool_operations': len(tool_test_results),
        'agent_scenarios': len(agent_results),
        'total_tool_calls': total_tool_calls,
        'tool_reliability': reliability
    }

if __name__ == "__main__":
    result = main()
    print(f"\n✅ Custom tools monitoring completed!")
    print(f"Operations: {result['tool_operations']}, Reliability: {result['tool_reliability']:.1f}%")
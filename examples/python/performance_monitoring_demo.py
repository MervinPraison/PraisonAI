"""
PraisonAI Performance Monitoring Demo

This example demonstrates how to use PraisonAI's comprehensive performance monitoring
capabilities to answer the key questions from Issue #1035:

1. How to evaluate how each function is performing
2. Function flow analysis  
3. How fast each function is executing
4. API call performance monitoring (fast vs slow calls)
5. How to see all API calls

Features Demonstrated:
- Function performance evaluation with detailed statistics
- Function execution flow analysis and visualization
- API call tracking and performance comparison
- Real-time performance monitoring
- Bottleneck identification and optimization recommendations
- Comprehensive performance reporting
"""

import time
import random
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, performance_monitor,
    analyze_function_flow,
    visualize_execution_flow, generate_comprehensive_report
)

print("=" * 80)
print("PRAISONAI PERFORMANCE MONITORING DEMONSTRATION")
print("=" * 80)
print("This demo answers the key questions from Issue #1035:")
print("1. How to evaluate how each function is performing")
print("2. Function flow analysis")  
print("3. How fast each function is executing")
print("4. API call performance monitoring (fast vs slow calls)")
print("5. How to see all API calls")
print("=" * 80)
print()

# Example 1: Function Performance Evaluation
print("📊 EXAMPLE 1: Function Performance Evaluation")
print("-" * 50)

# Demonstrate function monitoring with decorators
@monitor_function("data_processing")
def process_data(data_size: int):
    """Simulate data processing with variable performance."""
    processing_time = 0.1 + (data_size * 0.01)  # Simulate work
    time.sleep(processing_time)
    return f"Processed {data_size} items"

@monitor_function("model_inference") 
def run_model_inference(complexity: str):
    """Simulate model inference with different complexities."""
    if complexity == "simple":
        time.sleep(0.05)
    elif complexity == "medium": 
        time.sleep(0.2)
    else:  # complex
        time.sleep(0.5)
    return f"Inference completed for {complexity} model"

@monitor_function("database_query")
def query_database(query_type: str):
    """Simulate database queries with different performance characteristics."""
    if query_type == "fast":
        time.sleep(0.02)
    elif query_type == "medium":
        time.sleep(0.1) 
    else:  # slow
        time.sleep(0.3)
    return f"Query {query_type} completed"

# Run functions with different performance characteristics
print("Running functions to generate performance data...")
for _ in range(5):
    process_data(random.randint(10, 100))
    run_model_inference(random.choice(["simple", "medium", "complex"]))
    query_database(random.choice(["fast", "medium", "slow"]))

# Show function performance statistics
print("\n📈 Function Performance Statistics:")
function_stats = performance_monitor.get_function_performance()
for func_name, stats in function_stats.items():
    print(f"\n🔧 {func_name}:")
    print(f"  Calls: {stats['call_count']}")
    print(f"  Average Time: {stats.get('average_time', 0):.3f}s")
    print(f"  Min/Max Time: {stats['min_time']:.3f}s / {stats['max_time']:.3f}s")
    print(f"  Success Rate: {stats.get('success_rate', 0)*100:.1f}%")

# Example 2: Function Flow Analysis
print("\n\n🔄 EXAMPLE 2: Function Flow Analysis") 
print("-" * 50)

@monitor_function("workflow_step_1")
def workflow_step_1():
    time.sleep(0.1)
    workflow_step_2()
    workflow_step_3()

@monitor_function("workflow_step_2") 
def workflow_step_2():
    time.sleep(0.05)
    workflow_step_4()

@monitor_function("workflow_step_3")
def workflow_step_3():
    time.sleep(0.08)

@monitor_function("workflow_step_4")
def workflow_step_4():
    time.sleep(0.03)

print("Running workflow to demonstrate flow analysis...")
workflow_step_1()

# Analyze execution flow
print("\n📊 Function Execution Flow Analysis:")
flow_analysis = analyze_function_flow()
if "bottlenecks" in flow_analysis:
    bottlenecks = flow_analysis["bottlenecks"]
    if bottlenecks:
        print("🚨 Identified Bottlenecks:")
        for bottleneck in bottlenecks:
            print(f"  • {bottleneck['function']}: {bottleneck['average_duration']:.3f}s average")
    else:
        print("✅ No significant bottlenecks identified")

# Visualize execution flow
print("\n🎨 Function Execution Flow Visualization:")
flow_viz = visualize_execution_flow(format="text")
print(flow_viz)

# Example 3: API Call Performance Monitoring
print("\n\n🌐 EXAMPLE 3: API Call Performance Monitoring")
print("-" * 50)

# Simulate different API calls with various performance characteristics
def simulate_api_calls():
    """Simulate API calls to demonstrate tracking."""
    
    # Fast API calls
    with track_api_call("openai_api", "/v1/models"):
        time.sleep(0.05)  # Fast call
    
    with track_api_call("openai_api", "/v1/chat/completions"):
        time.sleep(0.3)  # Medium call
    
    # Slow API call
    with track_api_call("anthropic_api", "/v1/messages"):
        time.sleep(0.6)  # Slow call
    
    # Another fast call
    with track_api_call("gemini_api", "/v1/generate"):
        time.sleep(0.08)  # Fast call
    
    # Simulate error case
    try:
        with track_api_call("unreliable_api", "/v1/endpoint"):
            time.sleep(0.2)
            if random.random() < 0.3:  # 30% chance of error
                raise Exception("API Error")
    except Exception:
        pass  # Error is already tracked

print("Simulating API calls with different performance characteristics...")
for _ in range(8):
    simulate_api_calls()

# Show API performance statistics
print("\n📊 API Call Performance Statistics:")
api_stats = performance_monitor.get_api_call_performance()
for api_name, stats in api_stats.items():
    print(f"\n🔗 {api_name}:")
    print(f"  Total Calls: {stats['call_count']}")
    print(f"  Average Time: {stats.get('average_time', 0):.3f}s")
    print(f"  Min/Max Time: {stats['min_time']:.3f}s / {stats['max_time']:.3f}s")
    print(f"  Success Rate: {stats.get('success_rate', 0)*100:.1f}%")
    print(f"  Successful: {stats['success_count']} | Failed: {stats['error_count']}")

# Show fastest vs slowest APIs
print("\n🏁 Fastest vs Slowest API Calls:")
slowest_apis = performance_monitor.get_slowest_api_calls(10)
for i, api in enumerate(slowest_apis, 1):
    speed_indicator = "🐌" if api['average_time'] > 0.3 else "⚡" if api['average_time'] < 0.1 else "🚀"
    print(f"{i}. {speed_indicator} {api['api']}: {api['average_time']:.3f}s avg (Success: {api['success_rate']*100:.1f}%)")

# Example 4: Real-time Performance Monitoring with Agents
print("\n\n🤖 EXAMPLE 4: Real-time Performance Monitoring with AI Agents")
print("-" * 50)

# Create agents with performance monitoring
research_agent = Agent(
    name="PerformanceResearcher",
    role="Performance Research Specialist",
    goal="Research and analyze performance topics quickly",
    backstory="You are an expert at researching performance optimization topics.",
    tools=[duckduckgo],
    verbose=False  # Reduce output for cleaner demo
)

# Monitor agent operations
@monitor_function("agent_task_execution")
def execute_monitored_task(agent, task_description):
    """Execute an agent task with performance monitoring."""
    task = Task(
        description=task_description,
        expected_output="Brief research summary with key insights",
        agent=agent
    )
    
    agents_workflow = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        verbose=False
    )
    
    # Simulate API calls during agent execution
    with track_api_call("llm_provider", "/v1/chat/completions"):
        time.sleep(0.2)  # Simulate LLM call
    
    result = agents_workflow.start()
    return result

print("Running AI agent with performance monitoring...")
result = execute_monitored_task(
    research_agent, 
    "Research the latest trends in AI performance optimization"
)

# Example 5: Comprehensive Performance Report
print("\n\n📋 EXAMPLE 5: Comprehensive Performance Report")
print("-" * 50)

# Generate comprehensive performance report
comprehensive_report = generate_comprehensive_report()
print(comprehensive_report)

# Example 6: Using CLI Interface Programmatically
print("\n\n💻 EXAMPLE 6: CLI Interface Usage")
print("-" * 50)
print("You can also use the CLI interface from command line:")
print()
print("# Show performance report")
print("python -m praisonaiagents.telemetry.performance_cli report")
print()
print("# Show function statistics")  
print("python -m praisonaiagents.telemetry.performance_cli functions")
print()
print("# Show API call statistics")
print("python -m praisonaiagents.telemetry.performance_cli apis")
print()
print("# Show slowest functions")
print("python -m praisonaiagents.telemetry.performance_cli slowest-functions 5")
print()
print("# Analyze function flow") 
print("python -m praisonaiagents.telemetry.performance_cli analyze-flow")
print()
print("# Show execution flow visualization")
print("python -m praisonaiagents.telemetry.performance_cli flow --format text")
print()
print("# Export all data to JSON")
print("python -m praisonaiagents.telemetry.performance_cli export --format json --output performance_data.json")

# Example 7: Integration with Existing Code
print("\n\n🔧 EXAMPLE 7: Easy Integration with Existing Code")  
print("-" * 50)
print("To integrate performance monitoring into your existing PraisonAI code:")
print()
print("1. Import the performance monitoring tools:")
print("   from praisonaiagents.telemetry import monitor_function, track_api_call")
print()
print("2. Add decorators to your functions:")
print("   @monitor_function('my_function')")
print("   def my_function():")
print("       return 'result'")
print()
print("3. Track API calls:")
print("   with track_api_call('openai', '/v1/chat/completions'):")
print("       response = openai_client.chat.completions.create(...)")
print()
print("4. Get performance reports:")
print("   from praisonaiagents.telemetry import get_performance_report")
print("   print(get_performance_report())")

# Summary of capabilities
print("\n\n✅ SUMMARY: Questions from Issue #1035 - ANSWERED!")
print("=" * 80)
print("1. ✅ How to evaluate how each function is performing:")
print("   → Use @monitor_function decorator and get_function_stats()")
print("   → View detailed statistics: calls, timing, success rates, errors")
print()
print("2. ✅ Function flow analysis:")
print("   → Use analyze_function_flow() for bottleneck identification") 
print("   → Use visualize_execution_flow() for flow visualization")
print("   → Get call chains and execution patterns")
print()
print("3. ✅ How fast each function is executing:")
print("   → Automatic timing collection with min/max/average/recent stats")
print("   → Use get_slowest_functions() to find performance bottlenecks")
print("   → Real-time active call monitoring")
print()
print("4. ✅ API call performance monitoring (fast vs slow calls):")
print("   → Use track_api_call() context manager for API monitoring")
print("   → Compare API performance with get_slowest_apis()")
print("   → Success/error rate tracking")
print()
print("5. ✅ How to see all API calls:")
print("   → Use get_api_stats() to see all tracked APIs")
print("   → View recent call history and detailed metrics")
print("   → CLI interface for easy access: performance_cli apis")
print()
print("🎉 All requested features are now available with backward compatibility!")
print("🔧 Easy integration with existing code using decorators and context managers")
print("📊 Comprehensive reporting and analysis capabilities") 
print("💻 CLI interface for command-line access")
print("=" * 80)
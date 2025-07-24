"""
Comprehensive Performance Dashboard - Example 10

Demonstrates comprehensive performance monitoring dashboard:
- Complete performance analytics
- Advanced reporting and visualization
- Performance trends and insights
- System-wide monitoring overview

Shows how to create a comprehensive performance monitoring solution.
"""

import time
import json
from datetime import datetime, timedelta
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, performance_monitor,
    get_performance_report, get_function_stats, get_api_stats,
    get_slowest_functions, get_slowest_apis, 
    analyze_function_flow, visualize_execution_flow,
    analyze_performance_trends, generate_comprehensive_report,
    clear_performance_data
)

@monitor_function("dashboard_data_collection")
def collect_comprehensive_data():
    """Collect comprehensive performance data for dashboard."""
    
    print("📊 Collecting comprehensive performance data...")
    
    # Generate diverse workload for demonstration
    test_scenarios = [
        ("Quick query", "What is AI?"),
        ("Complex analysis", "Analyze the impact of artificial intelligence on modern business practices"),
        ("Research task", "Research the latest developments in quantum computing"),
        ("Creative task", "Write a creative story about space exploration"),
        ("Technical query", "Explain how neural networks process information")
    ]
    
    # Create different types of agents for variety
    agents = {
        'quick_agent': Agent(
            instructions="You are a quick-response agent. Provide concise answers.",
            llm="gpt-4o-mini"
        ),
        'analytical_agent': Agent(
            instructions="You are an analytical agent. Provide detailed analysis.",
            llm="gpt-4o-mini"
        ),
        'research_agent': Agent(
            instructions="You are a research agent. Provide comprehensive information.",
            llm="gpt-4o-mini"
        ),
        'creative_agent': Agent(
            instructions="You are a creative agent. Provide imaginative responses.",
            llm="gpt-4o-mini"
        )
    }
    
    results = []
    
    for i, (scenario_type, query) in enumerate(test_scenarios):
        print(f"\n🎯 Scenario {i+1}: {scenario_type}")
        
        # Select appropriate agent
        agent_type = list(agents.keys())[i % len(agents)]
        agent = agents[agent_type]
        
        with track_api_call(f"{scenario_type.lower().replace(' ', '_')}_execution"):
            try:
                result = agent.start(query)
                results.append({
                    'scenario': scenario_type,
                    'agent': agent_type,
                    'query': query,
                    'result': result[:200] + '...' if len(result) > 200 else result,
                    'success': True
                })
            except Exception as e:
                results.append({
                    'scenario': scenario_type,
                    'agent': agent_type,
                    'query': query,
                    'error': str(e),
                    'success': False
                })
    
    return results

@monitor_function("multi_agent_workflow_simulation")
def simulate_complex_workflow():
    """Simulate complex multi-agent workflow for comprehensive data."""
    
    print("🔄 Simulating complex multi-agent workflow...")
    
    # Create specialized agents
    planner = Agent(
        name="planner",
        instructions="You are a project planner. Break down tasks and plan execution.",
        llm="gpt-4o-mini"
    )
    
    executor = Agent(
        name="executor", 
        instructions="You are a task executor. Complete assigned tasks efficiently.",
        llm="gpt-4o-mini"
    )
    
    reviewer = Agent(
        name="reviewer",
        instructions="You are a quality reviewer. Review and improve work.",
        llm="gpt-4o-mini"
    )
    
    # Create workflow tasks
    planning_task = Task(
        name="planning",
        description="Plan a comprehensive report on renewable energy trends",
        expected_output="A detailed project plan with timeline and milestones"
    )
    
    execution_task = Task(
        name="execution", 
        description="Execute the planned research and compile findings",
        expected_output="Research findings and data compilation"
    )
    
    review_task = Task(
        name="review",
        description="Review the research and provide quality assessment",
        expected_output="Quality review and improvement recommendations"
    )
    
    # Assign agents to tasks
    planning_task.agent = planner
    execution_task.agent = executor  
    review_task.agent = reviewer
    
    # Execute workflow
    with track_api_call("complex_workflow_execution"):
        workflow = PraisonAIAgents(
            agents=[planner, executor, reviewer],
            tasks=[planning_task, execution_task, review_task],
            process="sequential",
            verbose=False
        )
        
        result = workflow.start()
    
    return result

@monitor_function("performance_benchmarking")
def run_performance_benchmarks():
    """Run performance benchmarks for various operations."""
    
    print("⚡ Running performance benchmarks...")
    
    benchmark_results = {}
    
    # Benchmark 1: Response time under different loads
    print("  📈 Benchmarking response times...")
    response_times = []
    
    for i in range(10):
        start_time = time.time()
        with track_api_call(f"benchmark_response_{i}"):
            # Simulate quick agent response
            time.sleep(0.05 + (i % 3) * 0.02)  # Variable response time
        response_times.append(time.time() - start_time)
    
    benchmark_results['response_times'] = {
        'min': min(response_times),
        'max': max(response_times), 
        'avg': sum(response_times) / len(response_times),
        'samples': len(response_times)
    }
    
    # Benchmark 2: Concurrent operations
    print("  🔄 Benchmarking concurrent operations...")
    concurrent_start = time.time()
    
    # Simulate concurrent operations
    for i in range(5):
        with track_api_call(f"concurrent_op_{i}"):
            time.sleep(0.1)  # Simulate concurrent work
    
    concurrent_time = time.time() - concurrent_start
    benchmark_results['concurrent_operations'] = {
        'total_time': concurrent_time,
        'operations': 5,
        'avg_per_operation': concurrent_time / 5
    }
    
    # Benchmark 3: Memory usage simulation
    print("  💾 Benchmarking memory operations...")
    memory_ops = []
    
    for i in range(8):
        start = time.time()
        with track_api_call(f"memory_benchmark_{i}"):
            # Simulate memory-intensive operation
            time.sleep(0.03 + (i % 2) * 0.02)
        memory_ops.append(time.time() - start)
    
    benchmark_results['memory_operations'] = {
        'operations': len(memory_ops),
        'total_time': sum(memory_ops),
        'avg_time': sum(memory_ops) / len(memory_ops)
    }
    
    return benchmark_results

@monitor_function("generate_dashboard_report")
def generate_dashboard_report():
    """Generate comprehensive dashboard report."""
    
    print("📋 Generating comprehensive dashboard report...")
    
    # Collect all performance data
    function_stats = get_function_stats()
    api_stats = get_api_stats()
    slowest_functions = get_slowest_functions()
    slowest_apis = get_slowest_apis()
    
    # Generate reports
    basic_report = get_performance_report()
    comprehensive_report = generate_comprehensive_report()
    
    # Analyze trends and flows
    try:
        flow_analysis = analyze_function_flow()
        performance_trends = analyze_performance_trends()
        flow_visualization = visualize_execution_flow()
    except Exception as e:
        flow_analysis = {"error": str(e)}
        performance_trends = {"error": str(e)} 
        flow_visualization = {"error": str(e)}
    
    dashboard_data = {
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_functions': len(function_stats),
            'total_api_calls': len(api_stats),
            'total_function_calls': sum(stats['call_count'] for stats in function_stats.values()),
            'total_api_requests': sum(stats['call_count'] for stats in api_stats.values()),
            'total_execution_time': sum(stats['total_time'] for stats in function_stats.values()),
            'total_errors': sum(stats['error_count'] for stats in function_stats.values())
        },
        'performance_data': {
            'function_stats': function_stats,
            'api_stats': api_stats,
            'slowest_functions': slowest_functions,
            'slowest_apis': slowest_apis
        },
        'analysis': {
            'flow_analysis': flow_analysis,
            'performance_trends': performance_trends,
            'flow_visualization': len(str(flow_visualization)) if flow_visualization else 0
        },
        'reports': {
            'basic_report': basic_report,
            'comprehensive_report': comprehensive_report[:500] + '...' if len(comprehensive_report) > 500 else comprehensive_report
        }
    }
    
    return dashboard_data

def display_dashboard(dashboard_data, benchmark_results):
    """Display comprehensive performance dashboard."""
    
    print("\n" + "=" * 80)
    print("📊 COMPREHENSIVE PERFORMANCE DASHBOARD")
    print("=" * 80)
    
    # Executive Summary
    summary = dashboard_data['summary']
    print(f"\n📈 EXECUTIVE SUMMARY")
    print(f"  Report Generated: {dashboard_data['timestamp']}")
    print(f"  Functions Monitored: {summary['total_functions']}")
    print(f"  API Endpoints: {summary['total_api_calls']}")
    print(f"  Total Function Calls: {summary['total_function_calls']}")
    print(f"  Total API Requests: {summary['total_api_requests']}")
    print(f"  Total Execution Time: {summary['total_execution_time']:.3f}s")
    print(f"  Total Errors: {summary['total_errors']}")
    
    # Performance Overview
    print(f"\n⚡ PERFORMANCE OVERVIEW")
    avg_function_time = 0
    if summary['total_function_calls'] > 0:
        avg_function_time = summary['total_execution_time'] / summary['total_function_calls']
        print(f"  Average Function Execution: {avg_function_time:.3f}s")
    
    if summary['total_errors'] > 0 and summary['total_function_calls'] > 0:
        error_rate = summary['total_errors'] / summary['total_function_calls'] * 100
        print(f"  Error Rate: {error_rate:.2f}%")
    else:
        print(f"  Error Rate: 0.00%")
    
    # Top Performers and Issues
    print(f"\n🏆 TOP PERFORMERS")
    perf_data = dashboard_data['performance_data']
    
    print("  Fastest Functions:")
    fastest_functions = sorted(perf_data['slowest_functions'], key=lambda x: x[1])[:3]
    for name, time in fastest_functions:
        print(f"    {name}: {time:.3f}s")
    
    print("  Slowest Functions:")
    for name, time in perf_data['slowest_functions'][:3]:
        print(f"    {name}: {time:.3f}s")
    
    # Benchmark Results
    print(f"\n⚡ BENCHMARK RESULTS")
    print(f"  Response Time Benchmarks:")
    rt = benchmark_results['response_times']
    print(f"    Min: {rt['min']:.3f}s, Max: {rt['max']:.3f}s, Avg: {rt['avg']:.3f}s")
    
    print(f"  Concurrent Operations:")
    co = benchmark_results['concurrent_operations']
    print(f"    {co['operations']} operations in {co['total_time']:.3f}s")
    print(f"    Avg per operation: {co['avg_per_operation']:.3f}s")
    
    print(f"  Memory Operations:")
    mo = benchmark_results['memory_operations']
    print(f"    {mo['operations']} operations, {mo['avg_time']:.3f}s average")
    
    # System Health
    print(f"\n🏥 SYSTEM HEALTH")
    
    # Calculate health score
    health_score = 100
    if avg_function_time > 0.2:
        health_score -= 20
    if summary['total_errors'] > 0:
        health_score -= summary['total_errors'] * 10
    if rt['avg'] > 0.1:
        health_score -= 15
    
    health_score = max(0, health_score)
    
    if health_score >= 90:
        status = "🟢 Excellent"
    elif health_score >= 70:
        status = "🟡 Good"
    elif health_score >= 50:
        status = "🟠 Fair"
    else:
        status = "🔴 Needs Attention"
    
    print(f"  Overall Health Score: {health_score}/100 - {status}")
    
    # Analysis Results
    print(f"\n🔍 ANALYSIS RESULTS")
    analysis = dashboard_data['analysis']
    
    if 'error' not in analysis['flow_analysis']:
        flow_data = analysis['flow_analysis']
        print(f"  Flow Analysis: {len(flow_data.get('functions', []))} functions analyzed")
    else:
        print(f"  Flow Analysis: {analysis['flow_analysis']['error']}")
    
    if analysis['flow_visualization']:
        print(f"  Flow Visualization: Generated ({analysis['flow_visualization']} chars)")
    
    # Recommendations
    print(f"\n💡 PERFORMANCE RECOMMENDATIONS")
    
    if avg_function_time > 0.15:
        print("  🔧 Optimize slow functions for better response times")
    if summary['total_errors'] > 0:
        print("  🚨 Investigate and resolve error sources")
    if rt['avg'] > 0.08:
        print("  ⚡ Consider response time optimization strategies")
    if summary['total_function_calls'] > 50:
        print("  📊 Implement performance caching for high-volume functions")
    
    print("  📈 Continue monitoring trends for proactive optimization")
    print("  🔄 Regular performance reviews recommended")

def main():
    """Main function for comprehensive performance dashboard."""
    print("=" * 80)
    print("EXAMPLE 10: Comprehensive Performance Dashboard")
    print("=" * 80)
    print("This example demonstrates a complete performance monitoring solution")
    print("with advanced analytics, benchmarking, and dashboard reporting.\n")
    
    # Clear previous data for clean demo
    clear_performance_data()
    
    # Phase 1: Data Collection
    print("📊 Phase 1: Comprehensive Data Collection")
    collection_results = collect_comprehensive_data()
    
    # Phase 2: Complex Workflow
    print("\n🔄 Phase 2: Complex Multi-Agent Workflow")
    workflow_result = simulate_complex_workflow()
    
    # Phase 3: Performance Benchmarking
    print("\n⚡ Phase 3: Performance Benchmarking")
    benchmark_results = run_performance_benchmarks()
    
    # Phase 4: Dashboard Generation
    print("\n📋 Phase 4: Dashboard Report Generation")
    dashboard_data = generate_dashboard_report()
    
    # Phase 5: Display Comprehensive Dashboard
    display_dashboard(dashboard_data, benchmark_results)
    
    # Final Summary
    print(f"\n🎯 EXECUTION SUMMARY")
    print(f"  Scenarios Executed: {len(collection_results)}")
    successful_scenarios = sum(1 for r in collection_results if r['success'])
    print(f"  Successful Scenarios: {successful_scenarios}/{len(collection_results)}")
    print(f"  Workflow Completed: {'✅ Yes' if workflow_result else '❌ No'}")
    print(f"  Benchmarks Run: {len(benchmark_results)}")
    print(f"  Dashboard Generated: ✅ Complete")
    
    return {
        'scenarios': len(collection_results),
        'success_rate': successful_scenarios / len(collection_results) * 100,
        'dashboard_data': dashboard_data,
        'benchmark_results': benchmark_results
    }

if __name__ == "__main__":
    result = main()
    print(f"\n🎉 Comprehensive dashboard monitoring completed!")
    print(f"Success Rate: {result['success_rate']:.1f}%")
    print(f"Total Functions Monitored: {result['dashboard_data']['summary']['total_functions']}")
    print(f"Performance Health Score Available in Dashboard Above ⬆️")
    print("\n💡 This dashboard provides real-time insights into your PraisonAI system performance!")
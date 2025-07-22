"""
Comprehensive Performance Monitoring Example for PraisonAI

This example demonstrates how to use the enhanced performance monitoring system
to track function performance, API calls, and execution flow WITHOUT making
any changes to existing code.
"""

import time
import asyncio
from pathlib import Path

# Import PraisonAI components
from praisonaiagents import Agent, PraisonAIAgents, Task

# Import performance monitoring components
from praisonaiagents.performance_monitor import get_performance_monitor
from praisonaiagents.auto_instrument import enable_auto_instrumentation, disable_auto_instrumentation
from praisonaiagents.performance_dashboard import start_performance_dashboard, stop_performance_dashboard
from praisonaiagents.performance_cli import PerformanceCLI


def basic_performance_tracking_example():
    """
    Example 1: Basic performance tracking without code changes.
    
    This shows how to enable monitoring and get performance insights
    for existing PraisonAI code without modifying any source code.
    """
    print("=" * 60)
    print("📊 Example 1: Basic Performance Tracking")
    print("=" * 60)
    
    # Step 1: Enable performance monitoring
    monitor = get_performance_monitor()
    monitor.enable()
    print("✅ Performance monitoring enabled")
    
    # Step 2: Enable auto-instrumentation (monkey patching)
    enable_auto_instrumentation()
    print("✅ Auto-instrumentation enabled - all PraisonAI functions are now tracked")
    
    # Step 3: Run your normal PraisonAI code - no changes needed!
    agent = Agent(
        name="PerformanceTestAgent",
        role="Performance Testing Assistant",
        goal="Test various operations for performance analysis",
        backstory="I help test performance monitoring capabilities"
    )
    
    # Execute some tasks
    print("\n🚀 Running test operations...")
    
    # Simple chat interaction
    response1 = agent.chat("What is the capital of France?")
    print(f"Response 1: {response1[:100]}...")
    
    # Another interaction
    response2 = agent.chat("Explain machine learning in simple terms.")
    print(f"Response 2: {response2[:100]}...")
    
    # Step 4: Get performance metrics
    print("\n📈 Performance Metrics:")
    summary = monitor.get_performance_summary()
    
    print(f"• Total function calls: {summary.get('total_function_calls', 0):,}")
    print(f"• Total API calls: {summary.get('total_api_calls', 0):,}")
    print(f"• Total execution time: {summary.get('total_execution_time', 0):.3f}s")
    print(f"• Memory usage: {summary.get('memory_usage', {}).get('rss_mb', 0)} MB")
    
    # Show slowest functions
    slowest_functions = summary.get('slowest_functions', [])[:3]
    if slowest_functions:
        print("\n🐌 Slowest Functions:")
        for func in slowest_functions:
            print(f"  • {func['function']}: {func['average_time']:.3f}s (avg)")
    
    # Show API call summary
    api_summary = summary.get('api_call_summary', {})
    if api_summary:
        print("\n🌐 API Calls by Type:")
        for api_type, stats in api_summary.items():
            print(f"  • {api_type}: {stats['count']} calls, {stats['average_time']:.3f}s avg")


def multi_agent_performance_analysis():
    """
    Example 2: Multi-agent workflow performance analysis.
    
    Shows how to track performance in complex multi-agent workflows
    and understand the execution flow.
    """
    print("\n" + "=" * 60)
    print("🤝 Example 2: Multi-Agent Performance Analysis")
    print("=" * 60)
    
    monitor = get_performance_monitor()
    
    # Create multiple agents for different roles
    researcher = Agent(
        name="Researcher",
        role="Research Specialist",
        goal="Conduct thorough research on given topics",
        backstory="Expert in gathering and analyzing information"
    )
    
    writer = Agent(
        name="Writer", 
        role="Content Writer",
        goal="Create well-structured content based on research",
        backstory="Professional writer skilled in creating engaging content"
    )
    
    editor = Agent(
        name="Editor",
        role="Content Editor",
        goal="Review and improve written content",
        backstory="Detail-oriented editor with expertise in content quality"
    )
    
    # Create tasks
    research_task = Task(
        description="Research the latest trends in artificial intelligence",
        expected_output="A comprehensive research report",
        agent=researcher
    )
    
    writing_task = Task(
        description="Write an engaging article about AI trends",
        expected_output="A well-structured article",
        agent=writer,
        context=[research_task]
    )
    
    editing_task = Task(
        description="Edit and improve the article for clarity and flow",
        expected_output="A polished final article",
        agent=editor,
        context=[writing_task]
    )
    
    # Create and run multi-agent workflow
    print("\n🚀 Running multi-agent workflow...")
    start_time = time.time()
    
    workflow = PraisonAIAgents(
        agents=[researcher, writer, editor],
        tasks=[research_task, writing_task, editing_task],
        process="sequential",
        verbose=True
    )
    
    # Execute workflow
    result = workflow.start()
    end_time = time.time()
    
    print(f"\n✅ Workflow completed in {end_time - start_time:.2f}s")
    
    # Analyze performance
    print("\n📊 Workflow Performance Analysis:")
    
    # Function-level analysis
    function_metrics = monitor.get_function_metrics()
    if function_metrics:
        print("\n🔍 Function Performance:")
        # Sort by total time and show top 5
        sorted_functions = sorted(
            function_metrics.items(),
            key=lambda x: x[1].get('total_time', 0),
            reverse=True
        )[:5]
        
        for func_name, metrics in sorted_functions:
            print(f"  • {func_name}:")
            print(f"    - Total time: {metrics.get('total_time', 0):.3f}s")
            print(f"    - Avg time: {metrics.get('average_time', 0):.3f}s") 
            print(f"    - Calls: {metrics.get('total_calls', 0)}")
    
    # API-level analysis
    api_metrics = monitor.get_api_metrics()
    if api_metrics.get('total_calls', 0) > 0:
        print(f"\n🌐 API Performance:")
        print(f"  • Total API calls: {api_metrics['total_calls']}")
        print(f"  • Success rate: {api_metrics['success_rate']:.1%}")
        print(f"  • Average response time: {api_metrics['average_time']:.3f}s")
        
        # Breakdown by provider
        by_provider = api_metrics.get('by_provider', {})
        if by_provider:
            print("  • By provider:")
            for provider, stats in by_provider.items():
                print(f"    - {provider}: {stats['count']} calls, {stats['average_time']:.3f}s avg")
    
    # Call hierarchy analysis
    hierarchy = monitor.get_call_hierarchy(max_depth=3)
    calls = hierarchy.get('call_hierarchy', [])
    if calls:
        print("\n🌳 Execution Flow (Top-level calls):")
        for i, call in enumerate(calls[:3], 1):
            duration = call.get('duration', 0)
            success = "✅" if call.get('success', True) else "❌"
            print(f"  {i}. {success} {call['function']} ({duration:.3f}s)")
            
            # Show children
            children = call.get('children', [])[:3]
            for child in children:
                child_duration = child.get('duration', 0)
                child_success = "✅" if child.get('success', True) else "❌"
                print(f"     └─ {child_success} {child['function']} ({child_duration:.3f}s)")


def performance_dashboard_example():
    """
    Example 3: Using the web-based performance dashboard.
    
    Shows how to start a real-time dashboard for monitoring performance.
    """
    print("\n" + "=" * 60)
    print("🖥️  Example 3: Performance Dashboard")
    print("=" * 60)
    
    # Start the dashboard
    dashboard_url = start_performance_dashboard(port=8889)
    
    if dashboard_url:
        print(f"🚀 Performance dashboard started at {dashboard_url}")
        print("📊 The dashboard provides real-time monitoring of:")
        print("   • Function performance metrics")
        print("   • API call analysis")
        print("   • Memory usage tracking")
        print("   • Call hierarchy visualization")
        print("   • Auto-refreshing charts and tables")
        print("\n💡 Open the URL in your browser to view the dashboard")
        print("⏰ Running some operations to generate data...")
        
        # Generate some activity for the dashboard
        agent = Agent(
            name="DashboardTestAgent",
            role="Dashboard Data Generator",
            goal="Generate performance data for dashboard testing"
        )
        
        # Run several operations
        for i in range(3):
            response = agent.chat(f"Test operation {i+1}: Tell me about Python programming.")
            print(f"   Operation {i+1} completed")
            time.sleep(1)  # Brief pause between operations
        
        print(f"\n✅ Sample data generated! Check the dashboard at {dashboard_url}")
        print("🔴 Dashboard will remain running (stop with Ctrl+C in production)")
        
        # In a real scenario, you might want to keep the dashboard running
        # For this example, we'll stop it after a short demonstration
        time.sleep(2)
        stop_performance_dashboard()
        print("🔴 Dashboard stopped")
    else:
        print("❌ Failed to start dashboard")


def cli_tools_example():
    """
    Example 4: Using the command-line interface for performance analysis.
    
    Shows how to use the CLI tools for performance monitoring and analysis.
    """
    print("\n" + "=" * 60)
    print("💻 Example 4: CLI Tools for Performance Analysis")
    print("=" * 60)
    
    cli = PerformanceCLI()
    
    print("🔧 Available CLI commands:")
    print("   • praisonai-perf status       - Show monitoring status")
    print("   • praisonai-perf summary      - Performance summary")
    print("   • praisonai-perf functions    - Function analysis")
    print("   • praisonai-perf apis         - API call analysis")
    print("   • praisonai-perf hierarchy    - Call hierarchy")
    print("   • praisonai-perf dashboard    - Start web dashboard")
    print("   • praisonai-perf export       - Export performance data")
    
    print("\n📊 Demonstrating CLI commands:")
    
    # Generate some test data first
    monitor = get_performance_monitor()
    agent = Agent(name="CLITestAgent", role="CLI Testing Assistant")
    agent.chat("Generate test data for CLI demonstration")
    
    # Demonstrate status command
    print("\n1️⃣ Status Command:")
    cli.run(['status'])
    
    # Demonstrate summary command
    print("\n2️⃣ Summary Command:")
    cli.run(['summary'])
    
    # Demonstrate functions command
    print("\n3️⃣ Functions Command (top 3):")
    cli.run(['functions', '--top', '3'])
    
    # Demonstrate export command
    print("\n4️⃣ Export Command:")
    export_file = "/tmp/performance_metrics.json"
    cli.run(['export', '--output', export_file])
    
    if Path(export_file).exists():
        print(f"   ✅ Performance data exported to {export_file}")
        
        # Show a sample of the exported data
        import json
        with open(export_file) as f:
            data = json.load(f)
        
        print(f"   📄 Export contains:")
        print(f"      • Summary: {len(data.get('summary', {}))}")
        print(f"      • Function metrics: {len(data.get('function_metrics', {}))}")
        print(f"      • API metrics: {len(data.get('api_metrics', {}))}")
        print(f"      • Call hierarchy: {len(data.get('call_hierarchy', {}).get('call_hierarchy', []))}")


def api_call_tracking_example():
    """
    Example 5: Detailed API call tracking and analysis.
    
    Shows how to track and analyze different types of API calls
    (LLM, HTTP, tools) with detailed timing information.
    """
    print("\n" + "=" * 60)
    print("🌐 Example 5: API Call Tracking and Analysis")
    print("=" * 60)
    
    monitor = get_performance_monitor()
    
    # Clear previous data for clean analysis
    monitor.clear_metrics()
    print("🗑️ Cleared previous performance data")
    
    # Create agent with different providers to test API tracking
    agent = Agent(
        name="APITestAgent",
        role="API Performance Tester", 
        goal="Test different types of API calls for performance analysis",
        llm="gpt-3.5-turbo"  # Specify model for API tracking
    )
    
    print("\n🚀 Testing different types of operations...")
    
    # Test 1: Simple LLM API call
    print("1️⃣ Testing LLM API call...")
    response1 = agent.chat("What is artificial intelligence?")
    
    # Test 2: More complex LLM API call
    print("2️⃣ Testing complex LLM API call...")
    response2 = agent.chat("Explain machine learning algorithms and their applications in detail.")
    
    # Test 3: Multiple quick calls
    print("3️⃣ Testing multiple quick calls...")
    for i in range(3):
        agent.chat(f"Quick test {i+1}: What is {2**i}?")
    
    # Wait a moment for all async operations to complete
    time.sleep(1)
    
    # Analyze API performance
    print("\n📊 API Performance Analysis:")
    
    api_metrics = monitor.get_api_metrics()
    if api_metrics:
        print(f"📈 Overall API Statistics:")
        print(f"   • Total API calls: {api_metrics.get('total_calls', 0)}")
        print(f"   • Success rate: {api_metrics.get('success_rate', 0):.1%}")
        print(f"   • Total time: {api_metrics.get('total_time', 0):.3f}s")
        print(f"   • Average time: {api_metrics.get('average_time', 0):.3f}s")
        print(f"   • Min/Max time: {api_metrics.get('min_time', 0):.3f}s / {api_metrics.get('max_time', 0):.3f}s")
        
        # Provider breakdown
        by_provider = api_metrics.get('by_provider', {})
        if by_provider:
            print(f"\n🏢 Performance by Provider:")
            for provider, stats in by_provider.items():
                efficiency = stats['total_time'] / stats['count'] if stats['count'] > 0 else 0
                print(f"   • {provider}:")
                print(f"     - Calls: {stats['count']}")
                print(f"     - Total time: {stats['total_time']:.3f}s")
                print(f"     - Average time: {stats['average_time']:.3f}s")
                print(f"     - Efficiency score: {1/efficiency:.2f}" if efficiency > 0 else "     - Efficiency: N/A")
    else:
        print("⚠️ No API metrics available - this might indicate API tracking needs configuration")
    
    # Performance recommendations
    print(f"\n💡 Performance Insights:")
    summary = monitor.get_performance_summary()
    total_time = summary.get('total_execution_time', 0)
    api_time = api_metrics.get('total_time', 0) if api_metrics else 0
    
    if total_time > 0:
        api_percentage = (api_time / total_time) * 100
        print(f"   • API calls account for {api_percentage:.1f}% of total execution time")
        
        if api_percentage > 70:
            print("   • 🐌 High API overhead detected - consider caching or batching requests")
        elif api_percentage < 30:
            print("   • ⚡ Low API overhead - performance bottlenecks likely in local processing")
        else:
            print("   • ✅ Balanced performance between API calls and local processing")
    
    if api_metrics and api_metrics.get('average_time', 0) > 2.0:
        print("   • 🐌 Slow API response times detected - check network or provider performance")
    elif api_metrics and api_metrics.get('average_time', 0) < 0.5:
        print("   • ⚡ Fast API response times - good network and provider performance")


def performance_optimization_workflow():
    """
    Example 6: Complete performance optimization workflow.
    
    Shows how to use the performance monitoring system to identify
    and optimize performance bottlenecks.
    """
    print("\n" + "=" * 60)
    print("🔧 Example 6: Performance Optimization Workflow")
    print("=" * 60)
    
    monitor = get_performance_monitor()
    
    # Step 1: Baseline measurement
    print("1️⃣ Establishing baseline performance...")
    monitor.clear_metrics()
    
    baseline_start = time.time()
    
    agent = Agent(
        name="OptimizationTestAgent",
        role="Performance Optimization Tester",
        goal="Help identify performance optimization opportunities"
    )
    
    # Run baseline operations
    for i in range(3):
        agent.chat(f"Baseline test {i+1}: Explain the concept of {['algorithms', 'data structures', 'optimization'][i]}")
    
    baseline_end = time.time()
    baseline_summary = monitor.get_performance_summary()
    
    print(f"   ✅ Baseline completed in {baseline_end - baseline_start:.2f}s")
    print(f"   • Function calls: {baseline_summary.get('total_function_calls', 0)}")
    print(f"   • API calls: {baseline_summary.get('total_api_calls', 0)}")
    print(f"   • Execution time: {baseline_summary.get('total_execution_time', 0):.3f}s")
    
    # Step 2: Identify bottlenecks
    print("\n2️⃣ Identifying performance bottlenecks...")
    
    slowest_functions = baseline_summary.get('slowest_functions', [])[:3]
    if slowest_functions:
        print("   🐌 Potential bottlenecks identified:")
        for func in slowest_functions:
            impact_score = func['average_time'] * func['call_count']
            print(f"      • {func['function']}: {func['average_time']:.3f}s avg (impact: {impact_score:.3f}s)")
    
    api_metrics = monitor.get_api_metrics()
    if api_metrics and api_metrics.get('average_time', 0) > 1.0:
        print(f"   🌐 API bottleneck detected: {api_metrics['average_time']:.3f}s average response time")
    
    # Step 3: Generate recommendations
    print("\n3️⃣ Performance optimization recommendations:")
    
    recommendations = []
    
    # Function-level recommendations
    if slowest_functions:
        slowest = slowest_functions[0]
        if slowest['average_time'] > 2.0:
            recommendations.append(f"🔧 Optimize '{slowest['function']}' function - it's taking {slowest['average_time']:.3f}s on average")
    
    # API-level recommendations
    if api_metrics:
        if api_metrics.get('average_time', 0) > 2.0:
            recommendations.append("🌐 Consider API response caching to reduce latency")
        
        if api_metrics.get('total_calls', 0) > 10:
            recommendations.append("📦 Consider batching API requests to reduce overhead")
    
    # Memory recommendations
    memory_usage = baseline_summary.get('memory_usage', {}).get('rss_mb', 0)
    if memory_usage > 500:  # More than 500MB
        recommendations.append(f"💾 High memory usage detected ({memory_usage}MB) - consider memory optimization")
    
    # Error rate recommendations
    error_count = baseline_summary.get('errors', 0)
    total_calls = baseline_summary.get('total_function_calls', 0)
    if total_calls > 0 and (error_count / total_calls) > 0.05:  # More than 5% error rate
        recommendations.append(f"⚠️ High error rate detected ({error_count}/{total_calls}) - investigate error handling")
    
    if recommendations:
        for rec in recommendations:
            print(f"   {rec}")
    else:
        print("   ✅ No major performance issues detected - system is running efficiently!")
    
    # Step 4: Export detailed analysis
    print("\n4️⃣ Exporting detailed analysis...")
    
    export_data = monitor.export_metrics('json')
    export_file = "/tmp/optimization_analysis.json"
    
    with open(export_file, 'w') as f:
        f.write(export_data)
    
    print(f"   ✅ Detailed analysis exported to {export_file}")
    print(f"   📊 Use this data for further analysis or sharing with team")
    
    # Step 5: Cleanup
    print("\n5️⃣ Cleaning up...")
    disable_auto_instrumentation()
    monitor.disable()
    print("   ✅ Performance monitoring disabled and functions restored")


def main():
    """
    Main function that runs all examples.
    
    This demonstrates the complete performance monitoring capabilities
    available in PraisonAI without requiring any code changes.
    """
    print("🚀 PraisonAI Enhanced Performance Monitoring Examples")
    print("=" * 60)
    print("This example demonstrates comprehensive performance tracking")
    print("capabilities that require NO changes to your existing code!")
    print()
    
    try:
        # Run all examples
        basic_performance_tracking_example()
        multi_agent_performance_analysis() 
        performance_dashboard_example()
        cli_tools_example()
        api_call_tracking_example()
        performance_optimization_workflow()
        
        print("\n" + "=" * 60)
        print("🎉 All examples completed successfully!")
        print("=" * 60)
        print("\n📚 What you've learned:")
        print("✅ How to enable performance monitoring without code changes")
        print("✅ Function-level performance tracking and analysis")  
        print("✅ API call monitoring and optimization")
        print("✅ Real-time dashboard for performance visualization")
        print("✅ CLI tools for performance analysis and reporting")
        print("✅ Complete performance optimization workflow")
        print()
        print("💡 Key Benefits:")
        print("• Zero code changes required")
        print("• Comprehensive performance insights")
        print("• Real-time monitoring and analysis")
        print("• Export capabilities for reporting")
        print("• Automatic bottleneck identification")
        print("• Multi-agent workflow analysis")
        print()
        print("🔧 Next Steps:")
        print("• Use 'praisonai-perf enable --auto-instrument' in your projects")
        print("• Start dashboard with 'praisonai-perf dashboard --port 8888'")
        print("• Export metrics with 'praisonai-perf export --output metrics.json'")
        print("• Monitor production systems with automated reporting")
        
    except Exception as e:
        print(f"❌ Example failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Ensure cleanup
        try:
            disable_auto_instrumentation()
            stop_performance_dashboard()
            get_performance_monitor().disable()
        except:
            pass


if __name__ == "__main__":
    main()
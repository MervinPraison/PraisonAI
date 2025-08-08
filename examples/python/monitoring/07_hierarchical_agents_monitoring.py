"""
Hierarchical Agents with Performance Monitoring - Example 7

Demonstrates performance monitoring for hierarchical agent systems:
- Manager-worker agent relationships
- Task delegation timing
- Hierarchical decision making performance
- Cross-level communication monitoring

Shows how to monitor complex organizational agent structures.
"""

import time
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, get_function_stats,
    visualize_execution_flow, generate_comprehensive_report
)

@monitor_function("manager_decision_making")
def make_management_decision(task_description: str):
    """Simulate manager decision making process."""
    print(f"👔 Manager analyzing task: {task_description}")
    # Simulate decision complexity
    time.sleep(0.1)
    
    # Simple task routing logic
    if "research" in task_description.lower():
        return "research_worker"
    elif "analysis" in task_description.lower():
        return "analysis_worker" 
    elif "report" in task_description.lower():
        return "writing_worker"
    else:
        return "general_worker"

@monitor_function("task_delegation") 
def delegate_task(task: str, worker_type: str):
    """Simulate task delegation to workers."""
    print(f"📤 Delegating to {worker_type}: {task}")
    time.sleep(0.05)  # Delegation overhead
    return f"Task delegated to {worker_type}"

@monitor_function("worker_execution")
def execute_worker_task(worker_name: str, task_description: str):
    """Simulate worker executing assigned task."""
    print(f"⚙️ {worker_name} executing: {task_description}")
    
    # Different workers have different execution times
    if "research" in worker_name:
        time.sleep(0.2)  # Research takes longer
    elif "analysis" in worker_name:
        time.sleep(0.15)  # Analysis is moderate
    elif "writing" in worker_name:
        time.sleep(0.1)   # Writing is relatively quick
    else:
        time.sleep(0.12)  # General tasks
    
    return f"{worker_name} completed: {task_description}"

@monitor_function("result_aggregation")
def aggregate_results(results: list):
    """Simulate aggregating results from multiple workers."""
    print(f"📊 Aggregating {len(results)} worker results...")
    time.sleep(0.08)  # Aggregation time
    return f"Aggregated {len(results)} results into final output"

@monitor_function("hierarchical_workflow")
def run_hierarchical_workflow():
    """Run a complete hierarchical workflow with monitoring."""
    
    # Create manager agent
    manager = Agent(
        name="project_manager",
        role="Project Manager",
        goal="Efficiently coordinate team efforts and ensure project success",
        backstory="Experienced project manager with expertise in team coordination",
        instructions="""You are a project manager. Break down complex projects into tasks,
        assign them to appropriate team members, and coordinate the overall effort.""",
        llm="gpt-5-nano"
    )
    
    # Create worker agents
    research_worker = Agent(
        name="research_specialist", 
        role="Research Specialist",
        goal="Conduct thorough research on assigned topics",
        backstory="Expert researcher with deep analytical skills",
        instructions="You are a research specialist. Provide detailed, factual information.",
        llm="gpt-5-nano"
    )
    
    analysis_worker = Agent(
        name="data_analyst",
        role="Data Analyst", 
        goal="Analyze data and identify patterns and insights",
        backstory="Experienced data analyst with strong analytical thinking",
        instructions="You are a data analyst. Focus on patterns, trends, and insights.",
        llm="gpt-5-nano"
    )
    
    writing_worker = Agent(
        name="technical_writer",
        role="Technical Writer",
        goal="Create clear, well-structured documentation and reports", 
        backstory="Professional writer specializing in technical content",
        instructions="You are a technical writer. Create clear, comprehensive reports.",
        llm="gpt-5-nano"
    )
    
    # Project tasks
    project_tasks = [
        "Research current trends in artificial intelligence",
        "Analyze the impact of AI on business productivity",
        "Write a comprehensive report on AI implementation strategies"
    ]
    
    # Execute hierarchical workflow
    with track_api_call("hierarchical_project_execution"):
        print("🏢 Starting hierarchical project execution...")
        
        all_results = []
        
        for task_desc in project_tasks:
            print(f"\n📋 Processing project task: {task_desc}")
            
            # Manager makes decision
            assigned_worker = make_management_decision(task_desc)
            
            # Delegate task
            delegation_result = delegate_task(task_desc, assigned_worker)
            
            # Select appropriate worker
            if "research" in assigned_worker:
                worker = research_worker
                worker_name = "research_specialist"
            elif "analysis" in assigned_worker:
                worker = analysis_worker
                worker_name = "data_analyst" 
            elif "writing" in assigned_worker:
                worker = writing_worker
                worker_name = "technical_writer"
            else:
                worker = research_worker  # Default
                worker_name = "research_specialist"
            
            # Worker executes task
            worker_result = execute_worker_task(worker_name, task_desc)
            
            # Simulate actual agent execution
            with track_api_call(f"{worker_name}_llm_execution"):
                agent_result = worker.start(task_desc)
                all_results.append(agent_result)
        
        # Manager aggregates results
        final_result = aggregate_results(all_results)
        
        # Final manager review
        with track_api_call("manager_final_review"):
            print("👔 Manager conducting final review...")
            manager_review = manager.start(
                f"Review and synthesize these team outputs: {[r[:100] + '...' for r in all_results]}"
            )
    
    return all_results, manager_review

def main():
    """Main function demonstrating hierarchical agents performance monitoring."""
    print("=" * 75)
    print("EXAMPLE 7: Hierarchical Agents Performance Monitoring")
    print("=" * 75)
    
    # Run hierarchical workflow
    print("\n🏢 Running Hierarchical Agent Workflow")
    worker_results, manager_review = run_hierarchical_workflow()
    
    print(f"\n✅ Workflow completed with {len(worker_results)} task results")
    
    # Performance Analysis
    print("\n" + "=" * 75)
    print("📊 HIERARCHICAL PERFORMANCE ANALYSIS")
    print("=" * 75)
    
    # Role-based performance breakdown
    print("\n👥 Role-Based Performance:")
    stats = get_function_stats()
    
    # Categorize functions by role
    management_functions = [f for f in stats.keys() if 'manager' in f or 'decision' in f or 'delegation' in f or 'aggregation' in f]
    worker_functions = [f for f in stats.keys() if 'worker' in f or 'execution' in f]
    coordination_functions = [f for f in stats.keys() if 'hierarchical' in f or 'workflow' in f]
    
    print("  📋 Management Functions:")
    for func in management_functions:
        data = stats[func]
        avg_time = data['total_time'] / data['call_count'] if data['call_count'] > 0 else 0
        print(f"    {func}: {data['call_count']} calls, {avg_time:.3f}s avg")
    
    print("\n  ⚙️ Worker Functions:")
    for func in worker_functions:
        data = stats[func] 
        avg_time = data['total_time'] / data['call_count'] if data['call_count'] > 0 else 0
        print(f"    {func}: {data['call_count']} calls, {avg_time:.3f}s avg")
    
    print("\n  🔄 Coordination Functions:")
    for func in coordination_functions:
        data = stats[func]
        avg_time = data['total_time'] / data['call_count'] if data['call_count'] > 0 else 0
        print(f"    {func}: {data['call_count']} calls, {avg_time:.3f}s avg")
    
    # Hierarchy efficiency metrics
    total_management_time = sum(stats[f]['total_time'] for f in management_functions)
    total_worker_time = sum(stats[f]['total_time'] for f in worker_functions)
    total_coordination_time = sum(stats[f]['total_time'] for f in coordination_functions)
    
    print(f"\n⚖️ Hierarchy Efficiency Metrics:")
    print(f"  Management Overhead: {total_management_time:.3f}s")
    print(f"  Worker Execution Time: {total_worker_time:.3f}s")
    print(f"  Coordination Overhead: {total_coordination_time:.3f}s")
    
    total_time = total_management_time + total_worker_time + total_coordination_time
    if total_time > 0:
        print(f"  Worker Efficiency: {total_worker_time/total_time*100:.1f}%")
        print(f"  Management Overhead: {total_management_time/total_time*100:.1f}%")
        print(f"  Coordination Overhead: {total_coordination_time/total_time*100:.1f}%")
    
    # Execution flow visualization
    print("\n🔄 Execution Flow Analysis:")
    try:
        flow_viz = visualize_execution_flow()
        print("  Hierarchical flow visualization generated")
        print(f"  Flow complexity: {len(str(flow_viz)) // 100} units")
    except Exception as e:
        print(f"  Flow visualization: {str(e)}")
    
    # Comprehensive report
    print("\n📋 Comprehensive Performance Report:")
    report = generate_comprehensive_report()
    print(report[:500] + "..." if len(report) > 500 else report)
    
    # Optimization recommendations
    print(f"\n💡 Hierarchical Optimization Recommendations:")
    
    if total_time > 0:
        if total_management_time / total_time > 0.3:
            print("  - High management overhead detected - consider task batching")
        if total_coordination_time / total_time > 0.2:
            print("  - Consider reducing coordination complexity")
    if len(worker_results) > 0:
        print(f"  - Successfully processed {len(worker_results)} tasks hierarchically")
    print("  - Monitor delegation efficiency vs direct execution trade-offs")
    
    return {
        'tasks_completed': len(worker_results),
        'management_time': total_management_time,
        'worker_time': total_worker_time,
        'coordination_time': total_coordination_time,
        'efficiency_ratio': total_worker_time / total_time if total_time > 0 else 0
    }

if __name__ == "__main__":
    result = main()
    print(f"\n🎉 Hierarchical monitoring completed!")
    print(f"Tasks: {result['tasks_completed']}, Efficiency: {result['efficiency_ratio']*100:.1f}%")
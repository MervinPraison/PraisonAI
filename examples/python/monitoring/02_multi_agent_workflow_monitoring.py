"""
Multi-Agent Workflow with Performance Monitoring - Example 2

Demonstrates performance monitoring in a multi-agent workflow:
- Multiple agents with different roles
- Inter-agent communication tracking
- Workflow performance analysis
- Task delegation timing

Shows how to monitor complex multi-agent systems.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.telemetry import (
    monitor_function, track_api_call, get_function_stats, 
    analyze_function_flow, generate_comprehensive_report
)
import time

@monitor_function("research_task")
def setup_research_task():
    """Set up research task with monitoring."""
    return Task(
        name="research_task",
        description="Research the topic of renewable energy trends",
        expected_output="A comprehensive research summary"
    )

@monitor_function("analysis_task") 
def setup_analysis_task():
    """Set up analysis task with monitoring."""
    return Task(
        name="analysis_task", 
        description="Analyze the research data and identify key trends",
        expected_output="Key insights and trend analysis"
    )

@monitor_function("report_task")
def setup_report_task():
    """Set up report generation task with monitoring."""
    return Task(
        name="report_task",
        description="Create a final report combining research and analysis", 
        expected_output="A well-structured final report"
    )

@monitor_function("agent_creation")
def create_agents():
    """Create specialized agents with monitoring."""
    
    researcher = Agent(
        name="researcher",
        role="Research Specialist",
        goal="Gather comprehensive information on renewable energy",
        backstory="Expert researcher with deep knowledge of energy sector",
        instructions="You are a thorough researcher. Provide detailed, fact-based information.",
        llm="gpt-4o-mini"
    )
    
    analyst = Agent(
        name="analyst", 
        role="Data Analyst",
        goal="Analyze trends and patterns in renewable energy data",
        backstory="Experienced data analyst specializing in energy markets",
        instructions="You are an analytical thinker. Focus on trends, patterns, and insights.",
        llm="gpt-4o-mini"
    )
    
    writer = Agent(
        name="writer",
        role="Report Writer", 
        goal="Create clear, compelling reports",
        backstory="Professional technical writer with expertise in energy sector",
        instructions="You are a skilled writer. Create clear, well-structured reports.",
        llm="gpt-4o-mini"
    )
    
    return researcher, analyst, writer

@monitor_function("workflow_execution")
def main():
    """Main function demonstrating multi-agent workflow with performance monitoring."""
    print("=" * 70)
    print("EXAMPLE 2: Multi-Agent Workflow with Performance Monitoring")
    print("=" * 70)
    
    # Create agents with monitoring
    researcher, analyst, writer = create_agents()
    
    # Set up tasks with monitoring
    research_task = setup_research_task()
    analysis_task = setup_analysis_task()
    report_task = setup_report_task()
    
    # Assign agents to tasks
    research_task.agent = researcher
    analysis_task.agent = analyst  
    report_task.agent = writer
    
    # Create workflow
    with track_api_call("multi_agent_workflow"):
        print("\n🚀 Starting multi-agent workflow...")
        
        workflow = PraisonAIAgents(
            agents=[researcher, analyst, writer],
            tasks=[research_task, analysis_task, report_task], 
            process="sequential",
            verbose=True
        )
        
        result = workflow.start()
    
    # Display comprehensive performance analysis
    print("\n" + "=" * 70)
    print("📊 MULTI-AGENT PERFORMANCE ANALYSIS")
    print("=" * 70)
    
    # Function statistics
    print("\n📈 Function Performance Statistics:")
    stats = get_function_stats()
    for func_name, data in stats.items():
        print(f"  {func_name}:")
        print(f"    Calls: {data['call_count']}")
        print(f"    Avg Time: {data['total_time']/data['call_count']:.3f}s")
        print(f"    Total Time: {data['total_time']:.3f}s")
    
    # Flow analysis
    print("\n🔄 Execution Flow Analysis:")
    flow_analysis = analyze_function_flow()
    print(f"  Total Functions Monitored: {len(flow_analysis.get('functions', []))}")
    print(f"  Execution Chains: {len(flow_analysis.get('call_chains', []))}")
    
    # Comprehensive report
    print("\n📋 Comprehensive Performance Report:")
    report = generate_comprehensive_report()
    print(report[:500] + "..." if len(report) > 500 else report)
    
    return result

if __name__ == "__main__":
    result = main()
    print(f"\n✅ Multi-agent workflow completed successfully!")
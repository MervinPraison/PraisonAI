"""
Telemetry Integration Example

This example shows how token metrics integrate with the main 
telemetry system for comprehensive monitoring and analytics.
Demonstrates privacy-first tracking and export capabilities.
"""

from praisonaiagents import PraisonAIAgents, Agent, Task
import json

def export_metrics_to_file(agents, filename="token_metrics_export.json"):
    """Export token metrics to a JSON file for external analysis."""
    try:
        # Get comprehensive metrics
        detailed_report = agents.get_detailed_token_report()
        
        if "error" in detailed_report:
            print("❌ Cannot export - token tracking not available")
            return False
        
        # Prepare export data
        export_data = {
            "timestamp": detailed_report.get("summary", {}).get("timestamp", "unknown"),
            "session_summary": detailed_report.get("summary", {}),
            "recent_interactions": detailed_report.get("recent_interactions", []),
            "cost_estimate": detailed_report.get("cost_estimate", {}),
            "metadata": {
                "export_version": "1.0",
                "agent_count": len(agents.agents),
                "task_count": len(agents.tasks)
            }
        }
        
        # Write to file
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"✅ Metrics exported to {filename}")
        return True
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False

def analyze_interaction_patterns(agents):
    """Analyze patterns in LLM interactions for optimization insights."""
    detailed_report = agents.get_detailed_token_report()
    
    if "error" in detailed_report:
        return
    
    recent_interactions = detailed_report.get("recent_interactions", [])
    
    if not recent_interactions:
        print("No recent interactions to analyze")
        return
    
    print(f"\n🔍 INTERACTION PATTERN ANALYSIS:")
    print(f"Total Interactions Analyzed: {len(recent_interactions)}")
    
    # Analyze token efficiency
    token_ratios = []
    for interaction in recent_interactions:
        metrics = interaction.get("metrics", {})
        input_tokens = metrics.get("input_tokens", 0)
        output_tokens = metrics.get("output_tokens", 0)
        
        if input_tokens > 0:
            ratio = output_tokens / input_tokens
            token_ratios.append(ratio)
    
    if token_ratios:
        avg_ratio = sum(token_ratios) / len(token_ratios)
        print(f"Average Output/Input Ratio: {avg_ratio:.2f}")
        
        if avg_ratio > 2.0:
            print("⚠️  High output ratio - consider more focused prompts")
        elif avg_ratio < 0.5:
            print("ℹ️  Low output ratio - may indicate brief responses")
        else:
            print("✅ Balanced input/output ratio")
    
    # Analyze agent usage
    agent_usage = {}
    for interaction in recent_interactions:
        agent = interaction.get("agent")
        if agent:
            agent_usage[agent] = agent_usage.get(agent, 0) + 1
    
    if agent_usage:
        print(f"\nAgent Usage Distribution:")
        for agent, count in sorted(agent_usage.items(), key=lambda x: x[1], reverse=True):
            print(f"  {agent}: {count} interactions")

def main():
    # Create agents with telemetry-friendly setup
    data_agent = Agent(
        name="Data Processor",
        role="Data Processing Specialist",
        goal="Process and analyze data efficiently",
        backstory="You specialize in data processing with focus on accuracy and efficiency.",
        verbose=True,
        llm="gpt-5-nano"
    )
    
    monitor_agent = Agent(
        name="Performance Monitor", 
        role="System Performance Analyst",
        goal="Monitor and optimize system performance",
        backstory="You analyze system metrics and provide optimization recommendations.",
        verbose=True,
        llm="gpt-5-nano"
    )
    
    # Create tasks that generate trackable metrics
    processing_task = Task(
        description="Process a dataset of customer feedback and extract key themes and sentiments",
        expected_output="A structured analysis of customer feedback themes",
        agent=data_agent
    )
    
    monitoring_task = Task(
        description="Analyze the data processing workflow and suggest performance optimizations",
        expected_output="Performance analysis report with optimization recommendations", 
        agent=monitor_agent,
        context=[processing_task]
    )
    
    # Initialize with telemetry awareness
    agents = PraisonAIAgents(
        agents=[data_agent, monitor_agent],
        tasks=[processing_task, monitoring_task],
        verbose=True
    )
    
    print("🚀 Running telemetry-enabled workflow...")
    result = agents.run()
    
    # Demonstrate telemetry integration
    print("\n" + "="*60)
    print("📡 TELEMETRY INTEGRATION DEMO")
    print("="*60)
    
    # Basic metrics display
    print(f"\n📊 LIVE METRICS:")
    agents.display_token_usage()
    
    # Pattern analysis
    analyze_interaction_patterns(agents)
    
    # Export capabilities
    print(f"\n💾 EXPORT CAPABILITIES:")
    success = export_metrics_to_file(agents)
    
    if success:
        print("• Metrics exported for external analytics")
        print("• Data can be imported into monitoring dashboards")
        print("• Compatible with business intelligence tools")
    
    # Privacy and security notes
    print(f"\n🔒 PRIVACY & SECURITY:")
    print("• Token metrics contain no personal data")
    print("• Only aggregated usage statistics tracked")
    print("• No prompt content or responses stored")
    print("• Telemetry can be disabled via configuration")
    
    # Monitoring recommendations
    token_summary = agents.get_token_usage_summary()
    total_tokens = token_summary.get("total_metrics", {}).get("total_tokens", 0)
    
    print(f"\n📈 MONITORING RECOMMENDATIONS:")
    if total_tokens > 5000:
        print("• Set up automated cost alerts")
        print("• Consider implementing token budgets")
        print("• Monitor daily/weekly usage trends")
    else:
        print("• Current usage is within normal ranges")
        print("• Consider baseline metrics for comparison")
    
    print("• Integrate with existing observability stack")
    print("• Set up automated reporting for stakeholders")
    
    print("\n✅ Telemetry integration demo completed!")

if __name__ == "__main__":
    main()
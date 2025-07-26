"""
Advanced Agent Integration Example

This example demonstrates advanced token tracking features including:
- Task-level token metrics
- Multi-model comparison
- Real-time monitoring during execution
- Token budget enforcement
"""

from praisonaiagents import PraisonAIAgents, Agent, Task
import time

class TokenBudgetManager:
    """Simple token budget manager for demonstration."""
    
    def __init__(self, max_tokens=10000):
        self.max_tokens = max_tokens
        self.start_time = time.time()
    
    def check_budget(self, agents):
        """Check if we're within token budget."""
        summary = agents.get_token_usage_summary()
        if "error" in summary:
            return True, "Token tracking unavailable"
        
        current_tokens = summary.get("total_metrics", {}).get("total_tokens", 0)
        remaining = self.max_tokens - current_tokens
        
        if remaining <= 0:
            return False, f"Budget exceeded! Used: {current_tokens:,}, Budget: {self.max_tokens:,}"
        
        return True, f"Budget OK. Used: {current_tokens:,}/{self.max_tokens:,} ({remaining:,} remaining)"
    
    def get_usage_rate(self, agents):
        """Calculate tokens per minute."""
        elapsed = time.time() - self.start_time
        summary = agents.get_token_usage_summary()
        
        if "error" in summary or elapsed == 0:
            return 0
        
        current_tokens = summary.get("total_metrics", {}).get("total_tokens", 0)
        return current_tokens / (elapsed / 60)  # tokens per minute

def monitor_task_execution(agents, budget_manager):
    """Monitor execution with real-time updates."""
    print("\n🔄 EXECUTION MONITORING:")
    
    while True:
        # Check budget
        within_budget, message = budget_manager.check_budget(agents)
        rate = budget_manager.get_usage_rate(agents)
        
        print(f"📊 {message} | Rate: {rate:.1f} tokens/min")
        
        if not within_budget:
            print("❌ BUDGET EXCEEDED - Consider stopping execution")
            break
        
        # In a real implementation, you might check task completion status
        time.sleep(2)  # Check every 2 seconds
        break  # For demo purposes, just check once

def compare_model_efficiency(agents):
    """Compare efficiency across different models."""
    summary = agents.get_token_usage_summary()
    
    if "error" in summary:
        print("❌ Cannot compare models - token tracking unavailable")
        return
    
    by_model = summary.get("by_model", {})
    
    if not by_model:
        print("ℹ️  No model comparison data available")
        return
    
    print(f"\n⚖️  MODEL EFFICIENCY COMPARISON:")
    
    for model, metrics in by_model.items():
        total_tokens = metrics.get("total_tokens", 0)
        input_tokens = metrics.get("input_tokens", 0)
        output_tokens = metrics.get("output_tokens", 0)
        
        if input_tokens > 0:
            efficiency = output_tokens / input_tokens
            print(f"\n🤖 {model}:")
            print(f"  Total Tokens: {total_tokens:,}")
            print(f"  Input/Output Ratio: 1:{efficiency:.2f}")
            print(f"  Efficiency Rating: {'⭐⭐⭐' if efficiency < 1.5 else '⭐⭐' if efficiency < 2.5 else '⭐'}")

def analyze_task_performance(agents):
    """Analyze performance at the task level."""
    detailed_report = agents.get_detailed_token_report()
    
    if "error" in detailed_report:
        print("❌ Cannot analyze tasks - token tracking unavailable")
        return
    
    recent_interactions = detailed_report.get("recent_interactions", [])
    
    print(f"\n📋 TASK-LEVEL PERFORMANCE:")
    
    # Group interactions by agent (proxy for task analysis)
    agent_performance = {}
    
    for interaction in recent_interactions:
        agent = interaction.get("agent", "Unknown")
        metrics = interaction.get("metrics", {})
        
        if agent not in agent_performance:
            agent_performance[agent] = {
                "interactions": 0,
                "total_tokens": 0,
                "avg_tokens": 0
            }
        
        agent_performance[agent]["interactions"] += 1
        agent_performance[agent]["total_tokens"] += metrics.get("total_tokens", 0)
    
    # Calculate averages
    for agent, perf in agent_performance.items():
        if perf["interactions"] > 0:
            perf["avg_tokens"] = perf["total_tokens"] / perf["interactions"]
    
    # Display results
    for agent, perf in sorted(agent_performance.items(), key=lambda x: x[1]["total_tokens"], reverse=True):
        print(f"\n👤 {agent}:")
        print(f"  Interactions: {perf['interactions']}")
        print(f"  Total Tokens: {perf['total_tokens']:,}")
        print(f"  Avg per Interaction: {perf['avg_tokens']:.0f}")
        
        # Performance indicators
        if perf["avg_tokens"] > 2000:
            print(f"  📈 High token usage - consider optimization")
        elif perf["avg_tokens"] < 500:
            print(f"  📉 Low token usage - efficient execution")
        else:
            print(f"  ✅ Moderate token usage - balanced")

def main():
    # Initialize budget manager
    budget_manager = TokenBudgetManager(max_tokens=15000)
    
    # Create diverse agents for comprehensive testing
    researcher_agent = Agent(
        name="Research Specialist",
        role="Senior Research Analyst", 
        goal="Conduct thorough research and analysis",
        backstory="You are a meticulous researcher who produces comprehensive reports.",
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    summarizer_agent = Agent(
        name="Content Summarizer",
        role="Information Synthesis Expert",
        goal="Create concise, accurate summaries",
        backstory="You excel at distilling complex information into clear, actionable insights.",
        verbose=True,
        llm="gpt-4o-mini"  # Same model for fair comparison
    )
    
    optimizer_agent = Agent(
        name="Process Optimizer",
        role="Efficiency Consultant",
        goal="Optimize workflows and processes",
        backstory="You identify inefficiencies and recommend improvements.",
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create tasks with varying complexity
    research_task = Task(
        description="""
        Research the impact of artificial intelligence on job markets in the next 5 years.
        Include analysis of:
        - Industries most affected
        - New job categories emerging
        - Skills that will be in demand
        - Policy recommendations
        """,
        expected_output="Comprehensive research report on AI's impact on employment",
        agent=researcher_agent
    )
    
    summary_task = Task(
        description="Create an executive summary of the AI job market research",
        expected_output="2-paragraph executive summary highlighting key findings",
        agent=summarizer_agent,
        context=[research_task]
    )
    
    optimization_task = Task(
        description="Analyze the research and summarization workflow for efficiency improvements",
        expected_output="Process optimization recommendations",
        agent=optimizer_agent,
        context=[research_task, summary_task]
    )
    
    # Initialize agents system
    agents = PraisonAIAgents(
        agents=[researcher_agent, summarizer_agent, optimizer_agent],
        tasks=[research_task, summary_task, optimization_task],
        verbose=True
    )
    
    print("🚀 Starting advanced token tracking demo...")
    print(f"💰 Token Budget: {budget_manager.max_tokens:,} tokens")
    
    # Pre-execution budget check
    within_budget, message = budget_manager.check_budget(agents)
    print(f"📊 Initial Status: {message}")
    
    # Execute tasks
    result = agents.run()
    
    # Post-execution analysis
    print("\n" + "="*70)
    print("🔬 ADVANCED ANALYSIS RESULTS")
    print("="*70)
    
    # Final budget check
    within_budget, message = budget_manager.check_budget(agents)
    rate = budget_manager.get_usage_rate(agents)
    print(f"\n💰 FINAL BUDGET STATUS:")
    print(f"Status: {message}")
    print(f"Usage Rate: {rate:.1f} tokens/min")
    
    # Comprehensive analysis
    compare_model_efficiency(agents)
    analyze_task_performance(agents)
    
    # Advanced metrics
    detailed_report = agents.get_detailed_token_report()
    if "error" not in detailed_report:
        cost_info = detailed_report.get("cost_estimate", {})
        print(f"\n💵 COST ANALYSIS:")
        print(f"Estimated Cost: {cost_info.get('total_cost', 'N/A')}")
        
        summary = detailed_report.get("summary", {})
        interactions = summary.get("total_interactions", 0)
        if interactions > 0:
            total_tokens = summary.get("total_metrics", {}).get("total_tokens", 0)
            avg_per_interaction = total_tokens / interactions
            print(f"Avg Tokens/Interaction: {avg_per_interaction:.0f}")
    
    # Recommendations
    print(f"\n💡 OPTIMIZATION RECOMMENDATIONS:")
    
    summary = agents.get_token_usage_summary()
    if "error" not in summary:
        total_tokens = summary.get("total_metrics", {}).get("total_tokens", 0)
        
        if total_tokens > 10000:
            print("• Consider breaking down complex tasks into smaller subtasks")
            print("• Implement progressive elaboration for large research tasks")
        
        by_agent = summary.get("by_agent", {})
        if len(by_agent) > 1:
            max_agent = max(by_agent.items(), key=lambda x: x[1].get("total_tokens", 0))
            print(f"• Highest usage: {max_agent[0]} - consider optimization")
    
    print("• Monitor token budgets in production environments")
    print("• Set up automated alerts for unusual usage patterns")
    
    print("\n✅ Advanced agent integration demo completed!")

if __name__ == "__main__":
    main()
"""
Session Metrics Tracking Example

This example shows how to track token usage across multiple agents
and tasks in a single session. Demonstrates model-specific and 
agent-specific token tracking capabilities.
"""

from praisonaiagents import PraisonAIAgents, Agent, Task

def main():
    # Create multiple agents with different roles
    analyst_agent = Agent(
        name="Data Analyst",
        role="Senior Data Analyst",
        goal="Analyze data and provide insights",
        backstory="You are an experienced data analyst with expertise in market research.",
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    writer_agent = Agent(
        name="Content Writer", 
        role="Technical Writer",
        goal="Create well-structured content",
        backstory="You are a skilled technical writer who creates clear, engaging content.",
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create multiple tasks
    analysis_task = Task(
        description="Analyze the current trends in artificial intelligence and machine learning",
        expected_output="A detailed analysis of AI/ML trends with key insights",
        agent=analyst_agent
    )
    
    writing_task = Task(
        description="Write a blog post about the AI trends analysis",
        expected_output="A well-structured blog post about AI trends",
        agent=writer_agent,
        context=[analysis_task]  # Use previous task output
    )
    
    # Initialize the agents system
    agents = PraisonAIAgents(
        agents=[analyst_agent, writer_agent],
        tasks=[analysis_task, writing_task],
        verbose=True
    )
    
    print("🚀 Running multi-agent workflow...")
    # Run all tasks
    result = agents.run()
    
    # Get comprehensive session metrics
    print("\n" + "="*60)
    print("📊 COMPREHENSIVE SESSION METRICS")
    print("="*60)
    
    token_summary = agents.get_token_usage_summary()
    
    if "error" in token_summary:
        print("❌ Token tracking not available")
        return
    
    # Overall session stats
    print(f"\n🔢 SESSION OVERVIEW:")
    print(f"Total Interactions: {token_summary.get('total_interactions', 0)}")
    print(f"Total Tokens: {token_summary.get('total_metrics', {}).get('total_tokens', 0):,}")
    
    # Breakdown by model
    by_model = token_summary.get('by_model', {})
    if by_model:
        print(f"\n🤖 USAGE BY MODEL:")
        for model, metrics in by_model.items():
            print(f"  {model}:")
            print(f"    Total: {metrics.get('total_tokens', 0):,} tokens")
            print(f"    Input: {metrics.get('input_tokens', 0):,}")
            print(f"    Output: {metrics.get('output_tokens', 0):,}")
    
    # Breakdown by agent
    by_agent = token_summary.get('by_agent', {})
    if by_agent:
        print(f"\n👥 USAGE BY AGENT:")
        for agent_name, metrics in by_agent.items():
            print(f"  {agent_name}:")
            print(f"    Total: {metrics.get('total_tokens', 0):,} tokens")
            print(f"    Input: {metrics.get('input_tokens', 0):,}")
            print(f"    Output: {metrics.get('output_tokens', 0):,}")
    
    # Use the built-in display method
    print(f"\n📋 FORMATTED DISPLAY:")
    agents.display_token_usage()
    
    print("✅ Multi-agent workflow completed!")

if __name__ == "__main__":
    main()
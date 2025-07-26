"""
Cost Estimation Example - SIMPLIFIED VERSION
This example demonstrates automatic token metrics and cost tracking 
using just Agent(metrics=True). All tracking and display is automatic!
For custom cost calculations, you can still access the detailed reports.
"""
from praisonaiagents import PraisonAIAgents, Agent, Task

def main():
    # Create agents with metrics=True for automatic cost tracking
    research_agent = Agent(
        name="Market Researcher",
        role="Senior Market Research Analyst", 
        goal="Conduct comprehensive market research",
        backstory="You are a seasoned market researcher with 10+ years of experience.",
        verbose=True,
        llm="gpt-4o-mini",
        metrics=True  # 🎯 Enable automatic metrics tracking
    )
    
    strategy_agent = Agent(
        name="Business Strategist",
        role="Strategic Business Consultant",
        goal="Develop actionable business strategies",
        backstory="You are a strategic consultant who translates research into business plans.",
        verbose=True,
        llm="gpt-4o-mini",
        metrics=True  # 🎯 Enable automatic metrics tracking
    )
    
    # Create tasks that will generate substantial token usage
    research_task = Task(
        description="""
        Conduct a comprehensive market analysis for electric vehicles in Europe including:
        1. Market size and growth projections
        2. Key competitors and market share
        3. Regulatory environment and policies
        4. Consumer adoption trends
        5. Technology developments
        """,
        expected_output="A detailed 500-word market research report with actionable insights",
        agent=research_agent
    )
    
    strategy_task = Task(
        description="""
        Based on the market research, develop a go-to-market strategy for a new 
        electric vehicle startup including:
        1. Target market segments
        2. Competitive positioning
        3. Pricing strategy
        4. Distribution channels
        5. Marketing approach
        """,
        expected_output="A comprehensive business strategy document with specific recommendations",
        agent=strategy_agent,
        context=[research_task]
    )
    
    # Initialize and run
    agents = PraisonAIAgents(
        agents=[research_agent, strategy_agent],
        tasks=[research_task, strategy_task],
        verbose=True
    )
    
    print("🚀 Running cost analysis workflow...")
    # Auto-display includes cost estimates!
    result = agents.run()
    
    # Optional: Get detailed cost report for custom analysis
    print("\n💡 For detailed cost analysis, you can still access:")
    print("• agents.get_detailed_token_report() - Full breakdown")
    print("• agents.get_token_usage_summary() - Session summary")
    
    print("\n✅ Cost analysis completed!")

if __name__ == "__main__":
    main()
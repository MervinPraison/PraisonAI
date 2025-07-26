"""
Cost Estimation Example

This example demonstrates how to get detailed cost estimates
for your agent workflows based on token usage. Useful for
budgeting and cost optimization.
"""

from praisonaiagents import PraisonAIAgents, Agent, Task

def calculate_custom_costs(token_summary, pricing_model="gpt-4o-mini"):
    """
    Calculate costs based on actual pricing models.
    You can customize this for different providers and models.
    """
    # Example pricing (as of 2024 - update with current rates)
    pricing = {
        "gpt-4o-mini": {
            "input": 0.00015,   # $0.00015 per 1K input tokens
            "output": 0.0006    # $0.0006 per 1K output tokens
        },
        "gpt-4o": {
            "input": 0.0025,    # $0.0025 per 1K input tokens  
            "output": 0.01      # $0.01 per 1K output tokens
        },
        "claude-3-sonnet": {
            "input": 0.003,     # $0.003 per 1K input tokens
            "output": 0.015     # $0.015 per 1K output tokens
        }
    }
    
    if pricing_model not in pricing:
        return {"error": f"Pricing not available for {pricing_model}"}
    
    rates = pricing[pricing_model]
    total_metrics = token_summary.get("total_metrics", {})
    
    input_tokens = total_metrics.get("input_tokens", 0)
    output_tokens = total_metrics.get("output_tokens", 0)
    
    input_cost = (input_tokens / 1000) * rates["input"]
    output_cost = (output_tokens / 1000) * rates["output"] 
    total_cost = input_cost + output_cost
    
    return {
        "model": pricing_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "currency": "USD"
    }

def main():
    # Create agents for a more complex workflow
    research_agent = Agent(
        name="Market Researcher",
        role="Senior Market Research Analyst", 
        goal="Conduct comprehensive market research",
        backstory="You are a seasoned market researcher with 10+ years of experience.",
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    strategy_agent = Agent(
        name="Business Strategist",
        role="Strategic Business Consultant",
        goal="Develop actionable business strategies",
        backstory="You are a strategic consultant who translates research into business plans.",
        verbose=True,
        llm="gpt-4o-mini"
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
    result = agents.run()
    
    # Get detailed cost report
    print("\n" + "="*60)
    print("💰 DETAILED COST ANALYSIS")
    print("="*60)
    
    # Use built-in detailed report
    detailed_report = agents.get_detailed_token_report()
    
    if "error" in detailed_report:
        print("❌ Token tracking not available")
        return
    
    # Display built-in cost estimate
    cost_info = detailed_report.get("cost_estimate", {})
    print(f"\n📊 BUILT-IN COST ESTIMATES:")
    print(f"Input Cost: {cost_info.get('input_cost', 'N/A')}")
    print(f"Output Cost: {cost_info.get('output_cost', 'N/A')}")
    print(f"Total Cost: {cost_info.get('total_cost', 'N/A')}")
    print(f"Note: {cost_info.get('note', '')}")
    
    # Custom cost calculation
    token_summary = detailed_report.get("summary", {})
    custom_costs = calculate_custom_costs(token_summary, "gpt-4o-mini")
    
    print(f"\n💵 DETAILED COST BREAKDOWN ({custom_costs['model']}):")
    print(f"Input Tokens: {custom_costs['input_tokens']:,} × ${custom_costs['input_cost']/custom_costs['input_tokens']*1000:.4f}/1K = ${custom_costs['input_cost']:.4f}")
    print(f"Output Tokens: {custom_costs['output_tokens']:,} × ${custom_costs['output_cost']/custom_costs['output_tokens']*1000:.4f}/1K = ${custom_costs['output_cost']:.4f}")
    print(f"Total Cost: ${custom_costs['total_cost']:.4f} {custom_costs['currency']}")
    
    # Cost optimization suggestions
    print(f"\n💡 COST OPTIMIZATION TIPS:")
    total_tokens = custom_costs['input_tokens'] + custom_costs['output_tokens']
    
    if total_tokens > 10000:
        print("• Consider using gpt-3.5-turbo for less complex tasks")
        print("• Break down large tasks into smaller, focused subtasks")
    
    if custom_costs['output_tokens'] > custom_costs['input_tokens'] * 2:
        print("• High output-to-input ratio detected")
        print("• Consider more concise prompts to reduce output tokens")
    
    print(f"• Estimated monthly cost at this usage: ${custom_costs['total_cost'] * 30:.2f}")
    
    print("\n✅ Cost analysis completed!")

if __name__ == "__main__":
    main()
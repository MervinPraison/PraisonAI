"""
Basic Token Tracking Example

This example demonstrates how to access and view basic token metrics 
after running PraisonAI agents. Shows the simplest way to get token 
usage information from your agent workflows.
"""

from praisonaiagents import PraisonAIAgents, Agent, Task

def main():
    # Create a simple agent
    research_agent = Agent(
        name="Research Agent",
        role="Research Specialist", 
        goal="Find information about a topic",
        backstory="You are an expert researcher who finds comprehensive information.",
        verbose=True,
        llm="gpt-4o-mini"  # Use a cost-effective model for examples
    )
    
    # Create a simple task
    research_task = Task(
        description="Research the current state of renewable energy technology in 2024",
        expected_output="A summary of recent developments in renewable energy",
        agent=research_agent
    )
    
    # Initialize the agents system
    agents = PraisonAIAgents(
        agents=[research_agent],
        tasks=[research_task],
        verbose=True
    )
    
    print("🚀 Running agent task...")
    # Run the task
    result = agents.run()
    
    # Get basic token usage summary
    print("\n" + "="*50)
    print("📊 BASIC TOKEN USAGE")
    print("="*50)
    
    token_summary = agents.get_token_usage_summary()
    
    if "error" in token_summary:
        print("❌ Token tracking not available")
        print("Make sure you're using a supported LLM provider")
    else:
        total_metrics = token_summary.get("total_metrics", {})
        print(f"Total Tokens Used: {total_metrics.get('total_tokens', 0):,}")
        print(f"Input Tokens: {total_metrics.get('input_tokens', 0):,}")
        print(f"Output Tokens: {total_metrics.get('output_tokens', 0):,}")
        print(f"Number of LLM Calls: {token_summary.get('total_interactions', 0)}")
    
    print("\n✅ Task completed!")
    print(f"🎯 Result: {result}")

if __name__ == "__main__":
    main()
"""
Basic Token Tracking Example - SIMPLIFIED VERSION
This example demonstrates the simplest way to enable token metrics 
tracking using just Agent(metrics=True). The token usage summary 
will be automatically displayed when tasks complete!
"""
from praisonaiagents import PraisonAIAgents, Agent, Task

def main():
    # Create a simple agent with metrics=True - that's it!
    research_agent = Agent(
        name="Research Agent",
        role="Research Specialist", 
        goal="Find information about a topic",
        backstory="You are an expert researcher who finds comprehensive information.",
        verbose=True,
        llm="gpt-4o-mini",  # Use a cost-effective model for examples
        metrics=True  # 🎯 SIMPLIFIED: Just add this parameter!
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
    # Run the task - token metrics will auto-display at the end!
    result = agents.run()
    
    print("\n✅ Task completed!")
    print(f"🎯 Result: {result}")

if __name__ == "__main__":
    main()
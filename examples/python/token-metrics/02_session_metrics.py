"""
Session Metrics Tracking Example - SIMPLIFIED VERSION
This example shows how to track token usage across multiple agents
with the simplified Agent(metrics=True) approach. Metrics are 
automatically displayed when any agent has metrics enabled!
"""
from praisonaiagents import PraisonAIAgents, Agent, Task

def main():
    # Create multiple agents - just add metrics=True to enable tracking
    analyst_agent = Agent(
        name="Data Analyst",
        role="Senior Data Analyst",
        goal="Analyze data and provide insights",
        backstory="You are an experienced data analyst with expertise in market research.",
        verbose=True,
        llm="gpt-4o-mini",
        metrics=True  # 🎯 Enable metrics tracking
    )
    
    writer_agent = Agent(
        name="Content Writer", 
        role="Technical Writer",
        goal="Create well-structured content",
        backstory="You are a skilled technical writer who creates clear, engaging content.",
        verbose=True,
        llm="gpt-4o-mini",
        metrics=True  # 🎯 Enable metrics tracking
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
    # Run all tasks - comprehensive metrics will auto-display!
    result = agents.run()
    
    print("✅ Multi-agent workflow completed!")
    print(f"🎯 Final result: {result}")

if __name__ == "__main__":
    main()
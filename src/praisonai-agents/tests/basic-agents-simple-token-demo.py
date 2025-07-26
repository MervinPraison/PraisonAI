#!/usr/bin/env python3
"""
Simple Token Tracking Example

This example demonstrates how to access and view token metrics 
after running a PraisonAI agent. Shows how to get token usage 
information from your agent workflows.
"""

from praisonaiagents import PraisonAIAgents, Agent, Task

def main():
    # Create an agent to answer questions
    question_agent = Agent(
        name="Question Agent",
        role="Science Explainer",
        goal="Provide clear scientific explanations",
        backstory="You are a knowledgeable assistant who explains scientific concepts clearly.",
        instructions="You are a helpful assistant",
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create a task to answer the question
    answer_task = Task(
        description="Why sky is Blue?",
        expected_output="A clear scientific explanation of why the sky appears blue",
        agent=question_agent
    )
    
    # Initialize the agents system
    agents = PraisonAIAgents(
        agents=[question_agent],
        tasks=[answer_task],
        verbose=True
    )
    
    print("🚀 Running agent task...")
    print("❓ Question: Why sky is Blue?")
    print("-" * 50)
    
    # Run the task
    result = agents.run()
    
    # Get token usage summary
    print("\n" + "="*50)
    print("📊 TOKEN USAGE SUMMARY")
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
    print(f"\n🎯 Answer:\n{result}")

if __name__ == "__main__":
    main()
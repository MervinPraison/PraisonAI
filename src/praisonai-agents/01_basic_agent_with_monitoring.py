"""
Basic Agent with Performance Monitoring - Example 1

Simple agent demonstrating performance monitoring basics:
- Function execution timing with @monitor_function decorator
- API call tracking with track_api_call context manager
- Basic performance statistics retrieval

This example shows the fundamental pattern for adding performance monitoring
to any PraisonAI agent workflow.
"""

from praisonaiagents import Agent
from praisonaiagents.telemetry import monitor_function, track_api_call, get_performance_report
import time

# Monitored function to demonstrate timing
@monitor_function("question_processing")
def process_question(question):
    """Process the incoming question with performance tracking."""
    print(f"Processing question: {question}")
    # Simulate some processing time
    time.sleep(0.1)
    return f"Processed: {question}"

# Main execution function with monitoring
@monitor_function("agent_execution")  
def main():
    """Main function demonstrating basic agent with performance monitoring."""
    print("=" * 60)
    print("EXAMPLE 1: Basic Agent with Performance Monitoring")
    print("=" * 60)
    
    # Process the question with monitoring
    question = "Why is the sky blue?"
    processed_question = process_question(question)
    
    # Create agent
    agent = Agent(
        instructions="You are a helpful assistant that explains scientific concepts simply",
        llm="gpt-5-nano"
    )
    
    # Track the API call performance
    with track_api_call("sky_explanation_request"):
        print("\n🚀 Starting agent execution...")
        result = agent.start(processed_question)
        print(f"\n📝 Agent Response:\n{result}")
    
    # Display performance statistics
    print("\n" + "=" * 60)
    print("📊 PERFORMANCE MONITORING RESULTS")
    print("=" * 60)
    
    # Get and display performance report
    report = get_performance_report()
    print(report)
    
    return result

if __name__ == "__main__":
    result = main()
    print(f"\n✅ Example completed successfully!")
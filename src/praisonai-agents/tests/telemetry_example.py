"""
Example demonstrating telemetry usage in PraisonAI Agents.

This example shows how to:
1. Enable telemetry with OpenTelemetry backend
2. Use automatic instrumentation
3. Use manual instrumentation
4. Export telemetry data
"""

import os
from praisonaiagents import (
    Agent, Task, PraisonAIAgents,
    enable_telemetry, disable_telemetry, get_telemetry_collector
)
from praisonaiagents.tools import DuckDuckGoSearchTool

# Set current path to package root directory
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def basic_telemetry_example():
    """Basic example with automatic telemetry."""
    print("\n=== Basic Telemetry Example ===\n")
    
    # Enable telemetry - it will automatically instrument all agents and tasks
    telemetry = enable_telemetry(
        backend="opentelemetry",
        service_name="praisonai-demo",
        exporter="console"  # Use console exporter for demo
    )
    
    if not telemetry:
        print("Telemetry dependencies not installed. Install with:")
        print("pip install praisonaiagents[telemetry]")
        return
    
    # Create agents - telemetry will be automatically added
    researcher = Agent(
        name="Researcher",
        role="Information gatherer",
        goal="Find accurate information about topics",
        backstory="You are an expert researcher with attention to detail",
        tools=[DuckDuckGoSearchTool()],
        llm="gpt-4o-mini"
    )
    
    writer = Agent(
        name="Writer",
        role="Content creator",
        goal="Create engaging content based on research",
        backstory="You are a skilled writer who creates clear, engaging content",
        llm="gpt-4o-mini"
    )
    
    # Create tasks
    research_task = Task(
        name="research_task",
        description="Research the latest developments in quantum computing",
        expected_output="A summary of recent quantum computing breakthroughs",
        agent=researcher
    )
    
    writing_task = Task(
        name="writing_task",
        description="Write a blog post about quantum computing developments",
        expected_output="A 300-word blog post suitable for a general audience",
        agent=writer,
        context=[research_task]  # Depends on research task
    )
    
    # Create workflow
    workflow = PraisonAIAgents(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
        process="sequential",
        verbose=True
    )
    
    # Run workflow - all telemetry will be collected automatically
    print("Running workflow with telemetry enabled...\n")
    result = workflow.start()
    
    # Get telemetry metrics
    metrics = telemetry.get_metrics()
    print("\n=== Telemetry Metrics ===")
    print(f"Agent executions: {metrics['agent_executions']}")
    print(f"Task completions: {metrics['task_completions']}")
    print(f"Tool calls: {metrics['tool_calls']}")
    print(f"LLM calls: {metrics['llm_calls']}")
    print(f"Total tokens: {metrics['total_tokens']}")
    print(f"Errors: {metrics['errors']}")
    
    # Disable telemetry
    disable_telemetry()
    
    return result


def manual_telemetry_example():
    """Example with manual telemetry instrumentation."""
    print("\n=== Manual Telemetry Example ===\n")
    
    # Enable telemetry
    telemetry = enable_telemetry(backend="custom")  # Use logging backend
    
    if not telemetry:
        return
    
    # Create agent without automatic instrumentation
    agent = Agent(
        name="Assistant",
        role="General assistant",
        goal="Help with various tasks",
        backstory="You are a helpful AI assistant",
        llm="gpt-4o-mini"
    )
    
    # Manual telemetry - trace custom operations
    with telemetry.trace_agent_execution("Assistant", custom_field="demo"):
        response = agent.chat("What is the capital of France?")
        print(f"Response: {response}")
    
    # Use telemetry decorator for functions
    @telemetry.trace(span_type="custom_operation")
    def process_data(data):
        """Process some data with telemetry."""
        # Simulate processing
        import time
        time.sleep(0.1)
        
        # Record custom metrics
        telemetry.record_metric("data.processed", len(data), {"type": "text"})
        
        return data.upper()
    
    # Call traced function
    result = process_data("hello world")
    print(f"Processed: {result}")
    
    # Manual event recording
    telemetry._backend.record_event("custom_event", {
        "user_action": "manual_example",
        "success": True
    })
    
    disable_telemetry()


def advanced_telemetry_example():
    """Advanced example with custom telemetry backend and OTLP export."""
    print("\n=== Advanced Telemetry Example ===\n")
    
    # For OTLP export, you would typically have an OTLP collector running
    # For this example, we'll use console export
    
    # Enable telemetry with OTLP configuration
    telemetry = enable_telemetry(
        backend="opentelemetry",
        service_name="praisonai-production",
        service_version="1.0.0",
        exporter="otlp",  # Would export to OTLP collector
        otlp_endpoint="localhost:4317",  # OTLP collector endpoint
        metric_export_interval=10000  # Export metrics every 10 seconds
    )
    
    if not telemetry:
        print("Telemetry not available. Using fallback.")
        # Even without telemetry, the code still works
        agent = Agent(
            name="Analyst",
            role="Data analyst",
            goal="Analyze data and provide insights",
            backstory="You are an experienced data analyst",
            llm="gpt-4o-mini"
        )
        
        result = agent.chat("Analyze the trend: [10, 15, 13, 18, 22, 20, 25]")
        print(f"Analysis: {result}")
        return
    
    # Create instrumented agent
    agent = Agent(
        name="Analyst",
        role="Data analyst", 
        goal="Analyze data and provide insights",
        backstory="You are an experienced data analyst",
        llm="gpt-4o-mini"
    )
    
    # Use context manager for grouped operations
    with telemetry.trace("analysis_workflow", workflow_type="data_analysis"):
        # Multiple operations within the same trace context
        response1 = agent.chat("What is the mean of: [10, 15, 13, 18, 22, 20, 25]")
        response2 = agent.chat("What is the trend in this data?")
        response3 = agent.chat("Predict the next 3 values")
        
        # Record custom metrics
        telemetry.record_metric("analysis.steps", 3)
        telemetry.record_cost(0.001, model="gpt-4o-mini")  # Track costs
    
    print("\nAnalysis complete. Telemetry data exported to OTLP collector.")
    
    disable_telemetry()


def telemetry_with_errors_example():
    """Example showing how telemetry handles errors."""
    print("\n=== Telemetry with Error Handling ===\n")
    
    telemetry = enable_telemetry()
    
    if not telemetry:
        return
    
    agent = Agent(
        name="ErrorProneAgent",
        role="Test agent",
        goal="Test error handling",
        backstory="An agent for testing",
        llm="gpt-4o-mini"
    )
    
    # This will be traced and errors will be recorded
    try:
        with telemetry.trace_agent_execution("ErrorProneAgent"):
            # Simulate an error by using an invalid tool
            agent.execute_tool("non_existent_tool", "test")
    except Exception as e:
        print(f"Caught error: {e}")
        print("Error was recorded in telemetry")
    
    # Check error metrics
    metrics = telemetry.get_metrics()
    print(f"\nError count in telemetry: {metrics['errors']}")
    
    disable_telemetry()


if __name__ == "__main__":
    print("PraisonAI Agents Telemetry Examples")
    print("===================================")
    
    # Run basic example
    basic_telemetry_example()
    
    # Run manual instrumentation example
    manual_telemetry_example()
    
    # Run advanced example (commented out as it requires OTLP collector)
    # advanced_telemetry_example()
    
    # Run error handling example
    telemetry_with_errors_example()
    
    print("\n✅ All telemetry examples completed!")
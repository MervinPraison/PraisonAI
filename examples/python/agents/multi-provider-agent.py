"""
Multi-Provider/Multi-Model Agent Example

This example demonstrates how to use multiple AI providers/models with intelligent
agent-based selection for cost optimization and performance.
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.agent import MultiModelAgent
from praisonaiagents.llm.model_router import ModelRouter, ModelProfile, TaskComplexity

# Example 1: Simple Multi-Model Agent with Auto-Routing
def example_auto_routing():
    """Example of automatic model routing based on task complexity"""
    print("\n=== Example 1: Auto-Routing Multi-Model Agent ===\n")
    
    # Create a multi-model agent that automatically selects models
    research_agent = MultiModelAgent(
        name="Smart Researcher",
        role="Adaptive Research Assistant",
        goal="Research topics using the most appropriate AI model",
        backstory="I analyze task complexity and route to the best model",
        models=["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022"],
        routing_strategy="auto",  # Automatic model selection
        verbose=True
    )
    
    # Create tasks with different complexity levels
    simple_task = Task(
        name="simple_calculation",
        description="Calculate the sum of 1542 and 2873",
        expected_output="The numerical result",
        agent=research_agent
    )
    
    moderate_task = Task(
        name="summarize_article", 
        description="Summarize the key points about renewable energy trends",
        expected_output="A concise summary with main points",
        agent=research_agent
    )
    
    complex_task = Task(
        name="analyze_code",
        description="Implement a Python function to find the longest palindromic substring in a given string with O(n^2) complexity",
        expected_output="Complete Python implementation with explanation",
        agent=research_agent
    )
    
    # Run the tasks
    agents = PraisonAIAgents(
        agents=[research_agent],
        tasks=[simple_task, moderate_task, complex_task],
        process="sequential",
        verbose=True
    )
    
    results = agents.start()
    
    # Show usage report
    print("\n=== Model Usage Report ===")
    print(research_agent.get_usage_report())


# Example 2: Cost-Optimized Workflow with Routing
def example_cost_optimized_workflow():
    """Example of cost-optimized workflow with model routing"""
    print("\n=== Example 2: Cost-Optimized Workflow ===\n")
    
    # Create custom model router with cost threshold
    cost_router = ModelRouter(
        cost_threshold=0.01,  # Max $0.01 per 1k tokens
        preferred_providers=["google", "openai", "anthropic"]  # Provider preference
    )
    
    # Create specialized agents with different model strategies
    analyzer = MultiModelAgent(
        name="Cost-Conscious Analyzer",
        role="Data Analyzer",
        goal="Analyze data efficiently while minimizing costs",
        models={
            "gemini/gemini-1.5-flash": {},
            "gpt-4o-mini": {},
            "deepseek-chat": {}
        },
        model_router=cost_router,
        routing_strategy="cost-optimized",
        verbose=True
    )
    
    writer = MultiModelAgent(
        name="Quality Writer",
        role="Content Writer", 
        goal="Create high-quality content",
        models={
            "claude-3-5-sonnet-20241022": {},
            "gpt-4o": {}
        },
        routing_strategy="performance-optimized",  # Prefer better models
        verbose=True
    )
    
    # Create workflow tasks
    analysis_task = Task(
        name="analyze_data",
        description="Analyze this dataset: [1, 2, 3, 4, 5]. Find mean, median, and mode.",
        expected_output="Statistical analysis results",
        agent=analyzer
    )
    
    writing_task = Task(
        name="write_report",
        description="Write a professional report based on the analysis",
        expected_output="Professional report with insights",
        agent=writer,
        context=[analysis_task]  # Use results from analysis
    )
    
    # Run workflow
    workflow = PraisonAIAgents(
        agents=[analyzer, writer],
        tasks=[analysis_task, writing_task],
        process="sequential",
        verbose=True
    )
    
    results = workflow.start()
    
    # Show cost comparison
    print("\n=== Cost Analysis ===")
    print(f"Analyzer costs: {analyzer.get_usage_report()}")
    print(f"Writer costs: {writer.get_usage_report()}")


# Example 3: Auto Agent Mode with Multi-Provider Support
def example_auto_agents_multi_provider():
    """Example using AutoAgents with multi-provider support"""
    print("\n=== Example 3: AutoAgents with Multi-Provider Support ===\n")
    
    from praisonaiagents.agents import AutoAgents
    
    # Create AutoAgents that will automatically assign appropriate models
    auto_agents = AutoAgents(
        instructions="Create a market research report on electric vehicles. Include data analysis, competitor analysis, and future projections.",
        max_agents=3,
        llm="gpt-4o-mini",  # Default model for agent generation
        verbose=True
    )
    
    # After agents are created, upgrade them to multi-model agents
    multi_model_agents = []
    for agent in auto_agents.agents:
        # Convert regular agents to multi-model agents
        multi_agent = MultiModelAgent(
            name=agent.name,
            role=agent.role,
            goal=agent.goal,
            backstory=agent.backstory,
            tools=agent.tools,
            models=["gpt-4o-mini", "gemini/gemini-1.5-flash", "claude-3-haiku-20240307", "gpt-4o"],
            routing_strategy="auto",
            verbose=True
        )
        multi_model_agents.append(multi_agent)
    
    # Update the agents in the AutoAgents instance
    auto_agents.agents = multi_model_agents
    
    # Run the auto-generated workflow
    results = auto_agents.start()
    
    # Show model usage across all agents
    print("\n=== Multi-Provider Usage Summary ===")
    total_calls = 0
    for agent in multi_model_agents:
        report = agent.get_usage_report()
        print(f"\nAgent: {agent.name}")
        for model, stats in report['model_usage'].items():
            if stats['calls'] > 0:
                print(f"  - {model}: {stats['calls']} calls")
                total_calls += stats['calls']
    
    print(f"\nTotal API calls: {total_calls}")


# Example 4: Custom Routing Logic
def example_custom_routing():
    """Example with custom routing logic based on specific requirements"""
    print("\n=== Example 4: Custom Routing Logic ===\n")
    
    # Create custom model profiles for specific use cases
    custom_models = [
        ModelProfile(
            name="gpt-4o",
            provider="openai",
            complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.VERY_COMPLEX),
            cost_per_1k_tokens=0.0075,
            strengths=["code-generation", "debugging"],
            capabilities=["text", "function-calling"],
            context_window=128000
        ),
        ModelProfile(
            name="deepseek-chat",
            provider="deepseek",
            complexity_range=(TaskComplexity.MODERATE, TaskComplexity.VERY_COMPLEX),
            cost_per_1k_tokens=0.001,
            strengths=["mathematics", "algorithms"],
            capabilities=["text", "function-calling"],
            context_window=128000
        )
    ]
    
    # Create router with custom models
    custom_router = ModelRouter(models=custom_models)
    
    # Tool for web search (example)
    def search_web(query: str) -> str:
        """Search the web for information"""
        return f"Search results for: {query}"
    
    # Create specialized agent
    coder = MultiModelAgent(
        name="Adaptive Coder",
        role="Software Developer",
        goal="Write and debug code using the best model for each task",
        backstory="I'm an expert coder who knows when to use different AI models",
        model_router=custom_router,
        routing_strategy="auto",
        tools=[search_web],
        verbose=True
    )
    
    # Create coding tasks
    tasks = [
        Task(
            name="fix_bug",
            description="Fix this Python bug: 'list' object has no attribute 'appendx'",
            expected_output="Corrected code with explanation",
            agent=coder
        ),
        Task(
            name="implement_algorithm",
            description="Implement Dijkstra's shortest path algorithm in Python",
            expected_output="Complete implementation with comments",
            agent=coder,
            tools=[search_web]
        )
    ]
    
    # Run tasks
    agents = PraisonAIAgents(
        agents=[coder],
        tasks=tasks,
        process="sequential",
        verbose=True
    )
    
    results = agents.start()
    
    print("\n=== Custom Routing Results ===")
    print(coder.get_usage_report())


# Run examples
if __name__ == "__main__":
    # Make sure to set your API keys
    # os.environ["OPENAI_API_KEY"] = "your-openai-key"
    # os.environ["ANTHROPIC_API_KEY"] = "your-anthropic-key"  
    # os.environ["GEMINI_API_KEY"] = "your-gemini-key"
    
    # Run examples
    example_auto_routing()
    example_cost_optimized_workflow()
    example_auto_agents_multi_provider()
    example_custom_routing()
    
    print("\n=== All Examples Completed ===")
    print("\nKey Features Demonstrated:")
    print("1. Automatic model selection based on task complexity")
    print("2. Cost-optimized routing for budget-conscious operations")
    print("3. Performance-optimized routing for quality-critical tasks")
    print("4. Multi-provider support with fallback mechanisms")
    print("5. Integration with AutoAgents for automatic workflow generation")
    print("6. Custom routing logic for specialized use cases")
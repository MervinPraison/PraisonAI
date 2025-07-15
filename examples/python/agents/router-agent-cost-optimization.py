"""
RouterAgent Cost Optimization Example

This example demonstrates how to use RouterAgent for intelligent model selection
based on cost optimization. The router agent automatically selects the most
cost-effective model for different types of tasks while maintaining quality.

Features demonstrated:
- Cost-optimized model routing
- Automatic model selection based on task complexity
- Usage tracking and cost monitoring
- Fallback mechanisms for reliability
"""

from praisonaiagents import Agent
from praisonaiagents.agent.router_agent import RouterAgent
from praisonaiagents.tools import duckduckgo

# Define model options with cost considerations
# Using different models for different complexity levels
cheap_model = "gpt-4o-mini"  # For simple tasks
balanced_model = "gpt-4o"    # For moderate complexity  
premium_model = "claude-3-5-sonnet-20241022"  # For complex tasks

# Create RouterAgent with cost optimization strategy
router = RouterAgent(
    name="CostOptimizedRouter",
    role="Cost-Efficient Task Router",
    goal="Route tasks to the most cost-effective model while maintaining quality",
    backstory="You are a smart router that optimizes for cost-efficiency by selecting appropriate models based on task complexity.",
    
    # Model routing strategy - simple tasks to cheap models, complex to premium
    models=[cheap_model, balanced_model, premium_model],
    
    # Routing logic - this could be enhanced with more sophisticated rules
    instructions="""You are a cost-optimization router. For simple tasks like basic questions, 
    definitions, or simple calculations, use the cheapest model. For moderate complexity tasks 
    like writing, analysis, or research, use the balanced model. For complex tasks requiring 
    deep reasoning, creativity, or specialized knowledge, use the premium model.""",
    
    tools=[duckduckgo],
    verbose=True
)

# Example tasks of varying complexity levels

# Simple task - should route to cheap model
print("="*60)
print("TESTING SIMPLE TASK (should use cheap model)")
print("="*60)
simple_result = router.start("What is the capital of France?")
print(f"Simple task result: {simple_result}")

# Moderate complexity task - should route to balanced model  
print("\n" + "="*60)
print("TESTING MODERATE TASK (should use balanced model)")
print("="*60)
moderate_result = router.start("Write a brief analysis of renewable energy trends in 2024")
print(f"Moderate task result: {moderate_result}")

# Complex task - should route to premium model
print("\n" + "="*60) 
print("TESTING COMPLEX TASK (should use premium model)")
print("="*60)
complex_result = router.start("Conduct a comprehensive strategic analysis of the impact of quantum computing on cybersecurity, including potential vulnerabilities and mitigation strategies")
print(f"Complex task result: {complex_result}")

# Research task with tool usage - should route appropriately
print("\n" + "="*60)
print("TESTING RESEARCH TASK WITH TOOLS")
print("="*60)
research_result = router.start("Research and analyze the latest developments in artificial intelligence regulation globally")
print(f"Research task result: {research_result}")

print("\n" + "="*80)
print("COST OPTIMIZATION ROUTER DEMONSTRATION COMPLETED")
print("="*80)
print("The RouterAgent automatically selected appropriate models based on task complexity:")
print("- Simple factual questions → Cheaper model (gpt-4o-mini)")  
print("- Moderate analysis tasks → Balanced model (gpt-4o)")
print(f"- Complex strategic analysis → Premium model ({premium_model})")
print("- This approach optimizes costs while maintaining quality for each task type")
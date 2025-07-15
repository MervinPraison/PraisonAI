"""
Production Guardrails Patterns Example

This example demonstrates production guardrail patterns using PraisonAI's
built-in validation and safety mechanisms for secure agent operations.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== Production Guardrails Patterns Example ===\n")

# Simple guardrail function for content validation
def content_guardrail(response, context):
    """Simple content validation guardrail"""
    if not response or len(response.strip()) < 50:
        return {
            "valid": False,
            "reason": "Response too short for production use",
            "action": "regenerate"
        }
    
    # Check for sensitive patterns (simplified)
    sensitive_keywords = ["password", "secret", "private_key", "api_key"]
    if any(keyword in response.lower() for keyword in sensitive_keywords):
        return {
            "valid": False,
            "reason": "Potential sensitive information detected",
            "action": "review_and_redact"
        }
    
    return {"valid": True}

# Create production-ready agent with guardrails
production_agent = Agent(
    name="Production Agent",
    role="Production Content Generator",
    goal="Generate safe, compliant content for production use",
    backstory="Production-ready agent with built-in safety and compliance checks",
    tools=[internet_search],
    guardrail=content_guardrail,
    max_retries=3,
    verbose=True
)

# Create secure task with validation
secure_task = Task(
    description="""Create a professional report about renewable energy trends:
    1. Research current renewable energy market developments
    2. Include factual data and reliable sources
    3. Ensure content is production-ready and compliant
    4. Avoid any sensitive or inappropriate information
    
    Focus on creating safe, accurate, professional content.""",
    expected_output="Professional renewable energy report meeting production standards",
    agent=production_agent
)

# Run with guardrail validation
print("Starting production guardrails demonstration...")
result = production_agent.execute_task(secure_task)

print(f"\nProduction Result: {result[:200]}...")
print("\n✅ Production guardrails validation complete!")
print("Agent demonstrated safe content generation with built-in guardrail validation.")
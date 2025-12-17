"""
Agentic Routing Workflow Example

Demonstrates decision-based routing where an agent classifier
routes to specialized handler agents based on the request type.
"""

from praisonaiagents import Agent, Workflow
from praisonaiagents.workflows import route

# Create classifier agent
classifier = Agent(
    name="Classifier",
    role="Request Classifier",
    goal="Classify incoming requests",
    instructions="Classify the request. Respond with ONLY 'technical', 'creative', or 'general'."
)

# Create specialized handler agents
tech_agent = Agent(
    name="TechExpert",
    role="Technical Expert",
    goal="Handle technical questions",
    instructions="You are a technical expert. Provide detailed technical answers."
)

creative_agent = Agent(
    name="CreativeWriter",
    role="Creative Writer", 
    goal="Handle creative requests",
    instructions="You are a creative writer. Write engaging, creative content."
)

general_agent = Agent(
    name="GeneralAssistant",
    role="General Assistant",
    goal="Handle general requests",
    instructions="You are a helpful assistant. Provide clear, helpful responses."
)

# Create workflow with routing
workflow = Workflow(
    name="Agentic Router",
    steps=[
        classifier,
        route({
            "technical": [tech_agent],
            "creative": [creative_agent],
            "default": [general_agent]
        })
    ]
)

if __name__ == "__main__":
    print("=== Testing Agentic Routing Workflow ===\n")
    
    # Test 1: Technical question
    print("--- Technical Request ---")
    result = workflow.start("How does machine learning work?", verbose=True)
    print(f"Result: {result['output'][:200]}...\n")
    
    # Test 2: Creative request
    print("--- Creative Request ---")
    result = workflow.start("Write a poem about the ocean", verbose=True)
    print(f"Result: {result['output'][:200]}...")

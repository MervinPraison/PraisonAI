"""
Basic handoff example demonstrating agent-to-agent delegation.

This example shows how agents can hand off tasks to specialized agents.
"""

from praisonaiagents import Agent

# Create specialized agents
billing_agent = Agent(
    name="Billing Agent",
    role="Billing Specialist",
    goal="Handle all billing-related inquiries and tasks",
    backstory="I am an expert in billing systems, payment processing, and invoice management."
)

refund_agent = Agent(
    name="Refund Agent",
    role="Refund Specialist",
    goal="Process refund requests and handle refund-related issues",
    backstory="I specialize in processing refunds, evaluating refund eligibility, and ensuring customer satisfaction."
)

technical_support_agent = Agent(
    name="Technical Support",
    role="Technical Support Specialist",
    goal="Resolve technical issues and provide technical assistance",
    backstory="I am skilled in troubleshooting technical problems and providing solutions."
)

# Create a triage agent with handoffs to specialized agents
triage_agent = Agent(
    name="Triage Agent",
    role="Customer Service Triage",
    goal="Understand customer needs and route them to the appropriate specialist",
    backstory="I analyze customer requests and direct them to the most suitable specialist for efficient resolution.",
    instructions="""Analyze the customer's request and determine which specialist can best help:
    - For billing questions, payment issues, or invoices, transfer to the Billing Agent
    - For refund requests or refund status inquiries, transfer to the Refund Agent  
    - For technical problems or product issues, transfer to Technical Support
    
    Always explain why you're transferring the customer before doing so.""",
    handoffs=[billing_agent, refund_agent, technical_support_agent]
)

# Example usage
if __name__ == "__main__":
    print("=== Customer Service Triage System ===\n")
    
    # Test different types of requests
    test_requests = [
        "I need a refund for my last purchase",
        "Why was I charged twice on my credit card?",
        "The app keeps crashing when I try to login"
    ]
    
    for request in test_requests:
        print(f"\nCustomer: {request}")
        response = triage_agent.chat(request)
        print(f"Response: {response}")
        print("-" * 50)
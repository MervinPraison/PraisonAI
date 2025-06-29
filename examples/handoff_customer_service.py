"""
Complete customer service workflow example with handoffs.

This example demonstrates a realistic customer service scenario with:
- Order status checking
- Refund processing
- Technical support
- FAQ handling
- Escalation management
"""

from praisonaiagents import Agent, handoff, RECOMMENDED_PROMPT_PREFIX
import random


# Mock functions for demonstration
def check_order_status(order_id: str) -> str:
    """Check the status of an order"""
    statuses = ["shipped", "processing", "delivered", "pending"]
    return f"Order {order_id} is {random.choice(statuses)}"


def process_refund(order_id: str, reason: str) -> str:
    """Process a refund request"""
    return f"Refund initiated for order {order_id}. Reason: {reason}. Expected in 3-5 business days."


def get_faq_answer(question: str) -> str:
    """Get answer from FAQ database"""
    faqs = {
        "shipping": "Standard shipping takes 5-7 business days. Express shipping takes 2-3 business days.",
        "returns": "You can return items within 30 days of purchase in original condition.",
        "warranty": "All products come with a 1-year manufacturer warranty.",
        "payment": "We accept credit cards, debit cards, PayPal, and Apple Pay."
    }
    for key, answer in faqs.items():
        if key in question.lower():
            return answer
    return "I'll need to check our documentation for that specific question."


# Create specialized agents with tools
order_agent = Agent(
    name="Order Specialist",
    role="Order Management Specialist",
    goal="Handle all order-related inquiries including tracking, modifications, and status updates",
    backstory="I specialize in order management and have access to the order tracking system.",
    tools=[check_order_status],
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

I can help with:
- Checking order status
- Tracking shipments
- Order modifications
- Delivery issues

For refunds, I'll transfer you to our Refund Specialist.
For technical issues, I'll connect you with Technical Support."""
)

refund_agent = Agent(
    name="Refund Specialist",
    role="Refund and Returns Specialist",
    goal="Process refunds and handle return requests efficiently",
    backstory="I'm authorized to process refunds and handle all return-related matters.",
    tools=[process_refund],
    instructions="""I process refunds and returns. I need the order ID and reason for the refund.
    I ensure all refunds are processed according to our policy."""
)

faq_agent = Agent(
    name="FAQ Assistant",
    role="Knowledge Base Specialist",
    goal="Provide quick answers to frequently asked questions",
    backstory="I have access to our comprehensive FAQ database.",
    tools=[get_faq_answer],
    instructions="I provide answers to common questions about shipping, returns, warranty, and payments."
)

technical_agent = Agent(
    name="Technical Support",
    role="Technical Support Engineer",
    goal="Resolve technical issues with products and services",
    backstory="I'm trained in troubleshooting all our products and technical services.",
    instructions="""I help with:
    - Product setup and configuration
    - Troubleshooting technical issues
    - Software problems
    - Hardware diagnostics"""
)

escalation_agent = Agent(
    name="Senior Manager",
    role="Customer Experience Manager",
    goal="Handle escalated issues and ensure customer satisfaction",
    backstory="I'm a senior manager with authority to make exceptions and handle complex cases.",
    instructions="""I handle:
    - Escalated complaints
    - Special requests requiring manager approval
    - Complex issues that need executive decisions
    - Customer retention situations"""
)

# Create main customer service agent with handoffs
customer_service_agent = Agent(
    name="Customer Service",
    role="Customer Service Representative",
    goal="Provide excellent customer service by understanding needs and routing to the right specialist",
    backstory="I'm your first point of contact and I'll make sure you get the help you need.",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}

Welcome! I'm here to help you today. I can assist with various requests or connect you with the right specialist:

- For order tracking and status → Order Specialist
- For refunds and returns → Refund Specialist  
- For common questions → FAQ Assistant
- For technical problems → Technical Support
- For complaints or special requests → Senior Manager

How can I help you today?""",
    handoffs=[
        order_agent,
        refund_agent,
        faq_agent,
        technical_agent,
        handoff(
            escalation_agent,
            tool_description_override="Escalate to senior management for complex issues or complaints"
        )
    ]
)

# Example interaction
if __name__ == "__main__":
    print("=== Customer Service System ===")
    print("Welcome to our customer service! Type 'quit' to exit.\n")
    
    # Simulated customer interactions
    test_scenarios = [
        "I need to check the status of my order #12345",
        "I want a refund for order #67890, the product was damaged",
        "What's your return policy?",
        "My device won't turn on after the update",
        "I'm very unhappy with the service and want to speak to a manager!",
        "How long does shipping usually take?"
    ]
    
    print("Running automated test scenarios:\n")
    for scenario in test_scenarios:
        print(f"Customer: {scenario}")
        response = customer_service_agent.chat(scenario)
        print(f"Agent: {response}")
        print("-" * 80)
        
    # Interactive mode
    print("\nNow entering interactive mode. You can ask questions directly:")
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() == 'quit':
            break
        response = customer_service_agent.chat(user_input)
        print(f"Agent: {response}")
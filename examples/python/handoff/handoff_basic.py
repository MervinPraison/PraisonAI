"""
Basic handoff example demonstrating agent-to-agent delegation.

This example shows how agents can hand off tasks to specialized agents.
"""

from pydantic import BaseModel
from typing import Optional
from praisonaiagents import Agent
from praisonaiagents.agent.handoff import handoff

# Define typed payload contracts for each handoff
class BillingPayload(BaseModel):
    account_id: Optional[str] = None  # Made optional to work with plain-text requests
    invoice_amount: Optional[float] = None
    issue_type: str = "billing"

class RefundPayload(BaseModel):  # Changed from TypedDict for runtime validation
    transaction_id: Optional[str] = None  # Made optional
    amount: Optional[float] = None  # Made optional
    reason: Optional[str] = None  # Made optional

class TechnicalPayload(BaseModel):
    error_code: Optional[str] = None
    device_info: Optional[str] = None  # Made optional
    user_agent: Optional[str] = None  # Made optional

# Create specialized agents
billing_agent = Agent(
    name="Billing Agent",
    role="Billing Specialist",
    goal="Handle all billing-related inquiries and tasks using structured data",
    backstory="I am an expert in billing systems, payment processing, and invoice management."
)

refund_agent = Agent(
    name="Refund Agent",
    role="Refund Specialist",
    goal="Process refund requests and handle refund-related issues with validated data",
    backstory="I specialize in processing refunds, evaluating refund eligibility, and ensuring customer satisfaction."
)

technical_support_agent = Agent(
    name="Technical Support",
    role="Technical Support Specialist",
    goal="Resolve technical issues and provide technical assistance with structured context",
    backstory="I am skilled in troubleshooting technical problems and providing solutions."
)

# Create a triage agent with typed handoffs
triage_agent = Agent(
    name="Triage Agent",
    role="Customer Service Triage",
    goal="Understand customer needs and route them to the appropriate specialist with a validated payload",
    backstory="I analyze customer requests and direct them to the most suitable specialist for efficient resolution.",
    instructions="""Analyze the customer's request and determine which specialist can best help:
    - For billing questions, payment issues, or invoices, transfer to the Billing Agent
    - For refund requests or refund status inquiries, transfer to the Refund Agent  
    - For technical problems or product issues, transfer to Technical Support
    
    Always explain why you're transferring the customer before doing so.
    When handing off, populate only fields explicitly present in the request. Do not invent missing values.""",
    handoffs=[
        handoff(billing_agent, input_type=BillingPayload),
        handoff(refund_agent, input_type=RefundPayload),
        handoff(technical_support_agent, input_type=TechnicalPayload)
    ]
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

from praisonaiagents import Agent
from praisonaiagents.agent.handoff import handoff, handoff_filters
from pydantic import BaseModel
from typing import Dict, Any
import logging

# Mock data for testing
MOCK_ORDERS = {
    "12345": {
        "id": "12345",
        "status": "shipped",
        "items": ["Widget A", "Widget B"],
        "total": 99.99,
        "tracking_number": "TRK123456789",
        "shipping_address": "123 Main St, City, ST 12345"
    },
    "67890": {
        "id": "67890", 
        "status": "processing",
        "items": ["Gadget X"],
        "total": 149.99,
        "tracking_number": None,
        "shipping_address": "456 Oak Ave, Town, ST 67890"
    }
}

MOCK_SHIPMENTS = {
    "TRK123456789": {
        "tracking_number": "TRK123456789",
        "status": "in_transit",
        "location": "Distribution Center - Chicago",
        "estimated_delivery": "2024-01-15",
        "updates": [
            {"date": "2024-01-10", "status": "picked_up", "location": "Warehouse"},
            {"date": "2024-01-12", "status": "in_transit", "location": "Chicago"}
        ]
    }
}

MOCK_TICKETS = []

# Mock tool functions
def check_order_status(order_id: str) -> Dict[str, Any]:
    """Check the status of an order"""
    if order_id in MOCK_ORDERS:
        return {"success": True, "order": MOCK_ORDERS[order_id]}
    return {"success": False, "error": f"Order {order_id} not found"}

def track_shipment(tracking_number: str) -> Dict[str, Any]:
    """Track a shipment by tracking number"""
    if tracking_number in MOCK_SHIPMENTS:
        return {"success": True, "shipment": MOCK_SHIPMENTS[tracking_number]}
    return {"success": False, "error": f"Tracking number {tracking_number} not found"}

def process_refund(order_id: str, reason: str = "customer_request") -> Dict[str, Any]:
    """Process a refund for an order"""
    if order_id in MOCK_ORDERS:
        order = MOCK_ORDERS[order_id]
        return {
            "success": True,
            "refund_id": f"REF{order_id}",
            "amount": order["total"],
            "status": "processing",
            "estimated_days": 3-5
        }
    return {"success": False, "error": f"Order {order_id} not found"}

def check_refund_policy(item_type: str = "general") -> Dict[str, Any]:
    """Check refund policy for different item types"""
    policies = {
        "general": {"days": 30, "condition": "unopened", "shipping": "customer_pays"},
        "electronics": {"days": 15, "condition": "original_packaging", "shipping": "free"},
        "clothing": {"days": 60, "condition": "tags_attached", "shipping": "customer_pays"}
    }
    return {"success": True, "policy": policies.get(item_type, policies["general"])}

def diagnose_issue(description: str) -> Dict[str, Any]:
    """Diagnose a technical issue"""
    common_solutions = {
        "login": "Clear cookies and cache, try password reset",
        "payment": "Check card details, try different payment method",
        "loading": "Check internet connection, try different browser",
        "mobile": "Update app, restart device, check storage space"
    }
    
    # Simple keyword matching for demo
    for issue_type, solution in common_solutions.items():
        if issue_type in description.lower():
            return {"success": True, "diagnosis": solution, "severity": "low"}
    
    return {"success": True, "diagnosis": "Please provide more details", "severity": "medium"}

def create_ticket(issue_description: str, priority: str = "medium") -> Dict[str, Any]:
    """Create a support ticket"""
    ticket_id = f"TICK{len(MOCK_TICKETS) + 1001}"
    ticket = {
        "id": ticket_id,
        "description": issue_description,
        "priority": priority,
        "status": "open",
        "created_at": "2024-01-13T10:00:00Z"
    }
    MOCK_TICKETS.append(ticket)
    return {"success": True, "ticket": ticket}

def log_escalation(source_agent: str, escalation_data: Dict[str, Any]) -> None:
    """Log escalation for audit purposes"""
    logging.info(f"Escalation from {source_agent}: {escalation_data}")

# Escalation with structured input
class EscalationRequest(BaseModel):
    issue_type: str
    severity: str
    description: str

# Specialist agents
order_agent = Agent(
    name="Order Management",
    instructions="You help with order status and tracking.",
    tools=[check_order_status, track_shipment]
)

refund_agent = Agent(
    name="Refund Specialist", 
    instructions="You process refunds and handle return requests.",
    tools=[process_refund, check_refund_policy]
)

technical_agent = Agent(
    name="Technical Support",
    instructions="You solve technical issues and provide guidance.",
    tools=[diagnose_issue, create_ticket]
)

escalation_agent = Agent(
    name="Senior Manager",
    instructions="You handle escalated issues requiring management attention."
)

# Main triage agent
triage_agent = Agent(
    name="Customer Service",
    instructions="""You are the first point of contact. Route customers to the right specialist:
    - Order issues → Order Management
    - Refunds → Refund Specialist  
    - Technical problems → Technical Support
    - Complex issues → Escalate to management
    """,
    handoffs=[
        order_agent,
        refund_agent,
        technical_agent,
        handoff(
            escalation_agent,
            tool_name_override="escalate_to_management",
            input_type=EscalationRequest,
            on_handoff=lambda src, data: log_escalation(src.name, data)
        )
    ]
)

# Start the service
if __name__ == "__main__":
    print("Customer Service Handoff System Demo")
    print("=" * 40)
    
    # Test different scenarios
    test_queries = [
        "I need a refund for order #12345",
        "What's the status of order #67890?",
        "I'm having trouble logging into my account",
        "This is urgent - I need to speak to a manager about a serious billing issue"
    ]
    
    for query in test_queries:
        print(f"\nCustomer: {query}")
        response = triage_agent.chat(query)
        print(f"Response: {response}")
        print("-" * 40)
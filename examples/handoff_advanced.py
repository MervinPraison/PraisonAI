"""
Advanced handoff example with callbacks, input types, and filters.

This example demonstrates advanced handoff features including:
- Custom handoff callbacks
- Structured input data
- Input filters
- Custom tool names and descriptions
"""

from praisonaiagents import Agent, handoff, handoff_filters, prompt_with_handoff_instructions
from pydantic import BaseModel
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)

# Define structured input for escalation
class EscalationData(BaseModel):
    reason: str
    priority: Optional[str] = "normal"
    customer_sentiment: Optional[str] = None

# Callback function for logging handoffs
def log_handoff(source_agent: Agent):
    """Log when a handoff occurs"""
    logging.info(f"Handoff initiated from {source_agent.name}")

# Callback function with input data
def log_escalation(source_agent: Agent, input_data: EscalationData):
    """Log escalation with structured data"""
    logging.info(f"ESCALATION from {source_agent.name}: {input_data.reason} (Priority: {input_data.priority})")

# Create specialized agents
faq_agent = Agent(
    name="FAQ Agent",
    role="FAQ Specialist",
    goal="Answer frequently asked questions using knowledge base",
    backstory="I have access to comprehensive FAQ documentation and can quickly provide accurate answers."
)

escalation_agent = Agent(
    name="Escalation Agent",
    role="Senior Support Manager",
    goal="Handle escalated issues that require special attention",
    backstory="I handle complex cases that need senior-level intervention and decision-making."
)

# Create support agent with custom handoffs
support_agent = Agent(
    name="Support Agent",
    role="Customer Support Representative",
    goal="Provide first-line support and escalate when necessary",
    backstory="I help customers with their issues and know when to involve specialists.",
    instructions=prompt_with_handoff_instructions(
        """Help customers with their requests. You should:
        1. Try to resolve issues yourself first
        2. Transfer to FAQ Agent for common questions you can't answer
        3. Escalate to senior management for complex or sensitive issues
        
        When escalating, always provide a clear reason and assess the priority.""",
        None  # Agent will be set later
    ),
    handoffs=[
        # Simple handoff with callback
        handoff(
            faq_agent,
            on_handoff=log_handoff,
            input_filter=handoff_filters.remove_all_tools  # Remove tool calls from history
        ),
        # Advanced handoff with structured input
        handoff(
            escalation_agent,
            tool_name_override="escalate_to_manager",
            tool_description_override="Escalate complex or sensitive issues to senior management",
            on_handoff=log_escalation,
            input_type=EscalationData
        )
    ]
)

# Update the instructions with the agent reference
support_agent.instructions = prompt_with_handoff_instructions(
    support_agent.instructions,
    support_agent
)

# Example with custom input filter
def custom_filter(data):
    """Keep only last 3 messages and remove system messages"""
    data = handoff_filters.keep_last_n_messages(3)(data)
    data = handoff_filters.remove_system_messages(data)
    return data

# Agent with custom filtered handoff
filtered_agent = Agent(
    name="Filtered Support",
    role="Support with Privacy",
    goal="Handle support while maintaining privacy",
    backstory="I ensure customer privacy by filtering sensitive conversation history.",
    handoffs=[
        handoff(
            faq_agent,
            tool_description_override="Transfer to FAQ (filtered history)",
            input_filter=custom_filter
        )
    ]
)

# Example usage
if __name__ == "__main__":
    print("=== Advanced Handoff Examples ===\n")
    
    # Test escalation with structured data
    print("Test 1: Escalation with structured input")
    response = support_agent.chat(
        "I've been waiting for my refund for 3 weeks and I'm very frustrated! "
        "I need this resolved immediately or I'll take legal action!"
    )
    print(f"Response: {response}\n")
    
    # Test FAQ handoff
    print("\nTest 2: FAQ handoff with filtering")
    response = support_agent.chat(
        "How do I reset my password? I can't find the option in settings."
    )
    print(f"Response: {response}\n")
    
    # Test filtered handoff
    print("\nTest 3: Filtered handoff")
    # Add some conversation history
    filtered_agent.chat("My account number is 12345")
    filtered_agent.chat("I have a sensitive issue")
    response = filtered_agent.chat("I need help with FAQ about privacy policy")
    print(f"Response: {response}\n")
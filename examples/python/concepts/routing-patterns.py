"""
Routing Patterns Example

This example demonstrates various routing patterns in PraisonAI including:
- Conditional routing based on task outcomes
- Loop patterns for iterative processing
- Decision trees for complex workflows
- Dynamic task selection
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from typing import Dict, Any
import random

# Agents for different routing scenarios
analyzer_agent = Agent(
    name="Analyzer",
    role="Data analyst",
    goal="Analyze input and determine appropriate routing",
    backstory="You are an expert at analyzing data and making routing decisions.",
    instructions="Analyze the input and determine the best path forward."
)

processor_agent = Agent(
    name="Processor",
    role="Data processor",
    goal="Process data according to specific requirements",
    backstory="You specialize in processing different types of data.",
    instructions="Process the data based on the routing decision."
)

validator_agent = Agent(
    name="Validator",
    role="Quality validator",
    goal="Validate processed data and determine if reprocessing is needed",
    backstory="You ensure data quality and correctness.",
    instructions="Validate the data and decide if it meets quality standards."
)

# Example 1: Basic Conditional Routing
def conditional_routing_example():
    """Demonstrates routing based on analysis results."""
    
    # Initial analysis task
    analysis_task = Task(
        name="analyze_data",
        description="Analyze the customer data and categorize as: high_value, medium_value, or low_value",
        expected_output="Customer category: high_value, medium_value, or low_value",
        agent=analyzer_agent,
        task_type="decision",
        condition={
            "high_value": ["premium_processing"],
            "medium_value": ["standard_processing"],
            "low_value": ["basic_processing"]
        }
    )
    
    # Different processing paths
    premium_task = Task(
        name="premium_processing",
        description="Apply premium processing with personalized features",
        expected_output="Premium processed data with personalization",
        agent=processor_agent
    )
    
    standard_task = Task(
        name="standard_processing",
        description="Apply standard processing",
        expected_output="Standard processed data",
        agent=processor_agent
    )
    
    basic_task = Task(
        name="basic_processing",
        description="Apply basic processing",
        expected_output="Basic processed data",
        agent=processor_agent
    )
    
    workflow = PraisonAIAgents(
        agents=[analyzer_agent, processor_agent],
        tasks=[analysis_task, premium_task, standard_task, basic_task],
        process="workflow",
        verbose=True
    )
    
    return workflow.start()

# Example 2: Loop Pattern with Exit Condition
def loop_pattern_example():
    """Demonstrates iterative processing with loop control."""
    
    # Process items in a loop until quality threshold is met
    process_task = Task(
        name="process_batch",
        description="Process the current batch of items and check quality",
        expected_output="Processed batch with quality score",
        agent=processor_agent,
        task_type="loop",
        condition={
            "quality below threshold": ["process_batch"],  # Loop back
            "quality meets threshold": ["finalize_batch"]  # Exit loop
        }
    )
    
    finalize_task = Task(
        name="finalize_batch",
        description="Finalize the batch processing and generate report",
        expected_output="Final batch report",
        agent=validator_agent
    )
    
    workflow = PraisonAIAgents(
        agents=[processor_agent, validator_agent],
        tasks=[process_task, finalize_task],
        process="workflow",
        verbose=True
    )
    
    return workflow.start()

# Example 3: Complex Decision Tree
def decision_tree_example():
    """Demonstrates multi-level decision tree routing."""
    
    # Level 1: Initial categorization
    categorize_task = Task(
        name="categorize_request",
        description="Categorize the request as: technical, business, or general",
        expected_output="Request category",
        agent=analyzer_agent,
        task_type="decision",
        condition={
            "technical": ["technical_analysis"],
            "business": ["business_analysis"],
            "general": ["general_handling"]
        }
    )
    
    # Level 2: Technical branch
    technical_task = Task(
        name="technical_analysis",
        description="Analyze technical complexity: simple, moderate, or complex",
        expected_output="Technical complexity level",
        agent=analyzer_agent,
        task_type="decision",
        condition={
            "simple": ["quick_fix"],
            "moderate": ["standard_solution"],
            "complex": ["expert_consultation"]
        }
    )
    
    # Level 2: Business branch
    business_task = Task(
        name="business_analysis",
        description="Analyze business impact: high, medium, or low",
        expected_output="Business impact level",
        agent=analyzer_agent,
        task_type="decision",
        condition={
            "high": ["executive_review"],
            "medium": ["manager_approval"],
            "low": ["auto_approve"]
        }
    )
    
    # Terminal tasks
    terminal_tasks = [
        Task(name="general_handling", description="Handle general request", 
             expected_output="General response", agent=processor_agent),
        Task(name="quick_fix", description="Apply quick fix", 
             expected_output="Quick fix applied", agent=processor_agent),
        Task(name="standard_solution", description="Apply standard solution", 
             expected_output="Standard solution applied", agent=processor_agent),
        Task(name="expert_consultation", description="Consult with expert", 
             expected_output="Expert consultation result", agent=processor_agent),
        Task(name="executive_review", description="Send for executive review", 
             expected_output="Executive decision", agent=processor_agent),
        Task(name="manager_approval", description="Send for manager approval", 
             expected_output="Manager decision", agent=processor_agent),
        Task(name="auto_approve", description="Auto-approve request", 
             expected_output="Auto-approved", agent=processor_agent)
    ]
    
    all_tasks = [categorize_task, technical_task, business_task] + terminal_tasks
    
    workflow = PraisonAIAgents(
        agents=[analyzer_agent, processor_agent],
        tasks=all_tasks,
        process="workflow",
        verbose=True
    )
    
    return workflow.start()

# Example 4: Dynamic Router Agent
dynamic_router = Agent(
    name="DynamicRouter",
    role="Intelligent routing specialist",
    goal="Dynamically route tasks based on complex conditions",
    backstory="You are an AI routing expert who can analyze multiple factors to determine optimal task paths.",
    instructions="""Analyze the input and determine routing based on:
1. Content type and complexity
2. Priority and urgency
3. Available resources
4. Historical performance
5. Current system load

Provide clear routing decisions with reasoning.""",
    self_reflect=True
)

def dynamic_routing_example():
    """Demonstrates dynamic routing based on multiple factors."""
    
    # Custom routing function
    def determine_route(task_output) -> str:
        """Custom function to determine routing based on output."""
        # Simulate complex routing logic
        factors = task_output.raw.lower()
        
        if "urgent" in factors and "complex" in factors:
            return "escalate"
        elif "simple" in factors:
            return "automate"
        elif "review" in factors:
            return "manual_review"
        else:
            return "standard"
    
    # Dynamic routing task
    route_task = Task(
        name="dynamic_route",
        description="""Analyze this request and determine routing:
        - Request type: Customer complaint
        - Complexity: Moderate
        - Priority: Urgent
        - Customer tier: Premium""",
        expected_output="Routing decision with reasoning",
        agent=dynamic_router,
        task_type="decision",
        condition=determine_route  # Use custom function for routing
    )
    
    # Possible routes
    escalate_task = Task(
        name="escalate",
        description="Escalate to senior team",
        expected_output="Escalation complete",
        agent=processor_agent
    )
    
    automate_task = Task(
        name="automate",
        description="Process automatically",
        expected_output="Automated processing complete",
        agent=processor_agent
    )
    
    review_task = Task(
        name="manual_review",
        description="Send for manual review",
        expected_output="Manual review complete",
        agent=processor_agent
    )
    
    standard_task = Task(
        name="standard",
        description="Standard processing",
        expected_output="Standard processing complete",
        agent=processor_agent
    )
    
    workflow = PraisonAIAgents(
        agents=[dynamic_router, processor_agent],
        tasks=[route_task, escalate_task, automate_task, review_task, standard_task],
        process="workflow",
        verbose=True
    )
    
    return workflow.start()

if __name__ == "__main__":
    print("=== Conditional Routing Example ===")
    result = conditional_routing_example()
    print(f"Result: {result}\n")
    
    print("=== Loop Pattern Example ===")
    result = loop_pattern_example()
    print(f"Result: {result}\n")
    
    print("=== Decision Tree Example ===")
    result = decision_tree_example()
    print(f"Result: {result}\n")
    
    print("=== Dynamic Routing Example ===")
    result = dynamic_routing_example()
    print(f"Result: {result}")
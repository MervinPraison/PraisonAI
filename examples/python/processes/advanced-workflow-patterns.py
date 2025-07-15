"""
Advanced Workflow Patterns Example

This example demonstrates sophisticated workflow orchestration patterns including
conditional routing, decision trees, loops, and complex multi-agent coordination.

Features demonstrated:
- Advanced workflow patterns with conditional routing
- Decision trees and dynamic task routing
- Loop-based processing with exit conditions
- Complex agent coordination and handoffs
- State-based workflow management
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo
import random

# Create specialized agents for complex workflow
intake_agent = Agent(
    name="IntakeAgent",
    role="Request Intake Specialist",
    goal="Classify and route incoming requests to appropriate specialists",
    backstory="You are an intake specialist who categorizes requests and determines the appropriate workflow path.",
    instructions="Analyze incoming requests and categorize them by type (research, analysis, technical, creative) and complexity (low, medium, high)."
)

research_agent = Agent(
    name="ResearchAgent", 
    role="Research Specialist",
    goal="Conduct comprehensive research on assigned topics",
    backstory="You are a research specialist who gathers and analyzes information from various sources.",
    tools=[duckduckgo],
    instructions="Conduct thorough research using available tools. Provide detailed findings with sources."
)

analysis_agent = Agent(
    name="AnalysisAgent",
    role="Data Analysis Expert",
    goal="Analyze data and provide insights",
    backstory="You are a data analysis expert who identifies patterns, trends, and actionable insights.",
    instructions="Analyze provided data to identify key insights, trends, and recommendations."
)

technical_agent = Agent(
    name="TechnicalAgent",
    role="Technical Solutions Specialist", 
    goal="Provide technical solutions and implementations",
    backstory="You are a technical specialist who designs and implements technical solutions.",
    instructions="Provide detailed technical solutions with implementation guidance and best practices."
)

creative_agent = Agent(
    name="CreativeAgent",
    role="Creative Content Specialist",
    goal="Create engaging and creative content",
    backstory="You are a creative specialist who develops engaging content and innovative solutions.",
    instructions="Create original, engaging content that meets the specified requirements."
)

review_agent = Agent(
    name="ReviewAgent",
    role="Quality Review Specialist",
    goal="Review work quality and provide feedback",
    backstory="You are a quality reviewer who ensures all work meets high standards.",
    instructions="Review completed work for quality, accuracy, and completeness. Provide specific feedback."
)

coordinator_agent = Agent(
    name="CoordinatorAgent",
    role="Workflow Coordinator",
    goal="Coordinate complex workflows and manage handoffs",
    backstory="You are a workflow coordinator who manages complex multi-agent processes.",
    instructions="Coordinate workflow execution, manage handoffs between agents, and ensure successful completion."
)

# Define workflow state management
workflow_state = {
    "request_count": 0,
    "completed_tasks": [],
    "active_workflows": [],
    "quality_threshold": 0.8
}

# Simulate incoming requests of different types
sample_requests = [
    {
        "id": "REQ001",
        "type": "market_research", 
        "description": "Research emerging trends in sustainable technology",
        "complexity": "medium",
        "priority": "high"
    },
    {
        "id": "REQ002",
        "type": "technical_solution",
        "description": "Design architecture for distributed AI system",
        "complexity": "high", 
        "priority": "medium"
    },
    {
        "id": "REQ003",
        "type": "creative_content",
        "description": "Create marketing campaign for new product launch",
        "complexity": "medium",
        "priority": "high"
    },
    {
        "id": "REQ004",
        "type": "data_analysis",
        "description": "Analyze customer behavior patterns from sales data",
        "complexity": "low",
        "priority": "low"
    }
]

# Process each request through the advanced workflow
for request in sample_requests:
    print(f"\n{'='*80}")
    print(f"PROCESSING REQUEST {request['id']}: {request['type'].upper()}")
    print(f"Description: {request['description']}")
    print(f"Complexity: {request['complexity']} | Priority: {request['priority']}")
    print(f"{'='*80}")
    
    workflow_state["request_count"] += 1
    workflow_state["active_workflows"].append(request["id"])
    
    # Step 1: Intake and Classification
    intake_task = Task(
        name=f"intake_{request['id']}",
        description=f"Classify and route this request: {request['description']} (Type: {request['type']}, Complexity: {request['complexity']})",
        expected_output="Request classification with recommended workflow path and agent assignment",
        agent=intake_agent
    )
    
    # Step 2: Route to appropriate specialist based on type
    if request['type'] == 'market_research':
        specialist_agent = research_agent
        specialist_task_desc = f"Conduct comprehensive market research on: {request['description']}"
    elif request['type'] == 'technical_solution':
        specialist_agent = technical_agent
        specialist_task_desc = f"Design technical solution for: {request['description']}"
    elif request['type'] == 'creative_content':
        specialist_agent = creative_agent
        specialist_task_desc = f"Create creative content for: {request['description']}"
    elif request['type'] == 'data_analysis':
        specialist_agent = analysis_agent
        specialist_task_desc = f"Analyze data for: {request['description']}"
    else:
        specialist_agent = research_agent  # Default fallback
        specialist_task_desc = f"Process request: {request['description']}"
    
    specialist_task = Task(
        name=f"specialist_{request['id']}",
        description=specialist_task_desc,
        expected_output="Comprehensive response addressing the request requirements",
        agent=specialist_agent,
        context=[intake_task]
    )
    
    # Step 3: Quality Review with conditional routing
    review_task = Task(
        name=f"review_{request['id']}",
        description=f"Review the quality of work completed for request {request['id']}. Assess if it meets standards or needs revision.",
        expected_output="Quality assessment with pass/fail decision and specific feedback",
        agent=review_agent,
        context=[intake_task, specialist_task],
        
        # Conditional routing based on quality
        task_type="decision",
        condition={
            "approved": [f"finalization_{request['id']}"],  # If approved, finalize
            "needs_revision": [f"revision_{request['id']}"],  # If needs work, revise
            "needs_escalation": [f"escalation_{request['id']}"]  # If complex, escalate
        }
    )
    
    # Step 4a: Revision Task (conditional)
    revision_task = Task(
        name=f"revision_{request['id']}",
        description=f"Revise the work based on quality review feedback for request {request['id']}",
        expected_output="Revised work addressing quality review feedback",
        agent=specialist_agent,
        context=[specialist_task, review_task]
    )
    
    # Step 4b: Escalation Task (conditional)
    escalation_task = Task(
        name=f"escalation_{request['id']}",
        description=f"Handle escalated request {request['id']} requiring additional expertise or coordination",
        expected_output="Escalated response with enhanced solution approach",
        agent=coordinator_agent,
        context=[intake_task, specialist_task, review_task]
    )
    
    # Step 5: Finalization and Coordination
    finalization_task = Task(
        name=f"finalization_{request['id']}",
        description=f"Finalize and package the completed work for request {request['id']}",
        expected_output="Final deliverable package with summary and next steps",
        agent=coordinator_agent,
        context=[intake_task, specialist_task, review_task]
    )
    
    # Execute the workflow with conditional routing
    workflow_agents = PraisonAIAgents(
        agents=[
            intake_agent, specialist_agent, review_agent, 
            coordinator_agent
        ],
        tasks=[
            intake_task, specialist_task, review_task,
            revision_task,      # Conditional
            escalation_task,    # Conditional  
            finalization_task
        ],
        process="workflow",  # Use workflow process for conditional execution
        verbose=True
    )
    
    print(f"Executing advanced workflow for {request['id']}...")
    result = workflow_agents.start()
    
    # Update workflow state
    workflow_state["completed_tasks"].append(request["id"])
    workflow_state["active_workflows"].remove(request["id"])
    
    # Simulate quality scoring
    quality_score = random.uniform(0.75, 0.95)
    
    print(f"✅ Request {request['id']} completed with quality score: {quality_score:.2f}")
    print(f"📋 Result preview: {str(result)[:150]}...")
    
    # Loop control - if we have processed enough requests, demonstrate loop exit
    if workflow_state["request_count"] >= 2:
        print(f"\n🔄 WORKFLOW LOOP CONTROL: Processed {workflow_state['request_count']} requests")
        print("Checking if we should continue or exit based on workflow state...")
        
        # Example loop control logic
        if workflow_state["request_count"] >= 4:
            print("📊 Batch processing complete. Exiting workflow loop.")
            break
        else:
            print("📈 Continuing with next request in the batch...")

# Advanced Workflow Analytics and Summary
print(f"\n{'='*80}")
print("ADVANCED WORKFLOW PATTERNS SUMMARY")
print(f"{'='*80}")

print(f"📊 Workflow Statistics:")
print(f"- Total Requests Processed: {workflow_state['request_count']}")
print(f"- Completed Tasks: {len(workflow_state['completed_tasks'])}")
print(f"- Active Workflows: {len(workflow_state['active_workflows'])}")

print(f"\n🔀 Workflow Patterns Demonstrated:")
print("- Dynamic request classification and routing")
print("- Conditional task execution based on quality review")
print("- Multi-path workflows (approval/revision/escalation)")
print("- State-based workflow management")
print("- Loop control with exit conditions")
print("- Agent specialization and handoffs")

print(f"\n⚙️ Advanced Features Used:")
print("- Workflow process type with conditional routing")
print("- Decision tasks with multiple outcome paths")
print("- Context passing between related tasks")
print("- State management across workflow iterations")
print("- Quality-based routing decisions")
print("- Scalable agent coordination patterns")

print(f"\n🎯 Production Benefits:")
print("- Handles complex, multi-step business processes")
print("- Automatically routes work to appropriate specialists")
print("- Implements quality gates and revision loops")
print("- Scales to handle multiple concurrent workflows")
print("- Provides visibility into workflow state and progress")
print("- Enables sophisticated business process automation")

print(f"\n{'='*80}")
print("ADVANCED WORKFLOW DEMONSTRATION COMPLETED")
print(f"{'='*80}")
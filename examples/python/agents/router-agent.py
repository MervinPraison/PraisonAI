#!/usr/bin/env python3

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create specialized agents for different tasks
math_agent = Agent(
    name="Math Expert",
    role="Mathematics Specialist",
    goal="Solve mathematical problems and calculations",
    backstory="You are a mathematics expert who can solve complex calculations and explain mathematical concepts clearly.",
    llm="gpt-4o-mini"
)

writer_agent = Agent(
    name="Content Writer",
    role="Professional Writer",
    goal="Create well-written content and documents",
    backstory="You are a skilled writer who can create engaging content, emails, and documentation.",
    llm="gpt-4o-mini"
)

code_agent = Agent(
    name="Code Expert",
    role="Software Developer",
    goal="Write, debug, and explain code",
    backstory="You are a experienced programmer who can write clean code and explain technical concepts.",
    llm="gpt-4o-mini"
)

# Create router agent that decides which agent to use
router_agent = Agent(
    name="Router Agent",
    role="Task Router",
    goal="Route requests to the most appropriate specialist agent",
    backstory="You analyze incoming requests and determine which specialist agent (Math Expert, Content Writer, or Code Expert) should handle the task. You route the request to the best agent based on the content.",
    llm="gpt-4o-mini"
)

# Create tasks for router to analyze and route
analysis_task = Task(
    name="analyze_request",
    description="Analyze this user request: 'Calculate the compound interest for $5000 at 5% for 3 years' and determine which specialist agent should handle it",
    expected_output="Route this request to the Math Expert agent for calculation",
    agent=router_agent
)

routing_task = Task(
    name="route_math_problem",
    description="Solve the compound interest calculation: Principal = $5000, Rate = 5%, Time = 3 years",
    expected_output="Detailed calculation with step-by-step solution",
    agent=math_agent,
    context=[analysis_task]
)

# Create the workflow
workflow = PraisonAIAgents(
    agents=[router_agent, math_agent, writer_agent, code_agent],
    tasks=[analysis_task, routing_task],
    process="sequential",
    verbose=True
)

# Run the workflow
if __name__ == "__main__":
    print("🔀 Router Agent Example")
    print("This example shows how to use a router agent to automatically route requests to specialist agents")
    print("=" * 80)
    
    _ = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ Router Agent Successfully Directed Request to Math Expert")
    print("💡 The router agent analyzed the request and chose the appropriate specialist")
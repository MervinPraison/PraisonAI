"""Simple Planning Mode Example: Plan first, then execute todo items."""

from praisonaiagents import Agent
from praisonaiagents.planning import PlanningAgent, TodoList

# Step 1: Create agents
researcher = Agent(name="Researcher", role="Research Analyst", verbose=True)
writer = Agent(name="Writer", role="Content Writer", verbose=True)

# Step 2: Create a plan using PlanningAgent
planner = PlanningAgent(llm="gpt-4o-mini", verbose=1)
plan = planner.create_plan_sync(
    request="Write a short article about the top 3 benefits of meditation",
    agents=[researcher, writer],
    context="Keep it concise"
)

# Step 3: Create todo list from the plan
todo = TodoList.from_plan(plan)

# Step 4: Execute each todo item one by one
for item in todo.items:
    todo.start(item.id)
    
    # Pick the right agent based on the item's assigned agent
    if item.agent == "Researcher":
        agent = researcher
    else:
        agent = writer
    
    # Execute the task
    result = agent.chat(item.description)
    
    todo.complete(item.id)

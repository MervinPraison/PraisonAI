"""
Complete Planning Mode Demo: Plan First, Then Execute Todo Items One by One.

This demonstrates the full workflow:
1. Create a plan with the PlanningAgent
2. Generate todo list from the plan
3. Execute each todo item sequentially with the appropriate agent
4. Update progress as items are completed

Run with: python test_planning_execution.py
"""

from praisonaiagents import Agent, Task
from praisonaiagents.planning import PlanningAgent, TodoList


def print_separator(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_progress(todo_list: TodoList):
    """Print current progress."""
    completed = len(todo_list.completed)
    total = len(todo_list.items)
    progress = todo_list.progress * 100
    bar_length = 30
    filled = int(bar_length * todo_list.progress)
    bar = "█" * filled + "░" * (bar_length - filled)
    print(f"\n📊 Progress: [{bar}] {progress:.0f}% ({completed}/{total} completed)\n")


def main():
    print_separator("🎯 PLANNING MODE: PLAN FIRST, EXECUTE TODO ITEMS")
    
    # ==========================================================================
    # STEP 1: Create Agents
    # ==========================================================================
    print("📦 Creating agents...")
    
    researcher = Agent(
        name="Researcher",
        role="Research Analyst",
        goal="Research topics thoroughly and provide accurate information",
        backstory="Expert researcher with access to vast knowledge bases",
        verbose=True
    )
    
    writer = Agent(
        name="Writer",
        role="Content Writer", 
        goal="Write clear, engaging, and well-structured content",
        backstory="Professional writer skilled in creating compelling narratives",
        verbose=True
    )
    
    print("✅ Agents created: Researcher, Writer\n")
    
    # ==========================================================================
    # STEP 2: Create Plan using PlanningAgent
    # ==========================================================================
    print_separator("📋 PHASE 1: CREATING PLAN")
    
    planner = PlanningAgent(
        llm="gpt-4o-mini",
        read_only=True,
        verbose=1
    )
    
    request = "Write a short article about the top 3 benefits of meditation for mental health"
    
    print(f"📝 Request: {request}\n")
    print("🤔 Planning agent is analyzing and creating a plan...\n")
    
    plan = planner.create_plan_sync(
        request=request,
        agents=[researcher, writer],
        context="Keep it concise - each section should be 2-3 sentences max"
    )
    
    print("\n✅ Plan created successfully!")
    print(f"   Plan Name: {plan.name}")
    print(f"   Total Steps: {len(plan.steps)}")
    
    # ==========================================================================
    # STEP 3: Display the Plan
    # ==========================================================================
    print_separator("📄 GENERATED PLAN")
    print(plan.to_markdown())
    
    # ==========================================================================
    # STEP 4: Create Todo List from Plan
    # ==========================================================================
    print_separator("📝 PHASE 2: TODO LIST CREATED")
    
    todo_list = TodoList.from_plan(plan)
    print(todo_list.to_markdown())
    print_progress(todo_list)
    
    # ==========================================================================
    # STEP 5: Execute Each Todo Item One by One
    # ==========================================================================
    print_separator("🚀 PHASE 3: EXECUTING TODO ITEMS")
    
    # Map agent names to agent instances
    agent_map = {
        "Researcher": researcher,
        "Writer": writer
    }
    
    results = {}
    
    for i, item in enumerate(todo_list.items):
        print(f"\n{'─' * 70}")
        print(f"📌 TODO ITEM {i + 1}/{len(todo_list.items)}")
        print(f"{'─' * 70}")
        print(f"   Description: {item.description}")
        print(f"   Agent: {item.agent or 'Auto-assign'}")
        print(f"   Status: {item.status}")
        
        if item.dependencies:
            print(f"   Dependencies: {', '.join(item.dependencies)}")
        
        # Mark as in progress
        todo_list.start(item.id)
        print(f"\n   ⏳ Starting execution...")
        
        # Get the appropriate agent
        agent_name = item.agent or "Researcher"
        agent = agent_map.get(agent_name, researcher)
        
        # Build context from previous results
        context = ""
        for dep_id in item.dependencies:
            if dep_id in results:
                context += f"\nPrevious result ({dep_id}):\n{results[dep_id]}\n"
        
        # Create task description
        task_description = item.description
        if context:
            task_description += f"\n\nContext from previous steps:{context}"
        
        # Execute with the agent
        try:
            result = agent.chat(task_description)
            results[item.id] = result
            
            # Mark as completed
            todo_list.complete(item.id)
            
            print(f"\n   ✅ Completed!")
            print(f"\n   📄 Result Preview:")
            print("   " + "-" * 50)
            preview = str(result)[:500] + "..." if len(str(result)) > 500 else str(result)
            for line in preview.split('\n'):
                print(f"   {line}")
            
        except Exception as e:
            print(f"\n   ❌ Error: {e}")
            results[item.id] = f"Error: {e}"
        
        print_progress(todo_list)
    
    # ==========================================================================
    # STEP 6: Final Summary
    # ==========================================================================
    print_separator("🎉 EXECUTION COMPLETE")
    
    print("📋 Final Todo List Status:")
    print(todo_list.to_markdown())
    
    print("\n📊 Final Results Summary:")
    print("-" * 50)
    for item in todo_list.items:
        status_icon = "✅" if item.status == "completed" else "❌"
        print(f"{status_icon} {item.description[:60]}...")
    
    print(f"\n🏆 All {len(todo_list.completed)} tasks completed successfully!")


if __name__ == "__main__":
    main()

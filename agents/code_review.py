from praisonaiagents import Agent, Task, PraisonAIAgents
import time
from typing import List, Dict

def analyze_code_changes():
    """Simulates code analysis"""
    issues = [
        {"type": "style", "severity": "low", "file": "main.py"},
        {"type": "security", "severity": "high", "file": "auth.py"},
        {"type": "performance", "severity": "medium", "file": "data.py"}
    ]
    return issues[int(time.time()) % 3]

def suggest_fixes(issue: Dict):
    """Simulates fix suggestions"""
    fixes = {
        "style": "Apply PEP 8 formatting",
        "security": "Implement input validation",
        "performance": "Use list comprehension"
    }
    return fixes.get(issue["type"], "Review manually")

def apply_automated_fix(fix: str):
    """Simulates applying automated fixes"""
    success = int(time.time()) % 2 == 0
    return "fixed" if success else "manual_review"

# Create specialized agents
analyzer = Agent(
    name="Code Analyzer",
    role="Code analysis",
    goal="Analyze code changes and identify issues",
    instructions="Review code changes and report issues",
    tools=[analyze_code_changes]
)

fix_suggester = Agent(
    name="Fix Suggester",
    role="Solution provider",
    goal="Suggest fixes for identified issues",
    instructions="Provide appropriate fix suggestions",
    tools=[suggest_fixes]
)

fix_applier = Agent(
    name="Fix Applier",
    role="Fix implementation",
    goal="Apply suggested fixes automatically when possible",
    instructions="Implement suggested fixes and report results",
    tools=[apply_automated_fix]
)

# Create workflow tasks
analysis_task = Task(
    name="analyze_code",
    description="Analyze code changes for issues",
    expected_output="Identified code issues",
    agent=analyzer,
    is_start=True,
    next_tasks=["suggest_fixes"]
)

suggestion_task = Task(
    name="suggest_fixes",
    description="Suggest fixes for identified issues",
    expected_output="Fix suggestions",
    agent=fix_suggester,
    next_tasks=["apply_fixes"]
)

fix_task = Task(
    name="apply_fixes",
    description="Apply suggested fixes",
    expected_output="Fix application status",
    agent=fix_applier,
    task_type="decision",
    condition={
        "fixed": "",
        "manual_review": ["suggest_fixes"]  # Loop back for manual review
    }
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[analyzer, fix_suggester, fix_applier],
    tasks=[analysis_task, suggestion_task, fix_task],
    process="workflow",
    verbose=True
)

def main():
    print("\nStarting Code Review Workflow...")
    print("=" * 50)
    
    # Run workflow
    results = workflow.start()
    
    # Print results
    print("\nCode Review Results:")
    print("=" * 50)
    for task_id, result in results["task_results"].items():
        if result:
            print(f"\nTask: {task_id}")
            print(f"Result: {result.raw}")
            print("-" * 50)

if __name__ == "__main__":
    main()
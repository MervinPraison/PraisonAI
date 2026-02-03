"""
Multi-Step Task Loop Example

Demonstrates evaluating sequential task steps where each step can
reference output from previous steps.

Pattern:
1. Research → Evaluate → Improve
2. Analyze (using research) → Evaluate → Improve  
3. Report (using analysis) → Evaluate → Improve

Usage:
    pip install praisonaiagents
    export OPENAI_API_KEY=your-key
    python multi_step_task_loop.py
"""
from praisonaiagents import Agent
from praisonaiagents.eval import EvaluationLoop


def on_iteration(result):
    """Show iteration progress."""
    status = "✅" if result.score >= 8.0 else "⚠️" if result.score >= 6.0 else "❌"
    print(f"  {status} Iteration {result.iteration}: {result.score:.1f}/10")


def run_step(step_name: str, agent: Agent, task: str, criteria: str, context: str = "") -> dict:
    """Run a single step through an evaluation loop."""
    print(f"\n{'─'*60}")
    print(f"STEP: {step_name}")
    print(f"{'─'*60}")
    
    # Include context from previous step if provided
    full_task = task
    if context:
        full_task = f"{task}\n\nContext from previous step:\n{context[:1000]}"
    
    loop = EvaluationLoop(
        agent=agent,
        criteria=criteria,
        threshold=8.0,
        max_iterations=3,
        on_iteration=on_iteration,
        verbose=False,
    )
    
    result = loop.run(full_task)
    
    print(f"  → Final: {result.final_score:.1f}/10 ({result.num_iterations} iterations)")
    
    return {
        "name": step_name,
        "output": result.final_output,
        "score": result.final_score,
        "success": result.success,
        "iterations": result.num_iterations,
    }


def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║         Multi-Step Task Loop Example                       ║")
    print("║  Pattern: Step1 → Step2 → Step3 (with context passing)    ║")
    print("║  Each step: Run → Judge → Improve until 8.0+              ║")
    print("╚════════════════════════════════════════════════════════════╝")

    # Create specialized agents
    researcher = Agent(
        name="researcher",
        instructions="You are a research specialist. Find and summarize key information."
    )
    
    analyst = Agent(
        name="analyst", 
        instructions="You are an analyst. Identify patterns, insights, and implications."
    )
    
    writer = Agent(
        name="writer",
        instructions="You are a report writer. Create clear, actionable summaries."
    )

    # Define task steps
    steps = [
        {
            "name": "Research",
            "agent": researcher,
            "task": "Research the top 3 trends in AI for 2024-2025. Provide brief descriptions.",
            "criteria": "Covers 3 distinct trends with accurate descriptions.",
        },
        {
            "name": "Analysis",
            "agent": analyst,
            "task": "Analyze the implications of these AI trends for software development.",
            "criteria": "Identifies actionable insights and potential challenges.",
        },
        {
            "name": "Report",
            "agent": writer,
            "task": "Create a brief executive summary (3-4 bullet points) for a CTO.",
            "criteria": "Concise, actionable, appropriate for executive audience.",
        },
    ]

    # Run all steps with context passing
    results = []
    context = ""
    
    for step in steps:
        result = run_step(
            step_name=step["name"],
            agent=step["agent"],
            task=step["task"],
            criteria=step["criteria"],
            context=context,
        )
        results.append(result)
        context = result["output"]  # Pass output as context to next step

    # Summary
    print("\n" + "═"*60)
    print("SUMMARY")
    print("═"*60)
    
    total_iterations = sum(r["iterations"] for r in results)
    avg_score = sum(r["score"] for r in results) / len(results)
    all_success = all(r["success"] for r in results)
    
    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f"  {status} {r['name']}: {r['score']:.1f}/10 ({r['iterations']} iterations)")
    
    print(f"\n  Total Iterations: {total_iterations}")
    print(f"  Average Score: {avg_score:.1f}/10")
    print(f"  All Steps Passed: {'Yes' if all_success else 'No'}")

    print("\n" + "─"*60)
    print("FINAL REPORT OUTPUT:")
    print("─"*60)
    print(results[-1]["output"][:600])


if __name__ == "__main__":
    main()

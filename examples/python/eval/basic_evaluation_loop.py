"""
Basic EvaluationLoop Example

Demonstrates the iterative evaluation loop pattern:
Run agent → Judge output → Improve → Repeat until threshold met.

Usage:
    pip install praisonaiagents
    export OPENAI_API_KEY=your-key
    python basic_evaluation_loop.py
"""
from praisonaiagents import Agent
from praisonaiagents.eval import EvaluationLoop


def on_iteration(result):
    """Callback showing progress after each iteration."""
    status = "✅" if result.score >= 8.0 else "⚠️" if result.score >= 6.0 else "❌"
    print(f"{status} Iteration {result.iteration}: {result.score:.1f}/10")
    if result.findings:
        print(f"   → {result.findings[0][:60]}...")


def main():
    # Create an agent
    agent = Agent(
        name="writer",
        instructions="You are a technical content writer. Write clear, accurate explanations."
    )

    # Run evaluation loop
    loop = EvaluationLoop(
        agent=agent,
        criteria="""
        Evaluate the response on:
        1. CLARITY: Is the explanation easy to understand?
        2. ACCURACY: Is the technical content correct?
        3. COMPLETENESS: Does it cover the key aspects?
        4. EXAMPLES: Does it include practical examples?
        
        Score 1-10 based on all criteria.
        """,
        threshold=8.0,
        max_iterations=5,
        on_iteration=on_iteration,
        verbose=False,
    )

    print("╔════════════════════════════════════════════════════════════╗")
    print("║            Basic EvaluationLoop Example                     ║")
    print("║  Pattern: Run → Judge → Improve → Repeat                   ║")
    print("║  Target: 8.0/10 score                                       ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    result = loop.run("Explain how API rate limiting works and why it matters")

    print("\n" + "─" * 60)
    print("RESULTS:")
    print("─" * 60)
    print(f"Success: {result.success}")
    print(f"Final Score: {result.final_score:.1f}/10")
    print(f"Iterations: {result.num_iterations}")
    print(f"Score History: {[f'{s:.1f}' for s in result.score_history]}")
    print(f"Duration: {result.total_duration_seconds:.2f}s")

    print("\n" + "─" * 60)
    print("FINAL OUTPUT (first 500 chars):")
    print("─" * 60)
    print(result.final_output[:500] + "..." if len(result.final_output) > 500 else result.final_output)


if __name__ == "__main__":
    main()

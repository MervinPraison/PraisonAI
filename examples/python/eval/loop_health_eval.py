"""
Loop Health Evaluation Example

Demonstrates ``LoopEvaluator``, which scores loop *health* (convergence,
wasted iterations, doom-loop guard events) on top of an ``EvaluationLoop`` run.

Where ``EvaluationLoop`` tells you *what* score the agent reached, the
``LoopEvaluator`` tells you *how healthy* the loop was getting there:
- Did it converge, and in how many iterations?
- Were iterations wasted after the threshold was already met?
- Did a doom-loop safety guard fire?

Usage:
    pip install praisonaiagents
    export OPENAI_API_KEY=your-key
    python loop_health_eval.py
"""
from praisonaiagents import Agent
from praisonaiagents.eval import EvaluationLoop, LoopEvaluator


def main():
    agent = Agent(
        name="writer",
        instructions="You are a technical writer. Write clear, accurate explanations.",
    )

    loop = EvaluationLoop(
        agent=agent,
        criteria="Explanation is clear, accurate, and complete.",
        threshold=8.0,
        max_iterations=5,
    )

    # 1. Run the quality loop (existing behaviour).
    loop_result = loop.run("Explain how HTTPS works.")
    loop_result.print_summary()

    # 2. Collect any structured guard events emitted during the run.
    #    In a real setup these would come from doom_loop.py / loop_detection
    #    plugins. Here we pass an empty list (no guards fired).
    guard_events = []

    # 3. Score loop health.
    health = LoopEvaluator(threshold=8.0).run(loop_result, guard_events=guard_events)
    health.print_summary()

    if not health.success:
        print("\n⚠️  Loop was UNHEALTHY:")
        print(f"    {health.reasoning}")
    else:
        print("\n✅  Loop was healthy.")


if __name__ == "__main__":
    main()

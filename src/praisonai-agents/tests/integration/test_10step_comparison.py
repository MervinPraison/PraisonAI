#!/usr/bin/env python3
"""
Complex 10-step task comparison: wrapper vs caller vs iterative.

Tests the tool_completion fix with a realistic multi-tool prompt that requires:
1. Web search (3x for frameworks)
2. File creation (Python dict)
3. Code execution (verify dict)
4. File write (markdown report)
5. File read (verify report)
6. List files (confirm both exist)
7. System info
8. Code analysis
9. Code formatting
10. Web search (Python 3.13)
"""

import sys
import time
import os

# Ensure local package is used
sys.path.insert(0, os.path.dirname(__file__))

from praisonaiagents import Agent

COMPLEX_PROMPT = """Research the top 3 Python web frameworks (Django, FastAPI, Flask), then:
1) Search the web for each framework's latest version and key features
2) Create a file called /tmp/framework_comparison.py that contains a Python dictionary with the comparison data
3) Execute the code to verify the dictionary is valid
4) Write a markdown report to /tmp/framework_report.md summarizing your findings in a table format
5) Read back the report file to verify it was written correctly
6) List the files in /tmp to confirm both files exist
7) Get system info to note what OS this report was generated on
8) Analyze the Python code you wrote for any issues
9) Format the Python code properly
10) Finally search for any recent news about Python 3.13 features"""


def run_test(name, agent, prompt):
    """Run agent and return results dict."""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}\n")

    start = time.time()
    try:
        result = agent.start(prompt)
    except Exception as e:
        return {
            "name": name,
            "duration": time.time() - start,
            "error": str(e),
            "success": False,
        }

    duration = time.time() - start
    output = result.output if hasattr(result, "output") else str(result)
    reason = getattr(result, "completion_reason", None)
    iters = getattr(result, "iterations", None)
    success = getattr(result, "success", True)

    print(f"\n--- {name} RESULTS ---")
    print(f"Duration: {duration:.1f}s")
    if reason:
        print(f"Completion reason: {reason}")
    if iters:
        print(f"Iterations: {iters}")
    print(f"Response length: {len(output or '')} chars")
    print(f"Success: {success}")
    if output:
        print(f"\nFirst 600 chars of response:")
        print(output[:600])

    return {
        "name": name,
        "duration": duration,
        "reason": reason,
        "iterations": iters,
        "length": len(output or ""),
        "success": success,
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = []

    if mode in ("wrapper", "all"):
        os.environ["PRAISONAI_AUTO_APPROVE"] = "true"
        agent = Agent(
            name="wrapper_agent",
            instructions="You are a helpful research assistant.",
            llm="gpt-4o-mini",
        )
        results.append(run_test("wrapper", agent, COMPLEX_PROMPT))
        os.environ.pop("PRAISONAI_AUTO_APPROVE", None)

    if mode in ("caller", "all"):
        agent = Agent(
            name="caller_agent",
            instructions="You are a helpful research assistant.",
            llm="gpt-4o-mini",
            autonomy={
                "level": "full_auto",
                "mode": "caller",  # Single chat(), no loop
            },
        )
        results.append(run_test("caller", agent, COMPLEX_PROMPT))

    if mode in ("iterative", "all"):
        agent = Agent(
            name="iterative_agent",
            instructions="You are a helpful research assistant.",
            llm="gpt-4o-mini",
            autonomy={
                "level": "full_auto",
                "mode": "iterative",
                "max_iterations": 5,
            },
        )
        results.append(run_test("iterative", agent, COMPLEX_PROMPT))

    # Summary
    print(f"\n{'='*70}")
    print("COMPARISON SUMMARY")
    print(f"{'='*70}")
    for r in results:
        parts = [f"{r['name']:15s}: {r['duration']:6.1f}s"]
        if r.get("reason"):
            parts.append(f"reason={r['reason']}")
        if r.get("iterations"):
            parts.append(f"iters={r['iterations']}")
        parts.append(f"len={r['length']}")
        parts.append(f"ok={r['success']}")
        print("  " + " | ".join(parts))

    # Check if /tmp files were created
    print(f"\n--- File Creation Check ---")
    for f in ["/tmp/framework_comparison.py", "/tmp/framework_report.md"]:
        exists = os.path.exists(f)
        size = os.path.getsize(f) if exists else 0
        print(f"  {f}: {'EXISTS' if exists else 'MISSING'} ({size} bytes)")


if __name__ == "__main__":
    main()

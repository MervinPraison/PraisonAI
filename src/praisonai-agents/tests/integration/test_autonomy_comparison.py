#!/usr/bin/env python3
"""
Root-Cause Diagnosis: WHY does iterative mode loop / repeat?

Uses only LOW-RISK tools (internet_search, get_system_info, list_files)
to avoid approval gates and isolate the looping behavior.
"""
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from praisonaiagents import Agent
from praisonaiagents.tools import list_files, get_system_info, internet_search

# Simpler task using only low-risk tools
TASK = (
    "Do these 3 things: "
    "1) Search the web for 'Python 3.13 new features', "
    "2) Get system info to identify the current OS, "
    "3) List files in /tmp. "
    "After completing all 3 tasks, summarize the results."
)

TOOLS = [list_files, get_system_info, internet_search]


def run_test(name, agent, task):
    """Run a test and print results."""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")
    
    start = time.time()
    result = agent.start(task)
    elapsed = time.time() - start
    
    if hasattr(result, 'output'):
        # AutonomyResult
        print(f"\n--- {name} RESULTS ---")
        print(f"Duration: {elapsed:.1f}s")
        print(f"Completion reason: {result.completion_reason}")
        print(f"Iterations: {result.iterations}")
        print(f"Response length: {len(result.output or '')} chars")
        print(f"Success: {result.success}")
        out = result.output or ""
    else:
        out = str(result) if result else ""
        print(f"\n--- {name} RESULTS ---")
        print(f"Duration: {elapsed:.1f}s")
        print(f"Response length: {len(out)} chars")
    
    # Show first 600 chars
    print(f"\nFirst 600 chars of response:")
    print(out[:600])
    return elapsed, result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("test", choices=["wrapper", "iterative", "caller", "all"], default="all", nargs="?")
    args = parser.parse_args()
    
    results = {}
    
    if args.test in ("wrapper", "all"):
        agent = Agent(
            name="WrapperTest",
            instructions="You are a helpful AI assistant. Complete the task and stop.",
            tools=TOOLS,
        )
        results["wrapper"] = run_test("WRAPPER (no autonomy)", agent, TASK)
    
    if args.test in ("caller", "all"):
        agent = Agent(
            name="CallerTest",
            instructions="You are a helpful AI assistant. Complete the task and stop.",
            tools=TOOLS,
            autonomy={"mode": "caller"},
        )
        results["caller"] = run_test("CALLER (autonomy=caller)", agent, TASK)
    
    if args.test in ("iterative", "all"):
        agent = Agent(
            name="IterativeTest",
            instructions="You are a helpful AI assistant. Complete the task and stop.",
            tools=TOOLS,
            autonomy={
                "mode": "iterative",
                "max_iterations": 5,
                "clear_context": False,
            },
        )
        results["iterative"] = run_test("ITERATIVE (autonomy=iterative, max=5)", agent, TASK)
    
    # Summary
    if len(results) > 1:
        print(f"\n{'='*70}")
        print("COMPARISON SUMMARY")
        print(f"{'='*70}")
        for name, (elapsed, result) in results.items():
            if hasattr(result, 'output'):
                print(f"  {name:15s}: {elapsed:6.1f}s | reason={result.completion_reason} | iters={result.iterations} | len={len(result.output or '')}")
            else:
                print(f"  {name:15s}: {elapsed:6.1f}s | len={len(str(result))}")


if __name__ == "__main__":
    main()

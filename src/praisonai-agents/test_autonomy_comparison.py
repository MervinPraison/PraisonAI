"""
Real agentic test: Run a complex 10-step task through the autonomy loop.

This exercises:
- Web search (internet_search)
- File write/read (write_file, read_file)
- Code execution (execute_code)
- System info (get_system_info)
- Code analysis (analyze_code, format_code)
- File listing (list_files)

Measures: iterations, wall time, completion reason, tools used.
"""
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from praisonaiagents import Agent
from praisonaiagents.agent.autonomy import AutonomyConfig

TASK = """Research the top 3 Python web frameworks (Django, FastAPI, Flask), then:
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


def run_autonomy_test(name, autonomy_config, max_iter=25, timeout=120):
    """Run the task with a specific autonomy config."""
    print(f"\n{'='*70}")
    print(f"MODE: {name}")
    print(f"{'='*70}")
    
    agent = Agent(
        name="Research Agent",
        instructions=(
            "You are a thorough research assistant. Complete ALL steps in the task. "
            "Use your tools to search the web, create files, execute code, and analyze results. "
            "After completing all steps, summarize what you did."
        ),
        llm="gpt-4o-mini",
        autonomy=autonomy_config,
    )

    start = time.time()
    try:
        result = agent.run_autonomous(TASK, timeout_seconds=timeout)
        elapsed = time.time() - start
        
        print(f"  Success:        {result.success}")
        print(f"  Reason:         {result.completion_reason}")
        print(f"  Iterations:     {result.iterations}")
        print(f"  Wall time:      {elapsed:.1f}s")
        print(f"  Output length:  {len(str(result.output))} chars")
        print(f"  Output preview: {str(result.output)[:200]}...")
        
        return {
            "name": name,
            "success": result.success,
            "reason": result.completion_reason,
            "iterations": result.iterations,
            "wall_time": elapsed,
            "output_len": len(str(result.output)),
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        return {
            "name": name,
            "success": False,
            "reason": f"error",
            "iterations": 0,
            "wall_time": elapsed,
            "output_len": 0,
        }


if __name__ == "__main__":
    print("=" * 70)
    print("REAL AGENTIC TASK: 10-Step Web Framework Research")
    print("Testing autonomy loop with real LLM + real tools")
    print("=" * 70)
    
    results = []
    
    # --- Mode 1: Full auto, iterative (the mode we fixed) ---
    results.append(run_autonomy_test(
        "full_auto / iterative (FIXED)",
        {
            "level": "full_auto",
            "mode": "iterative",
            "max_iterations": 25,
            "auto_escalate": False,
        },
        timeout=120,
    ))
    
    # --- Mode 2: Full auto, caller (single-shot) ---
    results.append(run_autonomy_test(
        "full_auto / caller (single-shot)",
        {
            "level": "full_auto",
            "mode": "caller",
            "max_iterations": 25,
        },
        timeout=120,
    ))
    
    # --- Mode 3: suggest / caller (minimal autonomy) ---
    results.append(run_autonomy_test(
        "suggest / caller (minimal)",
        {
            "level": "suggest",
            "mode": "caller",
            "max_iterations": 10,
        },
        timeout=60,
    ))
    
    # Check output files
    print("\n" + "=" * 70)
    print("FILE VERIFICATION")
    print("=" * 70)
    for f in ["/tmp/framework_comparison.py", "/tmp/framework_report.md"]:
        exists = os.path.exists(f)
        size = os.path.getsize(f) if exists else 0
        print(f"  {f}: {'✅ exists' if exists else '❌ missing'} ({size} bytes)")
        if exists:
            with open(f) as fh:
                print(f"    Preview: {fh.read()[:150]}...")
    
    # Summary
    print("\n" + "=" * 90)
    print("COMPARISON SUMMARY")
    print("=" * 90)
    print(f"{'Mode':<40} {'OK':>4} {'Reason':<18} {'Iters':>5} {'Time':>8} {'Output':>8}")
    print("-" * 90)
    for r in results:
        ok = "✅" if r["success"] else "❌"
        print(f"{r['name']:<40} {ok:>4} {r['reason']:<18} {r['iterations']:>5} {r['wall_time']:>7.1f}s {r['output_len']:>7}")
    print("-" * 90)

    # Key analysis
    print("\nKEY FINDINGS:")
    iterative = next((r for r in results if "iterative" in r["name"]), None)
    caller = next((r for r in results if "caller" in r["name"] and "full_auto" in r["name"]), None)
    if iterative and caller:
        if iterative["reason"] != "max_iterations":
            print(f"  ✅ Iterative mode completed properly ({iterative['reason']}) — NO infinite loop")
        else:
            print(f"  ❌ Iterative mode hit max_iterations — loop NOT fixed")
        
        print(f"  📊 Iterative: {iterative['iterations']} iters, {iterative['wall_time']:.1f}s")
        print(f"  📊 Caller:    {caller['iterations']} iter,  {caller['wall_time']:.1f}s")
        
        if iterative["iterations"] > 1:
            print(f"  ✅ Iterative mode used multiple iterations (multi-turn agentic loop)")
        else:
            print(f"  ℹ️  Iterative completed in 1 iteration (model finished all tool calls in single turn)")

"""
Autonomy Mode Comparison: Verifies loop fix and compares all modes.

Tests:
1. Simple iterative task with tools — should complete quickly
2. No-tool-call termination — model with no tools should auto-terminate
3. Caller mode — single shot, should be fast
4. Multi-tool task — iterative with multiple tools
5. Completion promise — should honor <promise> tag
6. autonomy=True default (caller mode)
7. Full auto string shorthand
"""
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from praisonaiagents import Agent

# Simple tools for testing
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: 72°F, sunny"

def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

def search_files(query: str) -> str:
    """Search for files matching a query."""
    return f"Found 3 files matching '{query}': file1.txt, file2.py, file3.md"


def run_test(name, agent, prompt, timeout=60):
    """Run a single autonomy test and capture results."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    
    start = time.time()
    try:
        result = agent.run_autonomous(prompt, timeout_seconds=timeout)
        elapsed = time.time() - start
        
        print(f"  Success:     {result.success}")
        print(f"  Reason:      {result.completion_reason}")
        print(f"  Iterations:  {result.iterations}")
        print(f"  Wall time:   {elapsed:.2f}s")
        print(f"  Output:      {str(result.output)[:150]}...")
        
        return {
            "name": name,
            "success": result.success,
            "reason": result.completion_reason,
            "iterations": result.iterations,
            "wall_time": elapsed,
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        return {
            "name": name,
            "success": False,
            "reason": f"error: {e}",
            "iterations": 0,
            "wall_time": elapsed,
        }


# ============================================================
# Tests
# ============================================================

def test_simple_task():
    """Iterative mode with tools — should call tool and terminate."""
    agent = Agent(
        instructions="You are a helpful weather assistant. Answer the question using your tools, then stop.",
        tools=[get_weather],
        llm="gpt-4o-mini",
        autonomy={"max_iterations": 10, "level": "full_auto", "mode": "iterative", "auto_escalate": False},
    )
    return run_test("Simple task (iterative+tools)", agent,
                    "What's the weather in London?", timeout=30)


def test_no_tool_termination():
    """Agent with NO tools, iterative mode — should terminate via no_tool_calls."""
    agent = Agent(
        instructions="Answer the question concisely and then stop.",
        llm="gpt-4o-mini",
        autonomy={"max_iterations": 10, "level": "full_auto", "mode": "iterative", "auto_escalate": False},
    )
    return run_test("No-tool termination (iterative)", agent,
                    "What is 2 + 2?", timeout=30)


def test_caller_mode():
    """Caller mode — single chat call, no loop."""
    agent = Agent(
        instructions="You are a helpful weather assistant.",
        tools=[get_weather],
        llm="gpt-4o-mini",
        autonomy={"max_iterations": 10, "level": "suggest", "mode": "caller"},
    )
    return run_test("Caller mode (single shot)", agent,
                    "What's the weather in Tokyo?", timeout=30)


def test_multi_tool():
    """Agent with multiple tools, multi-step task."""
    agent = Agent(
        instructions="You are a helpful assistant. Use your tools to answer, then summarize and stop.",
        tools=[get_weather, add_numbers, search_files],
        llm="gpt-4o-mini",
        autonomy={"max_iterations": 10, "level": "full_auto", "mode": "iterative", "auto_escalate": False},
    )
    return run_test("Multi-tool task (iterative)", agent,
                    "What's the weather in Paris, and what's 15 + 27?", timeout=45)


def test_promise_completion():
    """Agent with completion promise — should detect promise tag."""
    agent = Agent(
        instructions="You are a helpful assistant. When you are done, include <promise>DONE</promise> in your response.",
        tools=[add_numbers],
        llm="gpt-4o-mini",
        autonomy={
            "max_iterations": 10, "level": "full_auto", "mode": "iterative",
            "auto_escalate": False, "completion_promise": "DONE",
        },
    )
    return run_test("Promise completion (iterative)", agent,
                    "Calculate 10 + 20. When done, emit the promise tag.", timeout=30)


def test_autonomy_true():
    """autonomy=True — defaults to caller mode (suggest level)."""
    agent = Agent(
        instructions="Answer the question.",
        tools=[get_weather],
        llm="gpt-4o-mini",
        autonomy=True,
    )
    return run_test("autonomy=True (caller default)", agent,
                    "What's the weather in Berlin?", timeout=30)


def test_full_auto():
    """Full auto level with iterative mode."""
    agent = Agent(
        instructions="You are a math assistant. Use your tools and answer.",
        tools=[add_numbers],
        llm="gpt-4o-mini",
        autonomy={"level": "full_auto"},
    )
    return run_test("Full auto (level=full_auto)", agent,
                    "What is 100 + 200?", timeout=30)


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("AUTONOMY MODE COMPARISON TEST")
    print("Verifying loop fix: content detection + no-tool termination")
    print("=" * 60)
    
    results = []
    results.append(test_simple_task())
    results.append(test_no_tool_termination())
    results.append(test_caller_mode())
    results.append(test_multi_tool())
    results.append(test_promise_completion())
    results.append(test_autonomy_true())
    results.append(test_full_auto())
    
    # Summary table
    print("\n\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    print(f"{'Test':<45} {'OK':>4} {'Reason':<18} {'Iters':>5} {'Time':>8}")
    print("-" * 90)
    for r in results:
        ok = "✅" if r["success"] else "❌"
        print(f"{r['name']:<45} {ok:>4} {r['reason']:<18} {r['iterations']:>5} {r['wall_time']:>7.2f}s")
    print("-" * 90)
    
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    
    # Key checks
    print("\n" + "=" * 60)
    print("KEY VERIFICATION")
    print("=" * 60)
    
    for r in results:
        if "No-tool" in r["name"]:
            if r["reason"] == "no_tool_calls":
                print(f"✅ No-tool-call termination WORKS ({r['iterations']} iters, {r['wall_time']:.1f}s)")
            else:
                print(f"⚠️  No-tool-call terminated via: {r['reason']}")
        
        if r["reason"] == "max_iterations":
            print(f"❌ {r['name']}: Hit max_iterations — LOOP NOT FIXED")
        
        if "Caller" in r["name"] or "caller" in r["name"]:
            print(f"{'✅' if r['iterations'] <= 1 else '⚠️'}  Caller mode: {r['iterations']} iter, {r['wall_time']:.1f}s")

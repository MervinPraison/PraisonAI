#!/usr/bin/env python3
"""
Deep performance profiling integration test.

Runs cProfile-wrapped Agent prompts and stores full function-level
breakdown as JSONL for regression tracking. Each run appends a
timestamped record so you can compare performance over time.

Usage:
    # Run with pytest (records stored automatically)
    pytest tests/integration/test_performance_profile.py -v -s

    # Run directly (more detailed output)
    python tests/integration/test_performance_profile.py

    # Compare recent results
    python tests/integration/test_performance_profile.py --compare

    # Profile a specific model
    python tests/integration/test_performance_profile.py --model gpt-5-nano

    # Compare two models
    PROFILE_MODELS=gpt-5-nano,gpt-4o-mini python tests/integration/test_performance_profile.py

Results are stored in:
    tests/integration/profile_results/performance_history.jsonl
"""

import cProfile
import json
import os
import platform
import pstats
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, Tuple

import pytest

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "profile_results"
HISTORY_FILE = RESULTS_DIR / "performance_history.jsonl"

# Default model — override via PROFILE_MODEL env var
DEFAULT_MODEL = os.environ.get("PROFILE_MODEL", "gpt-4o-mini")

# Number of top functions to record
TOP_FUNCTIONS = 30

# Prompts
SIMPLE_PROMPT = "What is 2+2? Reply with just the number."
COMPLEX_PROMPT = (
    "List the top 3 programming languages by popularity in 2024. "
    "For each, give the name and one key strength. Keep it under 100 words."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_results_dir():
    """Create results directory if it doesn't exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    gitignore = RESULTS_DIR / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("# Auto-generated profile results\n*.jsonl\n*.txt\n")


def _get_version() -> str:
    """Get the current praisonaiagents version."""
    try:
        from praisonaiagents import __version__
        return __version__
    except (ImportError, AttributeError):
        return "unknown"


def _extract_function_stats(profiler: cProfile.Profile, top_n: int = TOP_FUNCTIONS) -> List[Dict]:
    """Extract top function stats from a cProfile.Profile instance."""
    stats = pstats.Stats(profiler, stream=StringIO())
    stats.sort_stats("cumulative")

    function_stats = []
    for (filename, line, name), (cc, nc, tt, ct, callers) in stats.stats.items():
        function_stats.append({
            "name": name,
            "file": os.path.basename(filename) if filename else "",
            "line": line,
            "calls": nc,
            "total_ms": round(tt * 1000, 2),
            "cumulative_ms": round(ct * 1000, 2),
        })

    function_stats.sort(key=lambda x: x["cumulative_ms"], reverse=True)
    return function_stats[:top_n]


def _extract_category_breakdown(function_stats: List[Dict]) -> Dict[str, float]:
    """Categorize function time into buckets: network, imports, framework, other."""
    categories = {
        "network_ms": 0.0,
        "imports_ms": 0.0,
        "framework_ms": 0.0,
        "other_ms": 0.0,
    }

    seen = set()
    for fn in function_stats:
        key = (fn["name"], fn["file"])
        if key in seen:
            continue
        seen.add(key)

        name = fn["name"]
        file = fn["file"]
        cum = fn["cumulative_ms"]

        # Network: SSL, socket, recv, send
        if name in ("recv", "send", "connect") or "ssl" in file.lower() or "_socket" in file:
            categories["network_ms"] = max(categories["network_ms"], cum)
        # Imports
        elif name in ("_find_and_load", "_find_and_load_unlocked", "_load_unlocked",
                       "exec_module", "_call_with_frames_removed") or "importlib" in file:
            categories["imports_ms"] = max(categories["imports_ms"], cum)
        # Framework
        elif "praisonai" in file.lower() or name in ("chat", "get_response", "start",
                                                       "_chat_impl", "create_completion"):
            categories["framework_ms"] = max(categories["framework_ms"], cum)

    return categories


def _run_deep_profile(
    prompt: str,
    model: str = DEFAULT_MODEL,
    runs: int = 3,
) -> Dict[str, Any]:
    """
    Run a cProfile-wrapped Agent execution (deep profile).

    Captures:
    - Wall-clock timing for agent init and execution phases
    - cProfile function-level stats (top N by cumulative time)
    - Category breakdown (network, imports, framework)
    """
    from praisonaiagents import Agent

    all_runs = []

    for i in range(runs):
        # --- Phase 1: Agent init (timed but not cProfiled) ---
        init_start = time.perf_counter()
        agent = Agent(
            instructions="Be concise.",
            llm={"model": model},
            output="silent",
        )
        init_ms = (time.perf_counter() - init_start) * 1000

        # --- Phase 2: Execution with cProfile deep profiling ---
        profiler = cProfile.Profile()
        exec_start = time.perf_counter()

        profiler.enable()
        try:
            result = agent.start(prompt)
        finally:
            profiler.disable()

        exec_ms = (time.perf_counter() - exec_start) * 1000
        total_ms = init_ms + exec_ms

        # --- Extract deep profile data ---
        top_functions = _extract_function_stats(profiler)
        categories = _extract_category_breakdown(top_functions)

        all_runs.append({
            "run": i + 1,
            "init_ms": round(init_ms, 2),
            "execution_ms": round(exec_ms, 2),
            "total_ms": round(total_ms, 2),
            "response_length": len(str(result)) if result else 0,
            "top_functions": top_functions,
            "categories": categories,
        })

    # --- Aggregate ---
    exec_times = [r["execution_ms"] for r in all_runs]
    init_times = [r["init_ms"] for r in all_runs]
    total_times = [r["total_ms"] for r in all_runs]

    # Average the category breakdowns
    avg_categories = {}
    for key in ["network_ms", "imports_ms", "framework_ms"]:
        vals = [r["categories"].get(key, 0) for r in all_runs]
        avg_categories[key] = round(mean(vals), 2)

    return {
        "prompt_label": prompt[:60] + "..." if len(prompt) > 60 else prompt,
        "model": model,
        "runs": runs,
        "profile_type": "deep",
        "individual_runs": all_runs,
        "execution_ms": {
            "mean": round(mean(exec_times), 2),
            "median": round(median(exec_times), 2),
            "stdev": round(stdev(exec_times), 2) if len(exec_times) > 1 else 0,
            "min": round(min(exec_times), 2),
            "max": round(max(exec_times), 2),
        },
        "init_ms": {
            "mean": round(mean(init_times), 2),
            "median": round(median(init_times), 2),
        },
        "total_ms": {
            "mean": round(mean(total_times), 2),
            "median": round(median(total_times), 2),
        },
        "avg_categories": avg_categories,
        # Store the top functions from the last run for display
        "top_functions_snapshot": all_runs[-1]["top_functions"][:20],
    }


def _save_result(record: Dict[str, Any]) -> Dict[str, Any]:
    """Append a profiling record to the JSONL history file."""
    _ensure_results_dir()

    record["timestamp"] = datetime.now(timezone.utc).isoformat()
    record["version"] = _get_version()
    record["python"] = platform.python_version()
    record["platform"] = platform.system()
    record["machine"] = platform.machine()

    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")

    return record


def _load_history() -> List[Dict[str, Any]]:
    """Load all historical profiling records."""
    if not HISTORY_FILE.exists():
        return []
    records = []
    for line in HISTORY_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _print_deep_report(label: str, result: Dict, history: List[Dict], model: str):
    """Print a deep profile report with function-level breakdown."""
    # Filter matching history
    matching = [
        r for r in history
        if r.get("model") == model
        and r.get("prompt_label") == result.get("prompt_label")
        and r.get("profile_type") == "deep"
    ]

    print(f"\n{'=' * 70}")
    print(f"  DEEP PROFILE: {label}")
    print(f"{'=' * 70}")
    print(f"  Model:     {model}")
    print(f"  Runs:      {result['runs']}")
    print(f"  Exec:      {result['execution_ms']['mean']:.0f}ms "
          f"(±{result['execution_ms']['stdev']:.0f}ms)")
    print(f"  Init:      {result['init_ms']['mean']:.1f}ms")
    print(f"  Total:     {result['total_ms']['mean']:.0f}ms")

    # Category breakdown
    cats = result.get("avg_categories", {})
    print(f"\n  Category Breakdown:")
    print(f"    Network (SSL/recv):  {cats.get('network_ms', 0):.0f}ms")
    print(f"    Imports:             {cats.get('imports_ms', 0):.0f}ms")
    print(f"    Framework:           {cats.get('framework_ms', 0):.0f}ms")

    # Top functions
    top_fns = result.get("top_functions_snapshot", [])
    if top_fns:
        print(f"\n  Top Functions by Cumulative Time:")
        print(f"  {'Function':<45} {'Calls':>6} {'Cumul (ms)':>12}")
        print(f"  {'-' * 65}")
        for fn in top_fns[:15]:
            name = fn["name"][:44]
            print(f"  {name:<45} {fn['calls']:>6} {fn['cumulative_ms']:>11.2f}")

    # Historical comparison
    if matching:
        prev = matching[-1]
        prev_mean = prev["execution_ms"]["mean"]
        curr_mean = result["execution_ms"]["mean"]
        delta = curr_mean - prev_mean
        pct = (delta / prev_mean * 100) if prev_mean > 0 else 0

        emoji = "🟢" if delta <= 0 else ("🔴" if pct > 20 else "🟡")
        print(f"\n  {emoji} vs previous ({prev.get('timestamp', '?')[:10]}):")
        print(f"     Previous: {prev_mean:.0f}ms → Current: {curr_mean:.0f}ms "
              f"({delta:+.0f}ms, {pct:+.1f}%)")

        if len(matching) >= 3:
            all_means = [r["execution_ms"]["mean"] for r in matching[-10:]]
            print(f"\n  📊 Last {len(all_means)} runs: "
                  f"avg={mean(all_means):.0f}ms, "
                  f"range={min(all_means):.0f}-{max(all_means):.0f}ms")
    else:
        print(f"\n  ℹ️  First deep profile — no history to compare")

    print()


# ---------------------------------------------------------------------------
# Pytest Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY required for live profiling"
)
class TestDeepPerformanceProfile:
    """Live deep performance profiling tests with result storage."""

    def test_simple_prompt_deep_profile(self):
        """Deep profile a simple prompt and store results."""
        model = DEFAULT_MODEL
        result = _run_deep_profile(SIMPLE_PROMPT, model=model, runs=3)
        _save_result({"test": "simple_prompt", **result})

        history = _load_history()
        _print_deep_report("Simple Prompt", result, history, model)

        # Sanity checks
        assert result["execution_ms"]["mean"] > 0, "Execution should take time"
        assert result["init_ms"]["mean"] < 2000, "Init should be under 2s"
        assert result.get("top_functions_snapshot"), "Should have function stats"
        assert all(r["response_length"] > 0 for r in result["individual_runs"]), \
            "All runs should produce output"

    def test_complex_prompt_deep_profile(self):
        """Deep profile a complex prompt and store results."""
        model = DEFAULT_MODEL
        result = _run_deep_profile(COMPLEX_PROMPT, model=model, runs=3)
        _save_result({"test": "complex_prompt", **result})

        history = _load_history()
        _print_deep_report("Complex Prompt", result, history, model)

        assert result["execution_ms"]["mean"] > 0
        assert result.get("top_functions_snapshot")

    def test_multi_model_deep_comparison(self):
        """Deep profile across multiple models (set PROFILE_MODELS env var)."""
        models = os.environ.get("PROFILE_MODELS", DEFAULT_MODEL).split(",")
        models = [m.strip() for m in models if m.strip()]

        for model in models:
            result = _run_deep_profile(SIMPLE_PROMPT, model=model, runs=2)
            _save_result({"test": "model_comparison", **result})

            history = _load_history()
            _print_deep_report(f"Model: {model}", result, history, model)

            assert result["execution_ms"]["mean"] > 0


# ---------------------------------------------------------------------------
# CLI: Direct execution
# ---------------------------------------------------------------------------

def main():
    """Run deep profiles directly and show comparison."""
    import argparse

    parser = argparse.ArgumentParser(description="Deep performance profiling tool")
    parser.add_argument("--compare", action="store_true",
                        help="Show comparison of historical results only")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Model to profile (default: {DEFAULT_MODEL})")
    parser.add_argument("--runs", type=int, default=3,
                        help="Number of runs per prompt (default: 3)")
    args = parser.parse_args()

    if args.compare:
        history = _load_history()
        if not history:
            print("No history found. Run profiles first.")
            return

        # Group by test + model
        groups: Dict[str, List] = {}
        for r in history:
            if r.get("profile_type") != "deep":
                continue
            key = f"{r.get('test', 'unknown')}|{r.get('model', 'unknown')}"
            groups.setdefault(key, []).append(r)

        for key, records in groups.items():
            test_name, model = key.split("|")
            print(f"\n{'=' * 70}")
            print(f"  {test_name} ({model}) — Deep Profile History")
            print(f"{'=' * 70}")
            print(f"  {'Date':<22} {'Exec':>8} {'Init':>8} "
                  f"{'Network':>10} {'Imports':>10}  Ver")
            print(f"  {'─' * 70}")

            for r in records[-10:]:
                ts = r.get("timestamp", "")[:19]
                ex = r.get("execution_ms", {})
                cats = r.get("avg_categories", {})
                ver = r.get("version", "?")
                print(f"  {ts:<22} {ex.get('mean', 0):>7.0f}ms"
                      f" {r.get('init_ms', {}).get('mean', 0):>7.1f}ms"
                      f" {cats.get('network_ms', 0):>9.0f}ms"
                      f" {cats.get('imports_ms', 0):>9.0f}ms"
                      f"  {ver}")

            # Trend
            if len(records) >= 2:
                first_mean = records[0]["execution_ms"]["mean"]
                last_mean = records[-1]["execution_ms"]["mean"]
                delta = last_mean - first_mean
                pct = (delta / first_mean * 100) if first_mean > 0 else 0
                emoji = "📈" if delta > 0 else "📉"
                print(f"\n  {emoji} Trend: {delta:+.0f}ms ({pct:+.1f}%) "
                      f"over {len(records)} runs")
        return

    # Run deep profiles
    print("=" * 70)
    print("  DEEP PERFORMANCE PROFILING")
    print(f"  Model: {args.model}  |  Runs: {args.runs}  |  cProfile: ON")
    print("=" * 70)

    prompts = {
        "simple_prompt": SIMPLE_PROMPT,
        "complex_prompt": COMPLEX_PROMPT,
    }

    for test_name, prompt in prompts.items():
        print(f"\n▸ Running deep profile: {test_name}...")
        result = _run_deep_profile(prompt, model=args.model, runs=args.runs)
        _save_result({"test": test_name, **result})

        history = _load_history()
        _print_deep_report(test_name.replace("_", " ").title(), result, history, args.model)

    print(f"\n✅ Deep profile results stored in: {HISTORY_FILE}")
    print("   Run with --compare to see trends over time.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
PraisonAI Agents - Real Execution Benchmark

Benchmarks ACTUAL agent execution with LLM API calls.
Tests single agent running a simple task across frameworks.

Each framework gets untimed warm-up calls first (imports, client set-up and
the first connection are not what this measures), then the timed runs are
interleaved round by round so network drift hits every framework alike.
A run that raises or returns an empty answer is counted as a failure, not
timed. The summary reports the median.

Usage:
    export OPENAI_API_KEY=your_key
    python benchmarks/execution_benchmark.py
    python benchmarks/execution_benchmark.py --save
    python benchmarks/execution_benchmark.py --iterations 10
    python benchmarks/execution_benchmark.py --model gpt-4o --iterations 10
"""

import argparse
import os
import statistics
import time
from importlib.metadata import version as get_version

# Defaults (can be overridden via CLI)
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ITERATIONS = 10
DEFAULT_WARMUP = 1
DEFAULT_PROMPT = "What is 2+2? Reply with just the number."
INSTRUCTIONS = "You are a helpful assistant. Be very brief."

METHODS = {
    'PraisonAI': 'agent.start()',
    'PraisonAI (LiteLLM)': 'agent.start()',
    'Agno': 'agent.run()',
    'CrewAI': 'crew.kickoff()',
}


def get_package_versions():
    """Get version numbers for benchmarked packages."""
    packages = {
        'PraisonAI': 'praisonaiagents',
        'Agno': 'agno',
        'CrewAI': 'crewai',
    }
    versions = {}
    for name, pkg in packages.items():
        try:
            versions[name] = get_version(pkg)
        except Exception:
            versions[name] = 'not installed'
    return versions


def praisonai_runner(model, prompt):
    """PraisonAI: a new agent per run, timed through agent.start()."""
    from praisonaiagents import Agent

    def run():
        agent = Agent(name="Calculator", instructions=INSTRUCTIONS, llm=model)
        return agent.start(prompt, output="silent")
    return run


def agno_runner(model, prompt):
    """Agno: a new agent per run, timed through agent.run()."""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    def run():
        agent = Agent(model=OpenAIChat(id=model), instructions=[INSTRUCTIONS])
        response = agent.run(prompt)
        # Agno reports a failed run in ``status`` and puts the error text in
        # ``content``, so the content alone would pass for an answer.
        if str(getattr(response, 'status', '')).lower().endswith('error'):
            raise RuntimeError(f"Agno run failed: {str(response.content)[:200]}")
        return getattr(response, 'content', response)
    return run


def crewai_runner(model, prompt):
    """CrewAI: a new one-agent crew per run, timed through crew.kickoff()."""
    from crewai import Agent, Crew, Task

    def run():
        agent = Agent(role="Calculator", goal="Answer math questions",
                      backstory=INSTRUCTIONS, llm=model, verbose=False)
        task = Task(description=prompt, expected_output="A number", agent=agent)
        return Crew(agents=[agent], tasks=[task], verbose=False).kickoff()
    return run


def build_runners(model, prompt):
    """Return {framework: run()} for every framework that is installed."""
    factories = [
        ('PraisonAI', lambda: praisonai_runner(model, prompt)),
        ('PraisonAI (LiteLLM)', lambda: praisonai_runner(f"openai/{model}", prompt)),
        ('Agno', lambda: agno_runner(model, prompt)),
        ('CrewAI', lambda: crewai_runner(model, prompt)),
    ]
    runners = {}
    for name, factory in factories:
        try:
            runners[name] = factory()
        except ImportError as e:
            print(f"  {name}: skipped ({e})")
    return runners


def answer_text(response):
    """The answer as text, or '' when the run produced nothing usable."""
    if response is None:
        return ''
    text = str(response).strip()
    return '' if text == 'None' else text


def run_benchmark(runners, iterations, warmup):
    """Warm up each framework, then time interleaved rounds.

    Returns {framework: {"times": [...], "failures": [...]}}.
    """
    results = {name: {"times": [], "failures": []} for name in runners}

    for name, run in list(runners.items()):
        for _ in range(warmup):
            try:
                if not answer_text(run()):
                    raise RuntimeError("empty answer")
            except Exception as e:
                print(f"  {name}: warm-up failed ({type(e).__name__}: {str(e)[:120]}); excluded")
                runners.pop(name)
                results[name]["failures"].append(f"warm-up: {type(e).__name__}: {e}")
                break

    for i in range(iterations):
        for name, run in runners.items():
            start = time.perf_counter()
            try:
                text = answer_text(run())
                error = None if text else "empty answer"
            except Exception as e:
                text, error = '', f"{type(e).__name__}: {e}"
            elapsed = time.perf_counter() - start
            if error:
                results[name]["failures"].append(error)
                print(f"  Round {i + 1} {name}: FAILED ({error[:120]})")
            else:
                results[name]["times"].append(elapsed)
                print(f"  Round {i + 1} {name}: {elapsed:.2f}s - {text[:40]}")
    return results


def summarise(results):
    """Rows of (framework, median, mean, ok, failed), fastest median first."""
    rows = []
    for name, r in results.items():
        times = r["times"]
        if times:
            rows.append((name, statistics.median(times), statistics.fmean(times),
                         len(times), len(r["failures"])))
    return sorted(rows, key=lambda row: row[1])


def save_results(rows, results, model, iterations, warmup, prompt):
    """Save results to markdown file."""
    from datetime import datetime

    filepath = os.path.join(os.path.dirname(__file__), 'EXECUTION_BENCHMARK_RESULTS.md')
    versions = get_package_versions()
    fastest = rows[0][1]

    with open(filepath, 'w') as f:
        f.write('# PraisonAI Agents - Real Execution Benchmark\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'**Model:** {model}\n')
        f.write(f'**Iterations:** {iterations} interleaved rounds after {warmup} warm-up call(s) per framework\n')
        f.write(f'**Prompt:** "{prompt}"\n\n')
        f.write('## Results\n\n')
        f.write('| Framework | Method | Median | Mean | Runs ok / failed | Relative |\n')
        f.write('|-----------|--------|--------|------|------------------|----------|\n')
        for name, median, mean, ok, failed in rows:
            ratio = median / fastest
            method = METHODS.get(name, 'unknown')
            if ratio == 1.0:
                f.write(f'| **{name}** | `{method}` | **{median:.2f}s** | {mean:.2f}s | {ok} / {failed} | **1.00x (fastest)** |\n')
            else:
                f.write(f'| {name} | `{method}` | {median:.2f}s | {mean:.2f}s | {ok} / {failed} | {ratio:.2f}x |\n')
        excluded = [name for name, r in results.items() if not r["times"]]
        if excluded:
            f.write(f'\nNo successful runs (not ranked): {", ".join(excluded)}\n')

        f.write('\n## Package Versions\n\n')
        f.write('| Package | Version |\n')
        f.write('|---------|--------|\n')
        for pkg, ver in versions.items():
            f.write(f'| {pkg} | {ver} |\n')

        f.write('\n## How to Reproduce\n\n')
        f.write('```bash\n')
        f.write('export OPENAI_API_KEY=your_key\n')
        f.write('cd src/praisonai-agents\n')
        f.write('python benchmarks/execution_benchmark.py --save\n')
        f.write('```\n')

    print(f'\nResults saved to: {filepath}')


def main():
    parser = argparse.ArgumentParser(description='PraisonAI Agents - Real Execution Benchmark')
    parser.add_argument('--save', action='store_true', help='Save results to EXECUTION_BENCHMARK_RESULTS.md')
    parser.add_argument('--model', '-m', type=str, default=DEFAULT_MODEL, help=f'Model to use (default: {DEFAULT_MODEL})')
    parser.add_argument('--iterations', '-i', type=int, default=DEFAULT_ITERATIONS, help=f'Timed rounds (default: {DEFAULT_ITERATIONS})')
    parser.add_argument('--warmup', '-w', type=int, default=DEFAULT_WARMUP, help=f'Untimed warm-up calls per framework (default: {DEFAULT_WARMUP})')
    parser.add_argument('--prompt', '-p', type=str, default=DEFAULT_PROMPT, help=f'Prompt to use (default: "{DEFAULT_PROMPT}")')
    args = parser.parse_args()

    if not os.environ.get('OPENAI_API_KEY'):
        print("ERROR: Set OPENAI_API_KEY environment variable")
        return 1

    print('=' * 60)
    print('PraisonAI Agents - Real Execution Benchmark')
    print('=' * 60)
    print(f'\nModel: {args.model}')
    print(f'Rounds: {args.iterations} (after {args.warmup} warm-up call(s) per framework)')
    print(f'Prompt: "{args.prompt}"')
    print('\nPackage versions:')
    for pkg, ver in get_package_versions().items():
        print(f'  {pkg}: {ver}')
    print()

    runners = build_runners(args.model, args.prompt)
    results = run_benchmark(runners, args.iterations, args.warmup)
    rows = summarise(results)

    print('\n' + '=' * 60)
    print('SUMMARY (median of successful runs)')
    print('=' * 60)
    if rows:
        fastest = rows[0][1]
        print(f"\n{'Framework':<22} {'Median':>8} {'Mean':>8} {'ok/failed':>10} {'Relative':>9}")
        print('-' * 61)
        for name, median, mean, ok, failed in rows:
            print(f'{name:<22} {median:>7.2f}s {mean:>7.2f}s {ok:>5}/{failed:<4} {median / fastest:>8.2f}x')
    for name, r in results.items():
        if not r["times"]:
            print(f'{name:<22} no successful runs: {(r["failures"] or ["?"])[0][:80]}')
    print('\n' + '=' * 60)

    if rows and args.save:
        save_results(rows, results, args.model, args.iterations, args.warmup, args.prompt)
    elif not args.save:
        print('\nResults not saved (use --save flag to save results to file)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

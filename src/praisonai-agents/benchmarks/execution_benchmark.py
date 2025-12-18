#!/usr/bin/env python3
"""
PraisonAI Agents - Real Execution Benchmark

Benchmarks ACTUAL agent execution with LLM API calls.
Tests single agent running a simple task across frameworks.

Usage:
    export OPENAI_API_KEY=your_key
    python benchmarks/execution_benchmark.py
    python benchmarks/execution_benchmark.py --no-save
    python benchmarks/execution_benchmark.py --iterations 5
    python benchmarks/execution_benchmark.py --model gpt-4o --iterations 10
"""

import time
import os
import argparse
from importlib.metadata import version as get_version

# Defaults (can be overridden via CLI)
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ITERATIONS = 3
DEFAULT_PROMPT = "What is 2+2? Reply with just the number."


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
        except:
            versions[name] = 'not installed'
    return versions


def benchmark_praisonai(model, iterations, prompt):
    """Benchmark PraisonAI agent execution using agent.start()"""
    from praisonaiagents import Agent
    
    print("\n--- PraisonAI ---")
    print("Method: agent.start()")
    
    times = []
    for i in range(iterations):
        agent = Agent(
            name="Calculator",
            instructions="You are a helpful assistant. Be very brief.",
            llm=model,
            verbose=False
        )
        
        start = time.perf_counter()
        response = agent.start(prompt)
        elapsed = time.perf_counter() - start
        
        times.append(elapsed)
        print(f"  Run {i+1}: {elapsed:.2f}s - Response: {str(response)[:50]}")
    
    avg = sum(times) / len(times)
    print(f"  Average: {avg:.2f}s")
    return avg


def benchmark_praisonai_litellm(model, iterations, prompt):
    """Benchmark PraisonAI with LiteLLM backend using agent.start()"""
    from praisonaiagents import Agent
    
    print("\n--- PraisonAI (LiteLLM) ---")
    print("Method: agent.start()")
    
    times = []
    for i in range(iterations):
        agent = Agent(
            name="Calculator",
            instructions="You are a helpful assistant. Be very brief.",
            llm=f"openai/{model}",
            verbose=False
        )
        
        start = time.perf_counter()
        response = agent.start(prompt)
        elapsed = time.perf_counter() - start
        
        times.append(elapsed)
        print(f"  Run {i+1}: {elapsed:.2f}s - Response: {str(response)[:50]}")
    
    avg = sum(times) / len(times)
    print(f"  Average: {avg:.2f}s")
    return avg


def benchmark_agno(model, iterations, prompt):
    """Benchmark Agno agent execution using agent.run()"""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    
    print("\n--- Agno ---")
    print("Method: agent.run()")
    
    times = []
    for i in range(iterations):
        agent = Agent(
            model=OpenAIChat(id=model),
            instructions=["You are a helpful assistant. Be very brief."],
        )
        
        start = time.perf_counter()
        response = agent.run(prompt)
        elapsed = time.perf_counter() - start
        
        times.append(elapsed)
        # Extract content from response
        content = str(response.content)[:50] if hasattr(response, 'content') else str(response)[:50]
        print(f"  Run {i+1}: {elapsed:.2f}s - Response: {content}")
    
    avg = sum(times) / len(times)
    print(f"  Average: {avg:.2f}s")
    return avg


def benchmark_crewai(model, iterations, prompt):
    """Benchmark CrewAI agent execution using crew.kickoff()"""
    from crewai import Agent, Task, Crew
    
    print("\n--- CrewAI ---")
    print("Method: crew.kickoff()")
    
    times = []
    for i in range(iterations):
        agent = Agent(
            role="Calculator",
            goal="Answer math questions",
            backstory="You are a helpful assistant.",
            llm=model,
            verbose=False
        )
        
        task = Task(
            description=prompt,
            expected_output="A number",
            agent=agent
        )
        
        crew = Crew(
            agents=[agent],
            tasks=[task],
            verbose=False
        )
        
        start = time.perf_counter()
        response = crew.kickoff()
        elapsed = time.perf_counter() - start
        
        times.append(elapsed)
        print(f"  Run {i+1}: {elapsed:.2f}s - Response: {str(response)[:50]}")
    
    avg = sum(times) / len(times)
    print(f"  Average: {avg:.2f}s")
    return avg


def save_results(results: dict, model: str, iterations: int, prompt: str):
    """Save results to markdown file."""
    import os
    from datetime import datetime
    
    filepath = os.path.join(os.path.dirname(__file__), 'EXECUTION_BENCHMARK_RESULTS.md')
    versions = get_package_versions()
    
    # Sort by time
    sorted_results = sorted(results.items(), key=lambda x: x[1])
    fastest = sorted_results[0][1]
    
    with open(filepath, 'w') as f:
        f.write('# PraisonAI Agents - Real Execution Benchmark\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'**Model:** {model}\n')
        f.write(f'**Iterations:** {iterations}\n')
        f.write(f'**Prompt:** "{prompt}"\n\n')
        f.write('## Results\n\n')
        f.write('| Framework | Method | Avg Time | Relative |\n')
        f.write('|-----------|--------|----------|----------|\n')
        
        methods = {
            'PraisonAI': 'agent.start()',
            'PraisonAI (LiteLLM)': 'agent.start()',
            'Agno': 'agent.run()',
            'CrewAI': 'crew.kickoff()',
        }
        
        for name, avg in sorted_results:
            ratio = avg / fastest
            method = methods.get(name, 'unknown')
            if ratio == 1.0:
                f.write(f'| **{name}** | `{method}` | **{avg:.2f}s** | **1.00x (fastest)** |\n')
            else:
                f.write(f'| {name} | `{method}` | {avg:.2f}s | {ratio:.2f}x |\n')
        
        f.write('\n## Package Versions\n\n')
        f.write('| Package | Version |\n')
        f.write('|---------|--------|\n')
        for pkg, ver in versions.items():
            f.write(f'| {pkg} | {ver} |\n')
        
        f.write('\n## How to Reproduce\n\n')
        f.write('```bash\n')
        f.write('export OPENAI_API_KEY=your_key\n')
        f.write('cd praisonai-agents\n')
        f.write('python benchmarks/execution_benchmark.py\n')
        f.write('```\n')
    
    print(f'\nResults saved to: {filepath}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PraisonAI Agents - Real Execution Benchmark')
    parser.add_argument('--no-save', action='store_true', help='Do not save results to file')
    parser.add_argument('--model', '-m', type=str, default=DEFAULT_MODEL, help=f'Model to use (default: {DEFAULT_MODEL})')
    parser.add_argument('--iterations', '-i', type=int, default=DEFAULT_ITERATIONS, help=f'Number of iterations (default: {DEFAULT_ITERATIONS})')
    parser.add_argument('--prompt', '-p', type=str, default=DEFAULT_PROMPT, help=f'Prompt to use (default: "{DEFAULT_PROMPT}")')
    args = parser.parse_args()
    
    # Check API key
    if not os.environ.get('OPENAI_API_KEY'):
        print("ERROR: Set OPENAI_API_KEY environment variable")
        exit(1)
    
    model = args.model
    iterations = args.iterations
    prompt = args.prompt
    
    print('=' * 60)
    print('PraisonAI Agents - Real Execution Benchmark')
    print('=' * 60)
    print(f'\nModel: {model}')
    print(f'Iterations: {iterations}')
    print(f'Prompt: "{prompt}"')
    
    versions = get_package_versions()
    print('\nPackage versions:')
    for pkg, ver in versions.items():
        print(f'  {pkg}: {ver}')
    
    results = {}
    
    # Run benchmarks
    try:
        results['PraisonAI'] = benchmark_praisonai(model, iterations, prompt)
    except Exception as e:
        print(f"PraisonAI error: {e}")
    
    try:
        results['PraisonAI (LiteLLM)'] = benchmark_praisonai_litellm(model, iterations, prompt)
    except Exception as e:
        print(f"PraisonAI (LiteLLM) error: {e}")
    
    try:
        results['Agno'] = benchmark_agno(model, iterations, prompt)
    except Exception as e:
        print(f"Agno error: {e}")
    
    try:
        results['CrewAI'] = benchmark_crewai(model, iterations, prompt)
    except Exception as e:
        print(f"CrewAI error: {e}")
    
    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    
    if results:
        sorted_results = sorted(results.items(), key=lambda x: x[1])
        fastest = sorted_results[0][1]
        
        print(f"\n{'Framework':<25} {'Avg Time':<12} {'Relative':<10}")
        print('-' * 47)
        
        for name, avg in sorted_results:
            ratio = avg / fastest
            print(f'{name:<25} {avg:<12.2f}s {ratio:.2f}x')
    
    print('\n' + '=' * 60)
    
    # Save results (unless --no-save)
    if results and not args.no_save:
        save_results(results, model, iterations, prompt)
    elif args.no_save:
        print('\nResults not saved (--no-save flag used)')

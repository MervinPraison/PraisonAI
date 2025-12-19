#!/usr/bin/env python3
"""
PraisonAI CLI - Performance Benchmark

Measures import times and module loading performance.

Usage:
    python benchmarks/simple_benchmark.py
    python benchmarks/simple_benchmark.py --no-save
"""

import time
import sys
import os
import argparse
from datetime import datetime


ITERATIONS = 100


def measure_import(module_name: str) -> float:
    """Measure import time in milliseconds."""
    # Clear from cache if present
    modules_to_remove = [k for k in sys.modules.keys() if k.startswith(module_name)]
    for mod in modules_to_remove:
        del sys.modules[mod]
    
    start = time.perf_counter()
    __import__(module_name)
    return (time.perf_counter() - start) * 1000


def measure_instantiation(create_fn, iterations=ITERATIONS) -> float:
    """Measure average instantiation time in microseconds."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        create_fn()
        times.append((time.perf_counter() - start) * 1_000_000)
    return sum(times) / len(times)


def run_benchmark():
    """Run the benchmark."""
    results = {}
    
    print('=' * 60)
    print('PraisonAI CLI - Performance Benchmark')
    print('=' * 60)
    print(f'\nIterations: {ITERATIONS}')
    print('Metrics: Import time (ms), Instantiation time (μs)\n')
    
    # 1. Package import time
    print("1. Testing package imports...")
    
    # Clear cache
    modules_to_remove = [k for k in sys.modules.keys() if 'praisonai' in k]
    for mod in modules_to_remove:
        del sys.modules[mod]
    
    start = time.perf_counter()
    import praisonai
    results['praisonai_import_ms'] = (time.perf_counter() - start) * 1000
    print(f"   import praisonai: {results['praisonai_import_ms']:.2f}ms")
    
    # 2. CLI features import
    print("\n2. Testing CLI features imports...")
    
    start = time.perf_counter()
    from praisonai.cli.features.message_queue import MessageQueue
    results['message_queue_import_ms'] = (time.perf_counter() - start) * 1000
    print(f"   message_queue: {results['message_queue_import_ms']:.2f}ms")
    
    start = time.perf_counter()
    from praisonai.cli.features.at_mentions import CombinedCompleter
    results['at_mentions_import_ms'] = (time.perf_counter() - start) * 1000
    print(f"   at_mentions: {results['at_mentions_import_ms']:.2f}ms")
    
    # 3. Profiler import (should be fast, standalone)
    print("\n3. Testing profiler import...")
    start = time.perf_counter()
    from praisonai.profiler import Profiler
    results['profiler_import_ms'] = (time.perf_counter() - start) * 1000
    print(f"   profiler: {results['profiler_import_ms']:.2f}ms")
    
    # 4. Instantiation benchmarks
    print(f"\n4. Testing instantiation ({ITERATIONS} iterations)...")
    
    from praisonai.cli.features.message_queue import MessageQueue, StateManager
    from praisonai.cli.features.at_mentions import FileSearchService
    
    results['MessageQueue_us'] = measure_instantiation(lambda: MessageQueue())
    print(f"   MessageQueue: {results['MessageQueue_us']:.2f}μs")
    
    results['StateManager_us'] = measure_instantiation(lambda: StateManager())
    print(f"   StateManager: {results['StateManager_us']:.2f}μs")
    
    results['FileSearchService_us'] = measure_instantiation(
        lambda: FileSearchService(root_dir=".")
    )
    print(f"   FileSearchService: {results['FileSearchService_us']:.2f}μs")
    
    # 5. PraisonAI class (lazy load)
    print("\n5. Testing PraisonAI class access (lazy load)...")
    start = time.perf_counter()
    PraisonAI = praisonai.PraisonAI
    results['PraisonAI_lazy_ms'] = (time.perf_counter() - start) * 1000
    print(f"   PraisonAI lazy load: {results['PraisonAI_lazy_ms']:.2f}ms")
    
    return results


def print_summary(results: dict):
    """Print benchmark summary."""
    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    
    print('\nImport Times (target: <50ms for features, <10ms for package):')
    print(f"  {'Module':<25} {'Time':>10} {'Status':>10}")
    print(f"  {'-'*25} {'-'*10} {'-'*10}")
    
    import_checks = [
        ('praisonai', results['praisonai_import_ms'], 10),
        ('message_queue', results['message_queue_import_ms'], 50),
        ('at_mentions', results['at_mentions_import_ms'], 50),
        ('profiler', results['profiler_import_ms'], 10),
    ]
    
    all_pass = True
    for name, time_ms, threshold in import_checks:
        status = '✅ PASS' if time_ms < threshold else '❌ SLOW'
        if time_ms >= threshold:
            all_pass = False
        print(f"  {name:<25} {time_ms:>8.2f}ms {status:>10}")
    
    print('\nInstantiation Times (target: <100μs):')
    print(f"  {'Class':<25} {'Time':>10} {'Status':>10}")
    print(f"  {'-'*25} {'-'*10} {'-'*10}")
    
    inst_checks = [
        ('MessageQueue', results['MessageQueue_us'], 100),
        ('StateManager', results['StateManager_us'], 100),
        ('FileSearchService', results['FileSearchService_us'], 100),
    ]
    
    for name, time_us, threshold in inst_checks:
        status = '✅ PASS' if time_us < threshold else '❌ SLOW'
        if time_us >= threshold:
            all_pass = False
        print(f"  {name:<25} {time_us:>8.2f}μs {status:>10}")
    
    print('\n' + '=' * 60)
    if all_pass:
        print('✅ All benchmarks PASSED')
    else:
        print('❌ Some benchmarks FAILED')
    print('=' * 60)
    
    return all_pass


def save_results(results: dict):
    """Save benchmark results to markdown file."""
    filepath = os.path.join(os.path.dirname(__file__), 'BENCHMARK_RESULTS.md')
    
    with open(filepath, 'w') as f:
        f.write('# PraisonAI CLI - Benchmark Results\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n')
        
        f.write('## Import Times\n\n')
        f.write('| Module | Time (ms) | Target | Status |\n')
        f.write('|--------|-----------|--------|--------|\n')
        
        import_data = [
            ('praisonai', results['praisonai_import_ms'], 10),
            ('message_queue', results['message_queue_import_ms'], 50),
            ('at_mentions', results['at_mentions_import_ms'], 50),
            ('profiler', results['profiler_import_ms'], 10),
        ]
        
        for name, time_ms, threshold in import_data:
            status = '✅' if time_ms < threshold else '❌'
            f.write(f'| {name} | {time_ms:.2f} | <{threshold} | {status} |\n')
        
        f.write('\n## Instantiation Times\n\n')
        f.write('| Class | Time (μs) | Target | Status |\n')
        f.write('|-------|-----------|--------|--------|\n')
        
        inst_data = [
            ('MessageQueue', results['MessageQueue_us'], 100),
            ('StateManager', results['StateManager_us'], 100),
            ('FileSearchService', results['FileSearchService_us'], 100),
        ]
        
        for name, time_us, threshold in inst_data:
            status = '✅' if time_us < threshold else '❌'
            f.write(f'| {name} | {time_us:.2f} | <{threshold} | {status} |\n')
        
        f.write('\n## Lazy Loading\n\n')
        f.write(f'| Operation | Time (ms) |\n')
        f.write(f'|-----------|----------|\n')
        f.write(f'| PraisonAI lazy load | {results["PraisonAI_lazy_ms"]:.2f} |\n')
        
        f.write('\n## How to Reproduce\n\n')
        f.write('```bash\n')
        f.write('cd praisonai\n')
        f.write('python benchmarks/simple_benchmark.py\n')
        f.write('```\n')
    
    print(f'\nResults saved to: {filepath}')
    return filepath


def main():
    parser = argparse.ArgumentParser(description='PraisonAI CLI Performance Benchmark')
    parser.add_argument('--no-save', action='store_true', help='Do not save results to file')
    args = parser.parse_args()
    
    results = run_benchmark()
    all_pass = print_summary(results)
    
    if not args.no_save:
        save_results(results)
    
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())

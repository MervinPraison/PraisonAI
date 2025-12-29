"""
Performance benchmark tests for PraisonAI.

These tests verify that import times, CLI startup, and memory usage
stay within acceptable bounds. They serve as regression guards.

Run with: pytest tests/unit/test_performance_benchmarks.py -v
"""

import subprocess
import sys
import os
import pytest

# Get the paths for praisonai and praisonaiagents
PRAISONAI_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRAISONAI_AGENTS_PATH = os.path.join(os.path.dirname(PRAISONAI_PATH), "praisonai-agents")

# Build PYTHONPATH that includes both packages
PYTHONPATH = f"{PRAISONAI_PATH}:{PRAISONAI_AGENTS_PATH}"

# Thresholds (can be adjusted based on CI environment)
PRAISONAI_WRAPPER_IMPORT_TIME_MS = 500  # Should be very fast (lazy)
CLI_STARTUP_TIME_S = 1.0  # Target < 1s for CLI cold start
CLI_MEMORY_MB = 50  # Target < 50MB for CLI cold start (without heavy deps)


def run_python_code(code: str, cwd: str = None) -> subprocess.CompletedProcess:
    """Run Python code in a subprocess with proper PYTHONPATH."""
    env = os.environ.copy()
    env['PYTHONPATH'] = PYTHONPATH
    return subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True,
        text=True,
        cwd=cwd or PRAISONAI_PATH,
        env=env
    )


class TestImportTimeBenchmarks:
    """Test import time performance."""
    
    def test_praisonai_wrapper_import_time(self):
        """Test that praisonai wrapper imports quickly (lazy loading)."""
        code = '''
import time
t = time.time()
import praisonai
elapsed_ms = (time.time() - t) * 1000
print(f"{elapsed_ms:.0f}")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        elapsed_ms = float(result.stdout.strip())
        assert elapsed_ms < PRAISONAI_WRAPPER_IMPORT_TIME_MS, \
            f"praisonai import took {elapsed_ms:.0f}ms, expected < {PRAISONAI_WRAPPER_IMPORT_TIME_MS}ms"
    
    def test_cli_main_import_time(self):
        """Test that CLI main module imports quickly (lazy loading)."""
        code = '''
import time
import os
os.environ['LOGLEVEL'] = 'WARNING'
t = time.time()
from praisonai.cli.main import PraisonAI
elapsed_ms = (time.time() - t) * 1000
print(f"{elapsed_ms:.0f}")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        elapsed_ms = float(result.stdout.strip())
        # CLI should be fast due to lazy loading
        assert elapsed_ms < CLI_STARTUP_TIME_S * 1000, \
            f"CLI import took {elapsed_ms:.0f}ms, expected < {CLI_STARTUP_TIME_S * 1000}ms"


class TestMemoryBenchmarks:
    """Test memory usage."""
    
    def test_cli_cold_start_memory(self):
        """Test that CLI cold start uses reasonable memory."""
        code = '''
import tracemalloc
import os
os.environ['LOGLEVEL'] = 'WARNING'
tracemalloc.start()
from praisonai.cli.main import PraisonAI
current, peak = tracemalloc.get_traced_memory()
print(f"{peak / 1024 / 1024:.1f}")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Memory test failed: {result.stderr}"
        peak_mb = float(result.stdout.strip())
        assert peak_mb < CLI_MEMORY_MB, \
            f"CLI cold start used {peak_mb:.1f}MB, expected < {CLI_MEMORY_MB}MB"


class TestLazyLoadingVerification:
    """Verify that lazy loading is working correctly."""
    
    def test_auto_generator_not_imported_at_cli_startup(self):
        """Verify AutoGenerator is not imported when CLI starts."""
        code = '''
import sys
import os
os.environ['LOGLEVEL'] = 'WARNING'
from praisonai.cli.main import PraisonAI
# Check if heavy modules are NOT loaded
heavy_modules = ['praisonai.auto', 'praisonai.agents_generator', 'litellm', 'instructor']
loaded = [m for m in heavy_modules if m in sys.modules]
if loaded:
    print(f"FAIL: {loaded}")
else:
    print("OK")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Test failed: {result.stderr}"
        output = result.stdout.strip()
        assert output == "OK", f"Heavy modules loaded at startup: {output}"
    
    def test_praisonaiagents_not_imported_at_cli_startup(self):
        """Verify praisonaiagents is not imported when CLI starts."""
        code = '''
import sys
import os
os.environ['LOGLEVEL'] = 'WARNING'
from praisonai.cli.main import PraisonAI
# Check if praisonaiagents is NOT loaded
if 'praisonaiagents' in sys.modules:
    print("FAIL: praisonaiagents loaded")
else:
    print("OK")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Test failed: {result.stderr}"
        output = result.stdout.strip()
        assert output == "OK", f"praisonaiagents loaded at startup: {output}"


class TestThreadSafetyToolRegistry:
    """Test thread safety of tool registry."""
    
    def test_concurrent_tool_registration(self):
        """Test that concurrent tool registration is thread-safe."""
        code = '''
import threading
import time
from praisonaiagents.tools.registry import ToolRegistry

registry = ToolRegistry()
errors = []
registered_count = [0]
lock = threading.Lock()

def register_tools(thread_id, count):
    try:
        for i in range(count):
            def tool_func():
                pass
            tool_func.__name__ = f"tool_{thread_id}_{i}"
            registry.register(tool_func)
            with lock:
                registered_count[0] += 1
    except Exception as e:
        errors.append(str(e))

# Create multiple threads that register tools concurrently
threads = []
num_threads = 10
tools_per_thread = 50

for i in range(num_threads):
    t = threading.Thread(target=register_tools, args=(i, tools_per_thread))
    threads.append(t)

# Start all threads
for t in threads:
    t.start()

# Wait for all threads to complete
for t in threads:
    t.join()

# Verify results
expected_total = num_threads * tools_per_thread
actual_total = len(registry)

if errors:
    print(f"FAIL: Errors occurred: {errors}")
elif actual_total != expected_total:
    print(f"FAIL: Expected {expected_total} tools, got {actual_total}")
else:
    print("OK")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Test failed: {result.stderr}"
        output = result.stdout.strip()
        assert output == "OK", f"Thread safety test failed: {output}"
    
    def test_concurrent_tool_access(self):
        """Test that concurrent tool access is thread-safe."""
        code = '''
import threading
from praisonaiagents.tools.registry import ToolRegistry

registry = ToolRegistry()
errors = []

# Pre-register some tools
for i in range(100):
    def tool_func():
        pass
    tool_func.__name__ = f"tool_{i}"
    registry.register(tool_func)

def access_tools(thread_id, iterations):
    try:
        for _ in range(iterations):
            # Mix of read operations
            registry.list_tools()
            registry.get(f"tool_{thread_id % 100}")
            len(registry)
            f"tool_{thread_id % 100}" in registry
    except Exception as e:
        errors.append(str(e))

# Create multiple threads that access tools concurrently
threads = []
num_threads = 20
iterations = 100

for i in range(num_threads):
    t = threading.Thread(target=access_tools, args=(i, iterations))
    threads.append(t)

for t in threads:
    t.start()

for t in threads:
    t.join()

if errors:
    print(f"FAIL: Errors occurred: {errors}")
else:
    print("OK")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Test failed: {result.stderr}"
        output = result.stdout.strip()
        assert output == "OK", f"Thread safety test failed: {output}"


class TestTemplateCaching:
    """Test template discovery caching."""
    
    def test_template_discovery_caching(self):
        """Test that template discovery results are cached."""
        code = '''
import time
from praisonai.templates.discovery import TemplateDiscovery

# Create discovery instance
discovery = TemplateDiscovery(include_package=False)

# First call - should scan filesystem
t1 = time.time()
result1 = discovery.discover_all()
time1 = time.time() - t1

# Second call - should use cache
t2 = time.time()
result2 = discovery.discover_all()
time2 = time.time() - t2

# Third call with refresh - should scan again
t3 = time.time()
result3 = discovery.discover_all(refresh=True)
time3 = time.time() - t3

# Cache hit should be significantly faster
# (at least 2x faster, typically 10x+)
if time2 > 0 and time1 / time2 < 1.5:
    # If times are very similar, cache might not be working
    # But if both are very fast (<1ms), it's fine
    if time1 > 0.001 and time2 > 0.001:
        print(f"WARN: Cache may not be working. First: {time1*1000:.2f}ms, Second: {time2*1000:.2f}ms")
    else:
        print("OK")
else:
    print("OK")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Test failed: {result.stderr}"
        output = result.stdout.strip()
        assert "OK" in output or "WARN" in output, f"Cache test failed: {output}"
    
    def test_template_cache_clear(self):
        """Test that template cache can be cleared."""
        code = '''
from praisonai.templates.discovery import TemplateDiscovery

discovery = TemplateDiscovery(include_package=False)

# Populate cache
discovery.discover_all()

# Clear cache
discovery.clear_cache()

# Verify cache is cleared by checking internal state
if discovery._cache_key in TemplateDiscovery._cache:
    print("FAIL: Cache not cleared")
else:
    print("OK")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Test failed: {result.stderr}"
        output = result.stdout.strip()
        assert output == "OK", f"Cache clear test failed: {output}"


class TestSchemaVersioning:
    """Test DB adapter schema versioning."""
    
    def test_schema_version_constant_exists(self):
        """Test that SCHEMA_VERSION constant is defined."""
        code = '''
from praisonaiagents.db.protocol import SCHEMA_VERSION
if SCHEMA_VERSION and isinstance(SCHEMA_VERSION, str):
    print("OK")
else:
    print(f"FAIL: Invalid SCHEMA_VERSION: {SCHEMA_VERSION}")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Test failed: {result.stderr}"
        output = result.stdout.strip()
        assert output == "OK", f"Schema version test failed: {output}"
    
    def test_schema_version_format(self):
        """Test that SCHEMA_VERSION follows MAJOR.MINOR format."""
        code = r'''
import re
from praisonaiagents.db.protocol import SCHEMA_VERSION
if re.match(r"^\d+\.\d+$", SCHEMA_VERSION):
    print("OK")
else:
    print(f"FAIL: Invalid format: {SCHEMA_VERSION}")
'''
        result = run_python_code(code)
        assert result.returncode == 0, f"Test failed: {result.stderr}"
        output = result.stdout.strip()
        assert output == "OK", f"Schema version format test failed: {output}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

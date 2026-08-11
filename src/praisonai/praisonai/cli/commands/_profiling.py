"""
Shared profiler context manager for PraisonAI CLI command groups.

Provides a single implementation of the ``--profile`` behaviour used by the
``rag`` and ``knowledge`` commands so profiling logic has one owner and cannot
drift between commands.
"""

from typing import Optional
from pathlib import Path
from contextlib import contextmanager
import time
import json as json_module


@contextmanager
def command_profiler(command_name: str, enabled: bool, profile_out: Optional[Path], profile_top: int = 20):
    """
    Context manager for CLI command profiling.

    Uses the existing praisonai.profiler infrastructure when available,
    falls back to basic timing if not.
    """
    if not enabled:
        yield None
        return

    import sys
    start_time = time.perf_counter()
    start_modules = set(sys.modules.keys())

    # Try to use the full profiler
    profiler = None
    try:
        from praisonai.profiler import Profiler
        Profiler.enable()
        Profiler.clear()
        profiler = Profiler
    except ImportError:
        pass

    # Try tracemalloc for memory
    try:
        import tracemalloc
        tracemalloc.start()
    except Exception:
        tracemalloc = None

    profile_data = {
        "command": command_name,
        "start_time": time.time(),
        "metrics": {},
        "imports": [],
        "top_functions": [],
    }

    try:
        yield profile_data
    finally:
        end_time = time.perf_counter()
        elapsed_ms = (end_time - start_time) * 1000

        # Collect metrics
        profile_data["metrics"]["wall_time_ms"] = elapsed_ms
        profile_data["metrics"]["wall_time_s"] = elapsed_ms / 1000

        # Memory usage
        if tracemalloc:
            try:
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                profile_data["metrics"]["peak_memory_mb"] = peak / (1024 * 1024)
                profile_data["metrics"]["current_memory_mb"] = current / (1024 * 1024)
            except Exception:
                pass

        # New imports during execution
        end_modules = set(sys.modules.keys())
        new_modules = end_modules - start_modules
        profile_data["imports"] = sorted(list(new_modules))[:profile_top]
        profile_data["metrics"]["modules_imported"] = len(new_modules)

        # Get profiler data if available
        if profiler:
            try:
                profiler.disable()
                stats = profiler.get_statistics()
                if stats:
                    profile_data["top_functions"] = stats.get("top_functions", [])[:profile_top]
                    profile_data["metrics"].update(stats.get("summary", {}))
            except Exception:
                pass

        # Save to file if requested
        if profile_out:
            try:
                profile_out.parent.mkdir(parents=True, exist_ok=True)
                with open(profile_out, "w") as f:
                    json_module.dump(profile_data, f, indent=2, default=str)
            except Exception as e:
                print(f"Warning: Failed to save profile: {e}")

        # Print summary
        from rich.console import Console
        console = Console(stderr=True)
        console.print(f"\n[dim]Profile: {elapsed_ms:.2f}ms wall time[/dim]")
        if "peak_memory_mb" in profile_data["metrics"]:
            console.print(f"[dim]Profile: {profile_data['metrics']['peak_memory_mb']:.2f}MB peak memory[/dim]")
        console.print(f"[dim]Profile: {len(new_modules)} modules imported[/dim]")
        if profile_out:
            console.print(f"[dim]Profile saved to: {profile_out}[/dim]")

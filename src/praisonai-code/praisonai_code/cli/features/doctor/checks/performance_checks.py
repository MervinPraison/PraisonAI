"""
Performance checks for the Doctor CLI module.

Measures import times and identifies slow imports.
"""

import sys
import time

from ..models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    CheckSeverity,
    DoctorConfig,
)
from ..registry import register_check


def _measure_import_time(module_name: str) -> tuple:
    """Measure import time for a module."""
    # Remove from cache if present
    modules_before = set(sys.modules.keys())
    
    start = time.perf_counter()
    try:
        __import__(module_name)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        return True, elapsed, None
    except ImportError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return False, elapsed, str(e)
    finally:
        # Clean up imported modules (optional, for accurate re-measurement)
        pass


@register_check(
    id="performance_praisonai_import",
    title="PraisonAI Import Time",
    description="Measure praisonai package import time",
    category=CheckCategory.PERFORMANCE,
    severity=CheckSeverity.INFO,
)
def check_performance_praisonai_import(config: DoctorConfig) -> CheckResult:
    """Measure praisonai package import time."""
    budget_ms = config.budget_ms or 2000  # 2 second default budget
    
    # praisonai is already imported, measure a fresh import of a submodule
    start = time.perf_counter()
    try:
        # Import version module (lightweight)
        from praisonai import version
        elapsed = (time.perf_counter() - start) * 1000
        
        if elapsed > budget_ms:
            return CheckResult(
                id="performance_praisonai_import",
                title="PraisonAI Import Time",
                category=CheckCategory.PERFORMANCE,
                status=CheckStatus.WARN,
                message=f"Import time {elapsed:.0f}ms exceeds budget {budget_ms}ms",
                remediation="Check for slow dependencies or disk I/O issues",
            )
        else:
            return CheckResult(
                id="performance_praisonai_import",
                title="PraisonAI Import Time",
                category=CheckCategory.PERFORMANCE,
                status=CheckStatus.PASS,
                message=f"Import time: {elapsed:.0f}ms (budget: {budget_ms}ms)",
                metadata={"import_time_ms": elapsed, "budget_ms": budget_ms},
            )
    except ImportError as e:
        return CheckResult(
            id="performance_praisonai_import",
            title="PraisonAI Import Time",
            category=CheckCategory.PERFORMANCE,
            status=CheckStatus.FAIL,
            message=f"Import failed: {e}",
        )


@register_check(
    id="performance_praisonaiagents_import",
    title="PraisonAI Agents Import Time",
    description="Measure praisonaiagents package import time",
    category=CheckCategory.PERFORMANCE,
    severity=CheckSeverity.INFO,
)
def check_performance_praisonaiagents_import(config: DoctorConfig) -> CheckResult:
    """Measure praisonaiagents package import time."""
    budget_ms = config.budget_ms or 3000  # 3 second default budget
    
    start = time.perf_counter()
    try:
        import praisonaiagents
        elapsed = (time.perf_counter() - start) * 1000
        
        if elapsed > budget_ms:
            return CheckResult(
                id="performance_praisonaiagents_import",
                title="PraisonAI Agents Import Time",
                category=CheckCategory.PERFORMANCE,
                status=CheckStatus.WARN,
                message=f"Import time {elapsed:.0f}ms exceeds budget {budget_ms}ms",
                remediation="Check for slow dependencies",
            )
        else:
            return CheckResult(
                id="performance_praisonaiagents_import",
                title="PraisonAI Agents Import Time",
                category=CheckCategory.PERFORMANCE,
                status=CheckStatus.PASS,
                message=f"Import time: {elapsed:.0f}ms (budget: {budget_ms}ms)",
                metadata={"import_time_ms": elapsed, "budget_ms": budget_ms},
            )
    except ImportError as e:
        return CheckResult(
            id="performance_praisonaiagents_import",
            title="PraisonAI Agents Import Time",
            category=CheckCategory.PERFORMANCE,
            status=CheckStatus.FAIL,
            message=f"Import failed: {e}",
        )


@register_check(
    id="performance_slow_imports",
    title="Slow Import Detection",
    description="Detect slow-loading optional dependencies",
    category=CheckCategory.PERFORMANCE,
    severity=CheckSeverity.INFO,
    requires_deep=True,
)
def check_performance_slow_imports(config: DoctorConfig) -> CheckResult:
    """Detect slow-loading optional dependencies."""
    modules_to_check = [
        "litellm",
        "chromadb",
        "langchain",
        "torch",
        "transformers",
        "pandas",
        "numpy",
    ]
    
    top_n = config.top_n or 5
    budget_ms = config.budget_ms or 1000
    
    import_times = []
    
    for module in modules_to_check:
        if module in sys.modules:
            # Already imported, skip
            continue
        
        success, elapsed, error = _measure_import_time(module)
        if success:
            import_times.append((module, elapsed))
    
    # Sort by time, descending
    import_times.sort(key=lambda x: x[1], reverse=True)
    
    slow_imports = [(m, t) for m, t in import_times if t > budget_ms]
    top_imports = import_times[:top_n]
    
    if slow_imports:
        slow_str = ", ".join(f"{m}({t:.0f}ms)" for m, t in slow_imports[:3])
        return CheckResult(
            id="performance_slow_imports",
            title="Slow Import Detection",
            category=CheckCategory.PERFORMANCE,
            status=CheckStatus.WARN,
            message=f"{len(slow_imports)} slow import(s) detected",
            details=f"Slow: {slow_str}",
            metadata={"slow_imports": slow_imports, "top_imports": top_imports},
        )
    elif top_imports:
        top_str = ", ".join(f"{m}({t:.0f}ms)" for m, t in top_imports[:3])
        return CheckResult(
            id="performance_slow_imports",
            title="Slow Import Detection",
            category=CheckCategory.PERFORMANCE,
            status=CheckStatus.PASS,
            message=f"No slow imports (top: {top_str})",
            metadata={"top_imports": top_imports},
        )
    else:
        return CheckResult(
            id="performance_slow_imports",
            title="Slow Import Detection",
            category=CheckCategory.PERFORMANCE,
            status=CheckStatus.SKIP,
            message="No optional modules to measure",
        )


@register_check(
    id="performance_loaded_modules",
    title="Loaded Modules Count",
    description="Count currently loaded Python modules",
    category=CheckCategory.PERFORMANCE,
    severity=CheckSeverity.INFO,
)
def check_performance_loaded_modules(config: DoctorConfig) -> CheckResult:
    """Count currently loaded Python modules."""
    module_count = len(sys.modules)
    
    # Categorize modules
    stdlib_count = 0
    third_party_count = 0
    praison_count = 0
    
    for name in sys.modules:
        if name.startswith("praisonai"):
            praison_count += 1
        elif "site-packages" in str(getattr(sys.modules[name], "__file__", "")):
            third_party_count += 1
        else:
            stdlib_count += 1
    
    return CheckResult(
        id="performance_loaded_modules",
        title="Loaded Modules Count",
        category=CheckCategory.PERFORMANCE,
        status=CheckStatus.PASS,
        message=f"{module_count} modules loaded (praison: {praison_count})",
        metadata={
            "total": module_count,
            "praison": praison_count,
            "third_party": third_party_count,
            "stdlib": stdlib_count,
        },
    )

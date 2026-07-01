"""
Queue System for PraisonAI TUI.

Provides multi-run, multi-agent queueing with priorities, cancel/retry,
streaming output, and persistence.

Lazy-loaded to avoid import overhead when not used.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import QueuedRun, RunState, RunPriority, QueueConfig
    from .scheduler import QueueScheduler
    from .worker import WorkerPool
    from .persistence import QueuePersistence

_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load queue components."""
    global _lazy_cache
    
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "QueuedRun":
        from .models import QueuedRun
        _lazy_cache[name] = QueuedRun
        return QueuedRun
    elif name == "RunState":
        from .models import RunState
        _lazy_cache[name] = RunState
        return RunState
    elif name == "RunPriority":
        from .models import RunPriority
        _lazy_cache[name] = RunPriority
        return RunPriority
    elif name == "QueueConfig":
        from .models import QueueConfig
        _lazy_cache[name] = QueueConfig
        return QueueConfig
    elif name == "QueueScheduler":
        from .scheduler import QueueScheduler
        _lazy_cache[name] = QueueScheduler
        return QueueScheduler
    elif name == "WorkerPool":
        from .worker import WorkerPool
        _lazy_cache[name] = WorkerPool
        return WorkerPool
    elif name == "QueuePersistence":
        from .persistence import QueuePersistence
        _lazy_cache[name] = QueuePersistence
        return QueuePersistence
    elif name == "QueueManager":
        from .manager import QueueManager
        _lazy_cache[name] = QueueManager
        return QueueManager
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "QueuedRun",
    "RunState", 
    "RunPriority",
    "QueueConfig",
    "QueueScheduler",
    "WorkerPool",
    "QueuePersistence",
    "QueueManager",
]

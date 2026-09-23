"""
Background Agents Module for PraisonAI Agents.

Provides the ability to run agents in the background, allowing:
- Long-running tasks without blocking
- Task queuing and management
- Progress monitoring and notifications
- Graceful cancellation

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Background processing only when explicitly started
- No overhead when not in use

Usage:
    from praisonaiagents.background import BackgroundRunner, BackgroundTask
    
    # Create a background runner
    runner = BackgroundRunner()
    
    # Submit a task
    task = runner.submit(
        agent=my_agent,
        prompt="Research AI trends",
        callback=on_complete
    )
    
    # Check status
    print(task.status)  # "running", "completed", "failed"
    
    # Wait for completion
    result = await task.wait()
"""

from .._lazy import create_lazy_getattr

__all__ = [
    # Core classes
    "BackgroundRunner",
    "BackgroundTask",
    # Status enum
    "TaskStatus",
    # Configuration
    "BackgroundConfig",
    # Shared runner accessor
    "get_background_runner",
    # Durable background job store
    "SqliteBackgroundJobStore",
]


_LAZY_IMPORTS = {
    "BackgroundRunner": ("praisonaiagents.background.runner", "BackgroundRunner"),
    "BackgroundTask": ("praisonaiagents.background.task", "BackgroundTask"),
    "TaskStatus": ("praisonaiagents.background.task", "TaskStatus"),
    "BackgroundConfig": ("praisonaiagents.background.config", "BackgroundConfig"),
    "get_background_runner": ("praisonaiagents.background.runner", "get_background_runner"),
    "SqliteBackgroundJobStore": ("praisonaiagents.background.sqlite_store", "SqliteBackgroundJobStore"),
}

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)

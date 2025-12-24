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

__all__ = [
    # Core classes
    "BackgroundRunner",
    "BackgroundTask",
    # Status enum
    "TaskStatus",
    # Configuration
    "BackgroundConfig",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name == "BackgroundRunner":
        from .runner import BackgroundRunner
        return BackgroundRunner
    
    if name == "BackgroundTask":
        from .task import BackgroundTask
        return BackgroundTask
    
    if name == "TaskStatus":
        from .task import TaskStatus
        return TaskStatus
    
    if name == "BackgroundConfig":
        from .config import BackgroundConfig
        return BackgroundConfig
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

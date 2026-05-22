"""Wire kanban store and jobs components for PraisonAIUI integration."""

from __future__ import annotations

from typing import Any, Optional


def get_kanban_store_factory():
    """Return kanban store factory for PraisonAIUI injection."""
    try:
        from praisonai.kanban.sqlite_store import SQLiteKanbanStore
        
        def _kanban_store_factory():
            """Create SQLite kanban store instance."""
            # Reads PRAISONAI_KANBAN_BOARD env var for board selection
            return SQLiteKanbanStore()
        
        return _kanban_store_factory
    except ImportError:
        return None


def get_jobs_store():
    """Return jobs store for PraisonAIUI injection."""
    try:
        from praisonai.jobs.store import get_store
        return get_store
    except ImportError:
        return None


def get_jobs_executor():
    """Return jobs executor for PraisonAIUI injection."""
    try:
        from praisonai.jobs.executor import get_executor
        return get_executor
    except ImportError:
        return None


def register_kanban_backends():
    """Register kanban-related backends with PraisonAIUI."""
    import logging
    
    log = logging.getLogger(__name__)
    
    try:
        import praisonaiui.backends as backends
        
        # Kanban store factory
        kanban_factory = get_kanban_store_factory()
        if kanban_factory is not None:
            backends.set_backend("kanban_store", kanban_factory)
            log.debug("kanban_store backend registered")
        
        # Jobs store
        jobs_store = get_jobs_store()
        if jobs_store is not None:
            backends.set_backend("jobs_store", jobs_store)
            log.debug("jobs_store backend registered")
        
        # Jobs executor
        jobs_executor = get_jobs_executor()
        if jobs_executor is not None:
            backends.set_backend("jobs_executor", jobs_executor)
            log.debug("jobs_executor backend registered")
        
        # Start kanban dispatcher
        ensure_kanban_dispatcher()
            
        return True
        
    except Exception as exc:
        log.debug("kanban backend registration failed: %s", exc)
        return False


def ensure_kanban_dispatcher():
    """Ensure kanban dispatcher is running in background."""
    import asyncio
    import logging
    
    log = logging.getLogger(__name__)
    
    try:
        from praisonai.gateway.kanban_dispatcher import start_kanban_dispatcher, is_dispatcher_running
        
        if not is_dispatcher_running():
            # Start dispatcher in background
            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop in this thread, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop and loop.is_running():
                # Loop is running, schedule the task
                asyncio.create_task(start_kanban_dispatcher())
                log.debug("kanban dispatcher scheduled to start")
            else:
                # No loop or loop not running, we can't start dispatcher here
                # This is expected in CLI/sync contexts
                log.debug("kanban dispatcher cannot start (no async context)")
        
    except Exception as exc:
        log.debug("kanban dispatcher startup failed: %s", exc)
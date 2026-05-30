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
        
        # Register kanban dispatcher startup handler
        register_kanban_startup_handler()
            
        return True
        
    except Exception as exc:
        log.debug("kanban backend registration failed: %s", exc)
        return False


def register_kanban_startup_handler():
    """Register kanban dispatcher startup handler with the ASGI app."""
    import logging
    
    log = logging.getLogger(__name__)
    
    try:
        import praisonaiui.backends as backends
        from praisonai.gateway.kanban_dispatcher import start_kanban_dispatcher, is_dispatcher_running
        
        async def _startup_handler():
            """Startup handler for kanban dispatcher."""
            try:
                if not is_dispatcher_running():
                    await start_kanban_dispatcher()
                    log.info("kanban dispatcher started")
            except Exception as exc:
                log.warning("failed to start kanban dispatcher: %s", exc)
        
        # Register startup handler if the backend supports it
        if hasattr(backends, 'register_startup_handler'):
            backends.register_startup_handler(_startup_handler)
            log.debug("kanban dispatcher startup handler registered")
        else:
            # Fallback: try immediate start if event loop is running
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                if loop and not is_dispatcher_running():
                    asyncio.create_task(start_kanban_dispatcher())
                    log.debug("kanban dispatcher started via task")
            except RuntimeError:
                log.debug("kanban dispatcher deferred (no running event loop)")
                
    except Exception as exc:
        log.debug("kanban startup handler registration failed: %s", exc)
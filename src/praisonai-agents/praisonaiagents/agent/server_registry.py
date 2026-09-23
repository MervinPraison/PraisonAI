"""
Shared HTTP server registry for launch() paths.

Both ``Agent.launch()`` (single-agent) and ``PraisonAIAgents.launch()``
(multi-agent) let multiple ``launch()`` calls share one FastAPI app / uvicorn
server per port. They MUST consult the *same* process-wide registry so a
standalone agent and a team launched on the same port see each other's state:
one "is this port started?" check, one FastAPI app, one set of routes. Keeping
two independent registries caused duplicate binds (``Address already in use``)
and routes registered through one launcher being invisible on the other's app.
"""

import os
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class _AgentServerRegistry:
    """Encapsulates all shared HTTP server state with proper synchronization."""

    def __init__(self):
        self._lock = threading.Lock()
        self._started: Dict[int, bool] = {}
        self._endpoints: Dict[int, Dict[str, str]] = {}
        self._apps: Dict[int, Any] = {}  # FastAPI apps
        self._ready_events: Dict[int, threading.Event] = {}

    def get_or_create_app(self, port: int, title: str = "AgentTeam API") -> Tuple[Any, bool]:
        """Thread-safe app creation. Returns (app, is_new)."""
        with self._lock:
            if port not in self._apps:
                # Lazy import to avoid optional dependency at module level
                from fastapi import FastAPI
                self._apps[port] = FastAPI(title=title)
                self._endpoints[port] = {}
                self._ready_events[port] = threading.Event()
                return self._apps[port], True
            return self._apps[port], False

    def register_route(self, port: int, path: str, endpoint_id: str = "registered") -> None:
        """Thread-safe route registration tracking."""
        with self._lock:
            if port not in self._endpoints:
                self._endpoints[port] = {}
            self._endpoints[port][path] = endpoint_id

    def reserve_route(self, port: int, path: str, endpoint_id: str) -> Tuple[str, Optional[str]]:
        """Atomically reserve and register a route.

        Returns:
            tuple[str, Optional[str]]: (final_path, original_path_if_collided).
            If there is no collision, final_path equals the requested path and
            original_path_if_collided is None.
        """
        with self._lock:
            if port not in self._endpoints:
                self._endpoints[port] = {}

            original_path = path
            while path in self._endpoints[port]:
                path = f"{original_path}_{str(uuid.uuid4())[:6]}"

            self._endpoints[port][path] = endpoint_id
            return path, (original_path if path != original_path else None)

    def list_routes(self, port: int) -> List[str]:
        """Return a snapshot list of registered routes for a port."""
        with self._lock:
            return list(self._endpoints.get(port, {}).keys())

    def unregister_routes_for(self, port: int, endpoint_id: str) -> List[str]:
        """Remove all routes owned by ``endpoint_id`` on ``port``.

        Returns the list of removed paths so callers can tear down the matching
        FastAPI routes. Thread-safe.
        """
        with self._lock:
            paths = self._endpoints.get(port, {})
            removed = [p for p, owner in paths.items() if owner == endpoint_id]
            for p in removed:
                del paths[p]
            if not paths:
                self._endpoints.pop(port, None)
            return removed

    def start_server_if_needed(self, port: int, host: str = "0.0.0.0", **kwargs) -> bool:  # noqa: S104
        """Start server with proper readiness signaling. Returns True if server was started."""
        with self._lock:
            if self._started.get(port, False):
                return False  # Already started
            self._started[port] = True
            app = self._apps.get(port)

        if not app:
            raise ValueError(f"No app registered for port {port}")

        ready_event = self._ready_events[port]

        def run_server():
            import uvicorn
            # Remove hardcoded log_level to avoid conflict with kwargs
            config = uvicorn.Config(app, host=host, port=port, **kwargs)
            server = uvicorn.Server(config)
            ready_event.set()  # Signal readiness
            server.run()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        # Check for configurable timeout via environment variable
        try:
            timeout = float(os.environ.get("PRAISONAI_SERVER_READY_TIMEOUT", "5.0"))
        except ValueError:
            logger.warning("Invalid PRAISONAI_SERVER_READY_TIMEOUT value. Using default 5.0s.")
            timeout = 5.0
        became_ready = ready_event.wait(timeout=timeout)

        if not became_ready:
            logger.warning(
                "Agent server on port %s did not become ready within %.1fs. "
                "Proceeding, but some features may not work correctly. "
                "Check server logs for startup errors.",
                port,
                timeout,
            )

        return True


# Module level — single registry instance shared by every launch() call site.
_server_registry = _AgentServerRegistry()

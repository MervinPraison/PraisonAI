"""
Framework Adapter Registry for PraisonAI.

Provides a registry pattern for managing framework adapters with entry points support,
enabling dynamic registration and discovery of framework adapters.
Mirrors the design of integrations/registry.py for consistency.
"""

from __future__ import annotations

import threading
from importlib.metadata import entry_points
from typing import Dict, Type, Optional
import logging

from .base import FrameworkAdapter

logger = logging.getLogger(__name__)


class FrameworkAdapterRegistry:
    """
    Registry for framework adapters.
    
    Provides centralized management of framework adapters with support
    for dynamic registration, entry points discovery, and availability checking.
    
    Uses singleton pattern to ensure consistent state across the application.
    """
    
    _instance: Optional["FrameworkAdapterRegistry"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize the registry with built-in adapters."""
        self._adapters: Dict[str, Type[FrameworkAdapter]] = {}
        self._lock = threading.Lock()
        self._register_builtin()
        self._register_entry_points()

    @classmethod
    def get_instance(cls) -> "FrameworkAdapterRegistry":
        """
        Get the singleton registry instance.
        
        Returns:
            FrameworkAdapterRegistry: The singleton registry
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _register_builtin(self) -> None:
        """Register built-in framework adapters with lazy imports."""
        # Lazy, optional imports - mirrors integrations/registry.py pattern
        try:
            from .crewai_adapter import CrewAIAdapter
            self._adapters["crewai"] = CrewAIAdapter
        except ImportError:
            pass
        
        try:
            from .autogen_adapter import AutoGenAdapter, AutoGenV4Adapter, AG2Adapter
            self._adapters["autogen"] = AutoGenAdapter
            self._adapters["autogen_v4"] = AutoGenV4Adapter
            self._adapters["ag2"] = AG2Adapter
        except ImportError:
            pass
        
        try:
            from .praisonai_adapter import PraisonAIAdapter
            self._adapters["praisonai"] = PraisonAIAdapter
        except ImportError:
            pass

    def _register_entry_points(self) -> None:
        """Register framework adapters from entry points."""
        try:
            for ep in entry_points(group="praisonai.framework_adapters"):
                try:
                    adapter_class = ep.load()
                    self._adapters[ep.name] = adapter_class
                except Exception:
                    # Do not break framework dispatch because one plugin is broken.
                    # Surface via structured logging instead of swallowing silently.
                    logger.warning(
                        "Failed to load framework adapter %r from entry point",
                        ep.name,
                        exc_info=True,
                    )
        except Exception:
            # entry_points() might not be available in older Python versions
            # or in certain packaging environments
            logger.debug("Entry points not available for framework adapters")

    def register(self, name: str, adapter_class: Type[FrameworkAdapter]) -> None:
        """
        Register a new framework adapter.
        
        Args:
            name: Unique name for the adapter
            adapter_class: The adapter class (must implement FrameworkAdapter protocol)
        """
        # Note: We don't enforce strict type checking here since FrameworkAdapter is a Protocol
        # and isinstance() doesn't work with Protocols. The runtime will catch typing issues.
        with self._lock:
            self._adapters[name] = adapter_class

    def unregister(self, name: str) -> bool:
        """
        Unregister a framework adapter.
        
        Args:
            name: Name of the adapter to unregister
            
        Returns:
            bool: True if the adapter was found and removed, False otherwise
        """
        with self._lock:
            return self._adapters.pop(name, None) is not None

    def create(self, name: str) -> FrameworkAdapter:
        """
        Create an instance of the specified framework adapter.
        
        Args:
            name: Name of the adapter to create
            
        Returns:
            FrameworkAdapter: Instance of the adapter
            
        Raises:
            ValueError: If the adapter is not found
        """
        with self._lock:
            adapter_class = self._adapters.get(name)
        
        if adapter_class is None:
            raise ValueError(
                f"Unsupported framework: {name}. "
                f"Registered: {sorted(self._adapters)}"
            )
        
        return adapter_class()

    def list_registered(self) -> list[str]:
        """
        List all registered framework adapter names.
        
        Returns:
            list[str]: Sorted list of registered adapter names
        """
        with self._lock:
            return sorted(self._adapters)

    def is_available(self, name: str) -> bool:
        """
        Check if a framework adapter is available and functional.
        
        Args:
            name: Name of the adapter to check
            
        Returns:
            bool: True if adapter exists and is available
        """
        try:
            adapter = self.create(name)
            return adapter.is_available()
        except (ValueError, Exception):
            return False
"""
Schema versioning and migrations for PraisonAI persistence.

This module provides tools for managing database schema versions
and applying migrations when upgrading.
"""

from .manager import MigrationManager, SchemaVersion

__all__ = ["MigrationManager", "SchemaVersion"]

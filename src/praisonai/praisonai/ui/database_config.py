"""
Database configuration utilities for PraisonAI UI components.

This module provides centralized database configuration functionality,
particularly for handling the FORCE_SQLITE environment variable.
"""

import os
from typing import Optional, Tuple


def should_force_sqlite() -> bool:
    """
    Check if FORCE_SQLITE environment variable is set to true.
    
    Returns:
        bool: True if FORCE_SQLITE is set to "true" (case-insensitive), False otherwise.
    """
    return os.getenv("FORCE_SQLITE", "false").lower() == "true"


def get_database_url_with_sqlite_override() -> Optional[str]:
    """
    Get database URL respecting FORCE_SQLITE flag.
    
    When FORCE_SQLITE=true, this function returns None to force SQLite usage.
    Otherwise, it returns the appropriate database URL from environment variables.
    
    Returns:
        Optional[str]: Database URL if external database should be used, None for SQLite.
    """
    if should_force_sqlite():
        return None
    
    database_url = os.getenv("DATABASE_URL")
    supabase_url = os.getenv("SUPABASE_DATABASE_URL")
    return supabase_url if supabase_url else database_url


def get_database_config_for_sqlalchemy() -> Tuple[Optional[str], Optional[str]]:
    """
    Get database configuration for SQLAlchemy module respecting FORCE_SQLITE flag.
    
    Returns:
        Tuple[Optional[str], Optional[str]]: (DATABASE_URL, SUPABASE_DATABASE_URL)
            Both will be None if FORCE_SQLITE=true, otherwise original values.
    """
    if should_force_sqlite():
        return None, None
    else:
        database_url = os.getenv("DATABASE_URL")
        supabase_url = os.getenv("SUPABASE_DATABASE_URL")
        # Apply Supabase override logic
        if supabase_url:
            database_url = supabase_url
        return database_url, supabase_url
"""
Async file operations for FastContext.

Provides optional aiofiles integration with graceful fallback:
- async_read_file: Async file reading (uses aiofiles if available)
- async_read_lines: Async line reading with range support

Design principles:
- Lazy import of aiofiles (optional dependency)
- Graceful fallback to sync operations in executor
- No import-time overhead
"""

import asyncio
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

# Lazy availability check
_AIOFILES_AVAILABLE: Optional[bool] = None


def _check_aiofiles() -> bool:
    """Lazy check for aiofiles availability.
    
    Returns:
        True if aiofiles is installed and importable
    """
    global _AIOFILES_AVAILABLE
    if _AIOFILES_AVAILABLE is None:
        try:
            import aiofiles  # noqa: F401
            _AIOFILES_AVAILABLE = True
            logger.debug("aiofiles available")
        except ImportError:
            _AIOFILES_AVAILABLE = False
            logger.debug("aiofiles not available, using sync fallback")
    return _AIOFILES_AVAILABLE


def _sync_read_file(
    path: str,
    encoding: str = 'utf-8',
    errors: str = 'ignore'
) -> str:
    """Sync file read for fallback."""
    with open(path, 'r', encoding=encoding, errors=errors) as f:
        return f.read()


def _sync_read_lines(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    encoding: str = 'utf-8',
    errors: str = 'ignore'
) -> List[str]:
    """Sync line read for fallback."""
    with open(path, 'r', encoding=encoding, errors=errors) as f:
        lines = f.readlines()
    
    if start_line is not None and end_line is not None:
        # Convert to 0-indexed
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        return [line.rstrip('\n\r') for line in lines[start_idx:end_idx]]
    elif start_line is not None:
        start_idx = max(0, start_line - 1)
        return [line.rstrip('\n\r') for line in lines[start_idx:]]
    elif end_line is not None:
        end_idx = min(len(lines), end_line)
        return [line.rstrip('\n\r') for line in lines[:end_idx]]
    else:
        return [line.rstrip('\n\r') for line in lines]


async def async_read_file(
    path: str,
    encoding: str = 'utf-8',
    errors: str = 'ignore'
) -> str:
    """Read file asynchronously.
    
    Uses aiofiles if available, otherwise runs sync read in executor.
    
    Args:
        path: File path to read
        encoding: Text encoding
        errors: Error handling ('ignore', 'strict', 'replace')
        
    Returns:
        File content as string
    """
    if _check_aiofiles():
        import aiofiles
        async with aiofiles.open(path, 'r', encoding=encoding, errors=errors) as f:
            return await f.read()
    else:
        # Fallback: run sync read in thread executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            lambda: _sync_read_file(path, encoding, errors)
        )


async def async_read_lines(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    encoding: str = 'utf-8',
    errors: str = 'ignore'
) -> List[str]:
    """Read specific lines from file asynchronously.
    
    Args:
        path: File path to read
        start_line: First line to read (1-indexed, inclusive)
        end_line: Last line to read (1-indexed, inclusive)
        encoding: Text encoding
        errors: Error handling
        
    Returns:
        List of lines (without line endings)
    """
    if _check_aiofiles():
        import aiofiles
        async with aiofiles.open(path, 'r', encoding=encoding, errors=errors) as f:
            lines = await f.readlines()
        
        if start_line is not None and end_line is not None:
            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)
            return [line.rstrip('\n\r') for line in lines[start_idx:end_idx]]
        elif start_line is not None:
            start_idx = max(0, start_line - 1)
            return [line.rstrip('\n\r') for line in lines[start_idx:]]
        elif end_line is not None:
            end_idx = min(len(lines), end_line)
            return [line.rstrip('\n\r') for line in lines[:end_idx]]
        else:
            return [line.rstrip('\n\r') for line in lines]
    else:
        # Fallback
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: _sync_read_lines(path, start_line, end_line, encoding, errors)
        )


def is_aiofiles_available() -> bool:
    """Check if aiofiles is available for async operations.
    
    Returns:
        True if aiofiles is installed
    """
    return _check_aiofiles()

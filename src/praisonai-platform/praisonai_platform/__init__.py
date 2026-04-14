"""
PraisonAI Platform — workspace, auth, issues, projects.

A separate package providing multi-tenancy, authentication, issue tracking,
and project management on top of the praisonaiagents core SDK.

Quick-start usage::

    from praisonai_platform import PlatformClient, create_app, __version__

    # Start FastAPI app
    app = create_app()

    # Use SDK client
    async with PlatformClient("http://localhost:8000") as client:
        await client.register("user@example.com", "pass")
"""

# Read version from package metadata
try:
    from importlib.metadata import version
    __version__ = version("praisonai-platform")
except ImportError:
    # Fallback for older Python versions
    try:
        from importlib_metadata import version
        __version__ = version("praisonai-platform")
    except (ImportError, Exception):
        __version__ = "0.1.0"

# Lazy imports to handle missing dependencies gracefully
def _get_create_app():
    """Lazy import for create_app to handle missing db module."""
    try:
        from .api.app import create_app
        return create_app
    except ImportError as e:
        error_msg = str(e)
        def create_app(*args, **kwargs):
            raise ImportError(
                f"Cannot create FastAPI app due to missing dependencies: {error_msg}. "
                "The database module may be incomplete or missing."
            )
        return create_app

def _get_platform_client():
    """Lazy import for PlatformClient."""
    from .client.platform_client import PlatformClient
    return PlatformClient

# Public API exports using lazy imports
create_app = _get_create_app()
PlatformClient = _get_platform_client()

__all__ = ["create_app", "PlatformClient", "__version__"]

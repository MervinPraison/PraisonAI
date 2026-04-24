"""
PraisonAI Platform — workspace, auth, issues, projects.

A separate package providing multi-tenancy, authentication, issue tracking,
and project management on top of the praisonaiagents core SDK.

Quick start::

    from praisonai_platform import PlatformClient, create_app

    # Client SDK
    async with PlatformClient("http://localhost:8000") as client:
        await client.register("agent@example.com", "password")
        workspaces = await client.list_workspaces()

    # Run server
    app = create_app()
"""

__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy import for platform components."""
    if name == "create_app":
        from .api.app import create_app
        return create_app
    elif name == "PlatformClient":
        from .client.platform_client import PlatformClient
        return PlatformClient
    raise AttributeError(f"module 'praisonai_platform' has no attribute '{name}'")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + ["create_app", "PlatformClient"])


__all__ = [
    "__version__",
    "create_app",
    "PlatformClient",
]

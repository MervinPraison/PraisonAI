"""
Cloud provider adapters for deployment.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseProvider
    from .aws import AWSProvider
    from .azure import AzureProvider
    from .gcp import GCPProvider


def __getattr__(name):
    """Lazy load provider modules."""
    if name == 'BaseProvider':
        from .base import BaseProvider
        return BaseProvider
    elif name == 'AWSProvider':
        from .aws import AWSProvider
        return AWSProvider
    elif name == 'AzureProvider':
        from .azure import AzureProvider
        return AzureProvider
    elif name == 'GCPProvider':
        from .gcp import GCPProvider
        return GCPProvider
    elif name == 'get_provider':
        from .base import get_provider
        return get_provider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ['BaseProvider', 'AWSProvider', 'AzureProvider', 'GCPProvider', 'get_provider']

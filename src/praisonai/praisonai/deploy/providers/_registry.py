"""
Registry for cloud deployment providers.

Maps provider names to their implementation classes (lazy-loaded).
Extensible: third-party providers can register via entry points.
"""

from __future__ import annotations

from typing import Optional

from ..._registry import PluginRegistry


def _aws_loader():
    from .aws import AWSProvider
    return AWSProvider


def _azure_loader():
    from .azure import AzureProvider
    return AzureProvider


def _gcp_loader():
    from .gcp import GCPProvider
    return GCPProvider


# Built-in cloud providers with lazy loading
_BUILTIN_CLOUDS = {
    "aws": _aws_loader,
    "azure": _azure_loader,
    "gcp": _gcp_loader,
}


class CloudProviderRegistry(PluginRegistry):
    """Registry for cloud deployment providers."""
    
    def __init__(self):
        super().__init__(
            entry_point_group="praisonai.deploy.providers",
            builtins=_BUILTIN_CLOUDS
        )
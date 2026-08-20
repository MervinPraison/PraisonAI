"""
Registry for cloud deployment providers.

Maps provider names to their implementation classes (lazy-loaded).
Extensible: third-party providers can register via entry points.
"""

from __future__ import annotations

from typing import Optional

from praisonai_deploy._plugin_registry import PluginRegistry


def _aws_loader():
    from .aws import AWSProvider
    return AWSProvider


def _azure_loader():
    from .azure import AzureProvider
    return AzureProvider


def _gcp_loader():
    from .gcp import GCPProvider
    return GCPProvider


def _fly_loader():
    from .fly import FlyProvider
    return FlyProvider


def _railway_loader():
    from .railway import RailwayProvider
    return RailwayProvider


def _render_loader():
    from .render import RenderProvider
    return RenderProvider


# Built-in cloud providers with lazy loading
_BUILTIN_CLOUDS = {
    "aws": _aws_loader,
    "azure": _azure_loader,
    "gcp": _gcp_loader,
    "fly": _fly_loader,
    "railway": _railway_loader,
    "render": _render_loader,
}


class CloudProviderRegistry(PluginRegistry):
    """Registry for cloud deployment providers."""
    
    def __init__(self):
        super().__init__(
            entry_point_group="praisonai.deploy.providers",
            builtins=_BUILTIN_CLOUDS
        )


def list_cloud_providers() -> list[str]:
    """Every deployable provider name: built-ins plus entry-point plugins.

    This is the *authority* on which providers exist. ``models.CloudProvider``
    only names the built-ins and must never be used as the validation gate.

    Built-ins keep their declaration order; plugins are appended sorted.
    """
    names = set(CloudProviderRegistry.default().list_names())
    ordered = [n for n in _BUILTIN_CLOUDS if n in names]
    ordered += sorted(names.difference(ordered))
    return ordered
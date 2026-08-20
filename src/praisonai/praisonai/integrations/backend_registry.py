"""Registry of managed agent-runtime backends.

This moves provider -> backend resolution off the hardcoded ``if provider !=
"anthropic"`` switch in :mod:`hosted_agent` and onto the same plugin-registry
primitive used for framework adapters. A third-party package can register a
``praisonai.managed_backends`` entry point and have ``HostedAgent(provider=...)``
resolve it with no core change.

Builtins:
    - ``anthropic`` -> :class:`AnthropicManagedAgent`

Future entry-point backends (e.g. ``e2b``, ``modal``, ``flyio``) register
themselves under the ``praisonai.managed_backends`` group.
"""

from __future__ import annotations

from typing import Type

from .._registry import PluginRegistry


def _anthropic_loader() -> Type:
    from .managed_agents import AnthropicManagedAgent
    return AnthropicManagedAgent


def _compute_backed() -> dict:
    """Every compute place, able to host a whole agent.

    run_on= accepted two names while tools_run_on= accepted twelve, which was
    an implementation detail leaking into the vocabulary: a place that can run
    a command can run the agent loop, which is just one more command. There was
    simply no backend written for the rest. One generic backend covers them
    all rather than eleven near-identical ones.

    `docker` keeps its specialised backend -- it can talk to the daemon
    directly and skip a provisioning layer -- so it is not overridden here.
    Places that cannot host a loop are excluded: `ssh` needs an object rather
    than a name, and `local` would run the agent in your own shell, which is
    what you already get by not passing run_on= at all.
    """
    from .compute_managed_agent import make_loader

    try:
        from praisonaiagents.managed._compute_bridge import available_providers

        places = available_providers()
    except Exception:
        return {}

    # `docker` used to be excluded here in favour of a bespoke backend that
    # talked to the daemon directly. That backend named its containers in a
    # shape DockerCompute's lookup did not recognise, so `praisonai managed ps`
    # listed them and `praisonai managed stop` could not stop them. The generic
    # path goes through DockerCompute, so reclaim works.
    #
    # Still excluded: `ssh` needs an object rather than a name; `local` would
    # run the agent in your own shell, which is what you get by passing
    # nothing; the local sandboxes isolate tools rather than host a runtime.
    skip = {"ssh", "local", "native", "subprocess", "sandlock"}
    return {name: make_loader(name) for name in places if name not in skip}


_BUILTIN_BACKENDS = {
    "anthropic": _anthropic_loader,
    # Self-hosted: the whole agent loop runs in a local container rather than a
    # vendor's cloud. Registering it here is all that `run_on="docker"` needs --
    # placement resolves run_on= against this registry, so the parameter, the
    # repr, the explanation and the conflict checks all pick it up unchanged.
    **_compute_backed(),
}


class ManagedBackendRegistry(PluginRegistry):
    """Registry for managed agent-runtime backends with entry-point support."""

    def __init__(self) -> None:
        super().__init__(
            entry_point_group="praisonai.managed_backends",
            builtins=_BUILTIN_BACKENDS,
        )


def get_backend_registry() -> "ManagedBackendRegistry":
    """Return the process-default managed-backend registry."""
    return ManagedBackendRegistry.default()

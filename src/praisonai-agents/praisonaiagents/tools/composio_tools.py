"""Composio tool integration.

Composio provides 250+ managed app integrations (GitHub, Slack, Gmail, Jira,
Notion, Linear, etc.) exposed as agent-callable tools. This module wraps the
optional ``composio`` package and returns plain Python callables that any
PraisonAI Agent can use directly via its ``tools=[...]`` parameter.

This module requires:
1. The ``composio`` package: ``pip install composio``
2. The ``COMPOSIO_API_KEY`` environment variable (or pass ``api_key=``).

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import composio_tools

    # Load a set of app tools (auto-resolved from Composio)
    tools = composio_tools(apps=["github"])

    agent = Agent(name="dev", tools=tools)
    agent.start("Star the praisonai/PraisonAI repository")

    # Or fetch by explicit tool/action names
    tools = composio_tools(actions=["GITHUB_STAR_A_REPOSITORY"])

    # Class style for more control
    from praisonaiagents.tools import ComposioTools
    composio = ComposioTools()
    tools = composio.get_tools(apps=["slack"])
"""

from typing import List, Dict, Any, Optional, Callable
import os
from importlib import util

from praisonaiagents._logging import get_logger


def _check_composio_available() -> tuple[bool, Optional[str]]:
    """Check if Composio is available and an API key is set.

    Returns:
        Tuple of (is_available, error_message).
    """
    if util.find_spec("composio") is None and util.find_spec("composio_openai") is None:
        return False, (
            "composio package is not installed. Install it with: pip install composio"
        )

    if not os.environ.get("COMPOSIO_API_KEY"):
        return False, (
            "COMPOSIO_API_KEY environment variable is not set. "
            "Please set it to use Composio tools."
        )

    return True, None


class ComposioTools:
    """Composio managed-integration tools.

    Wraps the Composio SDK and exposes its actions as agent-callable Python
    functions. A fresh instance is safe to create per agent/session; the heavy
    ``composio`` client is created lazily on first use.

    Example:
        from praisonaiagents.tools import ComposioTools

        composio = ComposioTools()
        tools = composio.get_tools(apps=["github"])
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize ComposioTools.

        Args:
            api_key: Composio API key. If not provided, uses COMPOSIO_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("COMPOSIO_API_KEY")
        self._client = None
        self.logger = get_logger(__name__)

    def _get_client(self):
        """Get or create the Composio client (lazy import)."""
        if self._client is None:
            is_available, error = _check_composio_available()
            if not is_available:
                raise ImportError(error)

            try:
                from composio import Composio

                self._client = Composio(api_key=self.api_key)
            except ImportError:
                # Older Composio releases expose the client differently.
                from composio import ComposioToolSet

                self._client = ComposioToolSet(api_key=self.api_key)
        return self._client

    def get_tools(
        self,
        apps: Optional[List[str]] = None,
        actions: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> List[Callable]:
        """Fetch Composio tools as agent-callable Python functions.

        Args:
            apps: App slugs to load tools for (e.g. ["github", "slack"]).
            actions: Explicit action/tool names to load (e.g. ["GITHUB_STAR_A_REPOSITORY"]).
            tags: Optional tags to filter tools by.
            user_id: Optional Composio user/entity id for authenticated actions.

        Returns:
            A list of callables usable in ``Agent(tools=[...])``. Returns an empty
            list if Composio is unavailable or an error occurs.
        """
        is_available, error = _check_composio_available()
        if not is_available:
            self.logger.error(error)
            return []

        try:
            client = self._get_client()

            kwargs: Dict[str, Any] = {}
            if apps:
                kwargs["apps"] = apps
            if actions:
                kwargs["actions"] = actions
            if tags:
                kwargs["tags"] = tags
            if user_id:
                kwargs["user_id"] = user_id

            # Newer Composio SDK: client.tools.get(...)
            if hasattr(client, "tools") and hasattr(client.tools, "get"):
                tools = client.tools.get(**kwargs)
            else:
                # Older ComposioToolSet exposes get_tools(...)
                toolset_kwargs = {
                    k: v for k, v in kwargs.items() if k in {"apps", "actions", "tags"}
                }
                tools = client.get_tools(**toolset_kwargs)

            return list(tools) if tools else []

        except Exception as e:
            self.logger.error(f"Composio get_tools error: {e}")
            return []

    def list_apps(self) -> List[str]:
        """List available Composio app slugs.

        Returns:
            A list of app slug strings, or an empty list on error.
        """
        is_available, error = _check_composio_available()
        if not is_available:
            self.logger.error(error)
            return []

        try:
            client = self._get_client()

            if hasattr(client, "apps") and hasattr(client.apps, "get"):
                apps = client.apps.get()
            elif hasattr(client, "get_apps"):
                apps = client.get_apps()
            else:
                return []

            result = []
            for app in apps or []:
                slug = getattr(app, "key", None) or getattr(app, "name", None) or getattr(app, "slug", None)
                if slug is None and isinstance(app, dict):
                    slug = app.get("key") or app.get("name") or app.get("slug")
                if slug:
                    result.append(slug)
            return result

        except Exception as e:
            self.logger.error(f"Composio list_apps error: {e}")
            return []


# Standalone function for easy access


def composio_tools(
    apps: Optional[List[str]] = None,
    actions: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Callable]:
    """Load Composio tools as agent-callable Python functions.

    Args:
        apps: App slugs to load tools for (e.g. ["github", "slack"]).
        actions: Explicit action/tool names to load.
        tags: Optional tags to filter tools by.
        user_id: Optional Composio user/entity id for authenticated actions.
        api_key: Composio API key. If not provided, uses COMPOSIO_API_KEY env var.

    Returns:
        A list of callables usable in ``Agent(tools=[...])``.

    Example:
        from praisonaiagents import Agent
        from praisonaiagents.tools import composio_tools

        agent = Agent(name="dev", tools=composio_tools(apps=["github"]))
        agent.start("Star praisonai/PraisonAI")
    """
    tools = ComposioTools(api_key=api_key)
    return tools.get_tools(apps=apps, actions=actions, tags=tags, user_id=user_id)


def composio_list_apps(api_key: Optional[str] = None) -> List[str]:
    """List available Composio app slugs.

    Args:
        api_key: Composio API key. If not provided, uses COMPOSIO_API_KEY env var.

    Returns:
        A list of app slug strings.

    Example:
        apps = composio_list_apps()
        print(apps)  # ["github", "slack", "gmail", ...]
    """
    tools = ComposioTools(api_key=api_key)
    return tools.list_apps()


# Alias for simple usage
composio = composio_tools


if __name__ == "__main__":
    print("=" * 60)
    print("Composio Tools - Example Usage")
    print("=" * 60)

    is_available, error = _check_composio_available()
    if not is_available:
        print(f"\nComposio is not available: {error}")
        print("\nTo use Composio tools:")
        print("1. Install the package: pip install composio")
        print("2. Set environment variable: export COMPOSIO_API_KEY=your_api_key")
    else:
        print("Composio SDK is available!")
        apps = composio_list_apps()
        print(f"\nFound {len(apps)} available apps")
        for app in apps[:10]:
            print(f"  - {app}")

    print("\n" + "=" * 60)
    print("Demonstration Complete")
    print("=" * 60)

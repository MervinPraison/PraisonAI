"""Local browser automation tool for PraisonAI Bots.

Wraps praisonai-browser's ``PlaywrightBrowserAgent`` so bot agents can drive a
local (Playwright) browser to navigate, snapshot and click without requiring
cloud credentials (unlike ``BrowserBaseTool``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def create_browser_tool(
    model: str = "gpt-4o-mini",
    headless: bool = True,
    profile: str = "default",
):
    """Create an agent-callable browser automation tool.

    Args:
        model: LLM model used by the browser agent.
        headless: Run the Playwright browser headless (``--browser-headless``).
        profile: Browser profile name (``--browser-profile``). Note: the
            underlying ``PlaywrightBrowserAgent`` launches a fresh ephemeral
            context and does not yet honour named profiles, so this value is
            currently informational only.

    Returns:
        A callable ``browser_automate`` tool.
    """
    from .._browser_bridge import import_browser_attr

    if profile and profile != "default":
        logger.info(
            "Browser profile %r requested but local PlaywrightBrowserAgent uses a "
            "fresh context; profile is not yet applied.",
            profile,
        )

    def browser_automate(goal: str, start_url: str = "https://www.google.com") -> Dict[str, Any]:
        """Automate a local browser to accomplish a goal.

        Navigates, snapshots the page and clicks/types as needed using a local
        Playwright browser (no cloud API key required).

        Args:
            goal: The task to accomplish in the browser.
            start_url: URL to start from.

        Returns:
            Result dict with success status, summary and final URL.
        """
        try:
            PlaywrightBrowserAgent = import_browser_attr("PlaywrightBrowserAgent")
        except ImportError as exc:
            return {"success": False, "error": str(exc)}

        agent = PlaywrightBrowserAgent(model=model, headless=headless)

        async def _run() -> Dict[str, Any]:
            return await agent.run(goal, start_url)

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, _run()).result()
            return asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Browser automation failed: %s", exc)
            return {"success": False, "error": str(exc)}

    browser_automate.__doc__ = (
        f"{browser_automate.__doc__}\n\n(headless={headless})"
    )
    return browser_automate

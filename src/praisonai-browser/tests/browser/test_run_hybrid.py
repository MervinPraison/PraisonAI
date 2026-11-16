"""Tests for run_hybrid engine fallback."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from praisonai_browser import cdp_agent, playwright_agent


def test_playwright_fallback_forwards_verbose():
    """run_hybrid(verbose=True) must pass verbose to the Playwright fallback."""
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value={"success": True})
    fake_cls = MagicMock(return_value=fake_agent)

    # aiohttp unavailable -> no extension and no CDP -> Playwright fallback
    with patch.dict(sys.modules, {"aiohttp": None}), \
         patch.object(playwright_agent, "PlaywrightBrowserAgent", fake_cls):
        result = asyncio.run(cdp_agent.run_hybrid("goal", verbose=True))

    assert result["engine"] == "playwright"
    assert fake_cls.call_args.kwargs["verbose"] is True

"""Playwright Browser Agent - Cross-browser automation using Playwright.

This module provides browser automation using Microsoft Playwright,
enabling cross-browser support (Chromium, Firefox, WebKit) and 
robust automation features.

Usage:
    praisonai browser run "Search for AI" --engine playwright

Requires:
    pip install playwright
    playwright install chromium
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger("praisonai.browser.playwright_agent")


@dataclass 
class PlaywrightPageState:
    """Page state captured via Playwright."""
    url: str
    title: str
    elements: List[Dict[str, Any]]


class PlaywrightBrowserAgent:
    """Browser agent using Playwright for cross-browser automation.
    
    Example:
        agent = PlaywrightBrowserAgent()
        await agent.run("Search for praisonai on Google")
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_steps: int = 15,
        headless: bool = True,
        browser_type: str = "chromium",  # chromium, firefox, webkit
        verbose: bool = False,
    ):
        self.model = model
        self.max_steps = max_steps
        self.headless = headless
        self.browser_type = browser_type
        self.verbose = verbose
        self.browser = None
        self.page = None
        self.playwright = None
    
    async def _launch(self):
        """Launch browser via Playwright."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright required: pip install playwright && playwright install chromium"
            )
        
        self.playwright = await async_playwright().start()
        
        # Select browser type
        if self.browser_type == "firefox":
            browser_launcher = self.playwright.firefox
        elif self.browser_type == "webkit":
            browser_launcher = self.playwright.webkit
        else:
            browser_launcher = self.playwright.chromium
        
        self.browser = await browser_launcher.launch(headless=self.headless)
        self.page = await self.browser.new_page()
        
        logger.info(f"Launched {self.browser_type} browser (headless={self.headless})")
    
    async def _get_page_state(self) -> PlaywrightPageState:
        """Get current page state via Playwright."""
        url = self.page.url
        title = await self.page.title()
        
        # Get interactive elements
        elements = await self.page.evaluate("""
            () => {
                const selectors = 'a, button, input, textarea, select, [onclick], [role="button"]';
                const elements = [];
                document.querySelectorAll(selectors).forEach((el, i) => {
                    if (el.offsetParent === null) return;
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;
                    
                    elements.push({
                        index: i,
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        text: (el.textContent || el.placeholder || el.value || '').trim().slice(0, 50),
                        selector: el.id ? '#' + el.id : 
                                  el.name ? el.tagName.toLowerCase() + '[name="' + el.name + '"]' :
                                  el.className ? el.tagName.toLowerCase() + '.' + el.className.split(' ')[0] : ''
                    });
                });
                return elements.slice(0, 30);
            }
        """)
        
        return PlaywrightPageState(url=url, title=title, elements=elements)
    
    async def _execute_action(self, action: Dict) -> Dict[str, Any]:
        """Execute action via Playwright."""
        action_type = action.get("action", "").lower()
        selector = action.get("selector", "")
        value = action.get("value", "")
        
        try:
            if action_type == "navigate":
                url = action.get("url", value)
                await self.page.goto(url, wait_until="domcontentloaded")
                return {"success": True}
            
            elif action_type == "type":
                # Clear and type
                await self.page.fill(selector, value)
                return {"success": True}
            
            elif action_type == "submit":
                await self.page.keyboard.press("Enter")
                await self.page.wait_for_load_state("domcontentloaded")
                return {"success": True}
            
            elif action_type == "click":
                await self.page.click(selector, timeout=5000)
                await asyncio.sleep(1)
                return {"success": True}
            
            elif action_type == "scroll":
                direction = action.get("direction", "down")
                delta = 300 if direction == "down" else -300
                await self.page.mouse.wheel(0, delta)
                return {"success": True}
            
            elif action_type in ("done", "wait"):
                return {"success": True}
            
            else:
                return {"success": False, "error": f"Unknown action: {action_type}"}
                
        except Exception as e:
            logger.warning(f"Playwright action failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def run(self, goal: str, start_url: str = "https://www.google.com") -> Dict[str, Any]:
        """Run browser automation to achieve goal.
        
        Args:
            goal: Task to accomplish
            start_url: Starting URL
            
        Returns:
            Result dict with success status and summary
        """
        from .agent import BrowserAgent, normalize_action
        
        try:
            # Launch browser
            await self._launch()
            await self.page.goto(start_url, wait_until="domcontentloaded")
            
            # Create browser agent
            agent = BrowserAgent(model=self.model, max_steps=self.max_steps, verbose=self.verbose)
            
            # Main automation loop
            for step in range(self.max_steps):
                # Get page state
                state = await self._get_page_state()
                
                if self.verbose:
                    logger.info(f"Step {step}: {state.url}")
                
                # Build observation
                observation = {
                    "task": goal,
                    "original_goal": goal,
                    "url": state.url,
                    "title": state.title,
                    "elements": state.elements,
                    "step_number": step,
                }
                
                # Get action from agent
                action = agent.process_observation(observation)
                action = normalize_action(action)
                
                if self.verbose:
                    logger.info(f"  Action: {action.get('action')} | Done: {action.get('done')}")
                
                # Check for completion
                if action.get("done"):
                    # Take screenshot for proof
                    screenshot_path = f"/tmp/playwright_done_{step}.png"
                    await self.page.screenshot(path=screenshot_path)
                    
                    return {
                        "success": True,
                        "summary": action.get("summary", "Task completed"),
                        "steps": step + 1,
                        "final_url": state.url,
                        "screenshot": screenshot_path
                    }
                
                # Execute action
                result = await self._execute_action(action)
                
                if not result.get("success"):
                    logger.warning(f"Action failed: {result.get('error')}")
                
                await asyncio.sleep(0.5)
            
            return {
                "success": False,
                "error": "Max steps reached",
                "steps": self.max_steps
            }
            
        finally:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()


async def run_playwright(
    goal: str,
    url: str = "https://www.google.com",
    model: str = "gpt-4o-mini",
    headless: bool = True,
    browser_type: str = "chromium",
    max_steps: int = 15,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run browser agent using Playwright for cross-browser automation.
    
    Args:
        goal: Task to accomplish
        url: Starting URL
        model: LLM model to use
        headless: Run in headless mode
        browser_type: Browser to use (chromium, firefox, webkit)
        max_steps: Maximum automation steps
        verbose: Enable verbose logging
        
    Returns:
        Result with success status and summary
        
    Example:
        result = await run_playwright(
            "Search for PraisonAI on Google",
            url="https://google.com",
            headless=True
        )
    """
    agent = PlaywrightBrowserAgent(
        model=model,
        max_steps=max_steps,
        headless=headless,
        browser_type=browser_type,
        verbose=verbose
    )
    return await agent.run(goal, url)

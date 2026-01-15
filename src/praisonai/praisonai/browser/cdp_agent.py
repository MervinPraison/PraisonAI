"""CDP-Only Browser Agent - Direct CDP control without Chrome extension.

This module provides browser automation using Chrome DevTools Protocol directly,
without requiring the PraisonAI Chrome extension. Useful for:
- Headless automation
- Environments where extensions can't be loaded
- Simpler deployment scenarios

Usage:
    praisonai browser run "Search for AI" --engine cdp
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger("praisonai.browser.cdp_agent")


@dataclass
class CDPPageState:
    """Page state captured via CDP."""
    url: str
    title: str
    elements: List[Dict[str, Any]]
    viewport: Dict[str, int]


class CDPBrowserAgent:
    """Browser agent using direct CDP control (no extension required).
    
    Example:
        agent = CDPBrowserAgent(port=9222)
        await agent.run("Search for praisonai on Google")
    """
    
    def __init__(
        self,
        port: int = 9222,
        model: str = "gpt-4o-mini",
        max_steps: int = 15,
        verbose: bool = False,
    ):
        self.port = port
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        self.ws = None
        self._message_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
    
    async def _get_targets(self) -> List[Dict]:
        """Get Chrome debugger targets."""
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp required: pip install aiohttp")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:{self.port}/json") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Chrome not responding on port {self.port}")
                return await resp.json()
    
    async def _connect_to_page(self, url: Optional[str] = None) -> str:
        """Connect to a page target or create new one."""
        try:
            import websockets
        except ImportError:
            raise ImportError("websockets required: pip install websockets")
        
        targets = await self._get_targets()
        
        # Find an existing page or background page
        page = None
        for t in targets:
            if t.get("type") == "page" and not t.get("url", "").startswith("chrome"):
                page = t
                break
        
        if not page:
            # No suitable page, need to create one via browser target
            browser = next((t for t in targets if t.get("type") == "browser"), None)
            if browser:
                # Create new tab via Target.createTarget
                async with websockets.connect(browser["webSocketDebuggerUrl"]) as ws:
                    await ws.send(json.dumps({
                        "id": 1,
                        "method": "Target.createTarget",
                        "params": {"url": url or "https://www.google.com"}
                    }))
                    response = json.loads(await ws.recv())
                    target_id = response.get("result", {}).get("targetId")
                    if target_id:
                        targets = await self._get_targets()
                        page = next((t for t in targets if t.get("id") == target_id), None)
        
        if not page:
            raise RuntimeError("No page target available")
        
        # Connect to page
        import websockets
        self.ws = await websockets.connect(page["webSocketDebuggerUrl"])
        
        # Enable required domains
        await self._send("Page.enable")
        await self._send("DOM.enable")
        await self._send("Runtime.enable")
        
        # Navigate if URL provided
        if url:
            await self._send("Page.navigate", {"url": url})
            await asyncio.sleep(2)  # Wait for load
        
        return page.get("url", "")
    
    async def _send(self, method: str, params: Optional[Dict] = None) -> Dict:
        """Send CDP command and wait for response."""
        self._message_id += 1
        msg_id = self._message_id
        
        message = {"id": msg_id, "method": method}
        if params:
            message["params"] = params
        
        await self.ws.send(json.dumps(message))
        
        # Wait for response with matching ID
        while True:
            response = json.loads(await self.ws.recv())
            if response.get("id") == msg_id:
                if "error" in response:
                    raise RuntimeError(f"CDP error: {response['error']}")
                return response.get("result", {})
    
    async def _get_page_state(self) -> CDPPageState:
        """Get current page state via CDP."""
        # Get URL and title
        result = await self._send("Runtime.evaluate", {
            "expression": "JSON.stringify({url: location.href, title: document.title})"
        })
        info = json.loads(result.get("result", {}).get("value", "{}"))
        
        # Get interactive elements
        elements_js = """
        (() => {
            const selectors = 'a, button, input, textarea, select, [onclick], [role="button"]';
            const elements = [];
            document.querySelectorAll(selectors).forEach((el, i) => {
                if (el.offsetParent === null) return; // Skip hidden
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                
                elements.push({
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    text: (el.textContent || el.placeholder || el.value || '').trim().slice(0, 50),
                    selector: el.id ? '#' + el.id : 
                              el.name ? el.tagName.toLowerCase() + '[name="' + el.name + '"]' :
                              el.className ? el.tagName.toLowerCase() + '.' + el.className.split(' ')[0] : '',
                    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
                });
            });
            return elements.slice(0, 30);
        })()
        """
        result = await self._send("Runtime.evaluate", {
            "expression": f"JSON.stringify({elements_js})",
            "returnByValue": True
        })
        elements = json.loads(result.get("result", {}).get("value", "[]"))
        
        # Get viewport
        result = await self._send("Runtime.evaluate", {
            "expression": "JSON.stringify({width: window.innerWidth, height: window.innerHeight})"
        })
        viewport = json.loads(result.get("result", {}).get("value", "{}"))
        
        return CDPPageState(
            url=info.get("url", ""),
            title=info.get("title", ""),
            elements=elements,
            viewport=viewport
        )
    
    async def _execute_action(self, action: Dict) -> Dict[str, Any]:
        """Execute action via CDP."""
        action_type = action.get("action", "").lower()
        selector = action.get("selector", "")
        value = action.get("value", "")
        
        try:
            if action_type == "navigate":
                url = action.get("url", value)
                await self._send("Page.navigate", {"url": url})
                await asyncio.sleep(2)
                return {"success": True}
            
            elif action_type == "type":
                # Focus element and type
                await self._send("Runtime.evaluate", {
                    "expression": f"document.querySelector('{selector}')?.focus()"
                })
                await asyncio.sleep(0.2)
                
                # Clear existing text
                await self._send("Input.insertText", {"text": ""})
                
                # Type new text
                for char in value:
                    await self._send("Input.dispatchKeyEvent", {
                        "type": "char",
                        "text": char
                    })
                    await asyncio.sleep(0.02)
                
                return {"success": True}
            
            elif action_type == "submit":
                await self._send("Input.dispatchKeyEvent", {
                    "type": "keyDown",
                    "key": "Enter",
                    "code": "Enter",
                    "windowsVirtualKeyCode": 13
                })
                await self._send("Input.dispatchKeyEvent", {
                    "type": "keyUp",
                    "key": "Enter",
                    "code": "Enter"
                })
                await asyncio.sleep(2)
                return {"success": True}
            
            elif action_type == "click":
                # Get element position
                result = await self._send("Runtime.evaluate", {
                    "expression": f"""
                        (function() {{
                            const el = document.querySelector('{selector}');
                            if (!el) return null;
                            const rect = el.getBoundingClientRect();
                            return {{x: rect.x + rect.width/2, y: rect.y + rect.height/2}};
                        }})()
                    """,
                    "returnByValue": True
                })
                pos = result.get("result", {}).get("value")
                
                if pos:
                    x, y = pos["x"], pos["y"]
                    # Click sequence
                    await self._send("Input.dispatchMouseEvent", {
                        "type": "mousePressed",
                        "x": x, "y": y,
                        "button": "left",
                        "clickCount": 1
                    })
                    await self._send("Input.dispatchMouseEvent", {
                        "type": "mouseReleased",
                        "x": x, "y": y,
                        "button": "left"
                    })
                    await asyncio.sleep(1)
                    return {"success": True}
                else:
                    # Fallback to JS click
                    await self._send("Runtime.evaluate", {
                        "expression": f"document.querySelector('{selector}')?.click()"
                    })
                    await asyncio.sleep(1)
                    return {"success": True}
            
            elif action_type == "scroll":
                direction = action.get("direction", "down")
                delta_y = 300 if direction == "down" else -300
                await self._send("Input.dispatchMouseEvent", {
                    "type": "mouseWheel",
                    "x": 400, "y": 300,
                    "deltaX": 0, "deltaY": delta_y
                })
                await asyncio.sleep(0.5)
                return {"success": True}
            
            elif action_type in ("done", "wait"):
                return {"success": True}
            
            else:
                return {"success": False, "error": f"Unknown action: {action_type}"}
                
        except Exception as e:
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
            # Connect to Chrome
            logger.info(f"Connecting to Chrome on port {self.port}")
            await self._connect_to_page(start_url)
            
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
                    return {
                        "success": True,
                        "summary": action.get("summary", "Task completed"),
                        "steps": step + 1,
                        "final_url": state.url
                    }
                
                # Execute action
                result = await self._execute_action(action)
                
                if not result.get("success"):
                    logger.warning(f"Action failed: {result.get('error')}")
                
                await asyncio.sleep(1)  # Brief pause between steps
            
            return {
                "success": False,
                "error": "Max steps reached",
                "steps": self.max_steps
            }
            
        finally:
            if self.ws:
                await self.ws.close()


async def run_cdp_only(
    goal: str,
    url: str = "https://www.google.com",
    model: str = "gpt-4o-mini",
    port: int = 9222,
    max_steps: int = 15,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run browser agent using direct CDP (no extension required).
    
    Args:
        goal: Task to accomplish
        url: Starting URL
        model: LLM model to use
        port: Chrome debug port
        max_steps: Maximum automation steps
        verbose: Enable verbose logging
        
    Returns:
        Result with success status and summary
        
    Example:
        result = await run_cdp_only(
            "Search for PraisonAI on Google",
            url="https://google.com"
        )
    """
    agent = CDPBrowserAgent(
        port=port,
        model=model,
        max_steps=max_steps,
        verbose=verbose
    )
    return await agent.run(goal, url)

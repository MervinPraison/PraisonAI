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
    
    Features:
        - Retry Logic: Automatic retry with alternative selectors on failures
        - Session Recording: Full action logging for debugging
        - Screenshot Analysis: Vision-based element detection (optional)
        - Hybrid Mode: Automatic engine switching based on task
    """
    
    def __init__(
        self,
        port: int = 9222,
        model: str = "gpt-4o-mini",
        max_steps: int = 15,
        verbose: bool = False,
        max_retries: int = 3,
        enable_vision: bool = False,
        record_session: bool = True,
        screenshot_dir: Optional[str] = None,
    ):
        """Initialize CDP Browser Agent.
        
        Args:
            port: Chrome debug port
            model: LLM model to use
            max_steps: Maximum automation steps
            verbose: Enable verbose logging
            max_retries: Max retries per action on failure
            enable_vision: Enable vision-based element detection
            record_session: Log all actions to session database
            screenshot_dir: Directory to save screenshots (optional)
        """
        self.port = port
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        self.max_retries = max_retries
        self.enable_vision = enable_vision
        self.record_session = record_session
        self.screenshot_dir = screenshot_dir
        self.ws = None
        self._message_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._session_manager = None
        self._current_session_id: Optional[str] = None
        self._total_retries = 0
    
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
        """Get current page state via CDP.
        
        Enhanced element extraction includes:
        - Actual href values for links
        - Multiple selector strategies per element
        - aria-label and data attributes
        - Text content for text-based fallback
        """
        # Get URL and title
        result = await self._send("Runtime.evaluate", {
            "expression": "JSON.stringify({url: location.href, title: document.title})"
        })
        info = json.loads(result.get("result", {}).get("value", "{}"))
        
        # Enhanced interactive elements extraction
        elements_js = """
        (() => {
            const selectors = 'a, button, input, textarea, select, [onclick], [role="button"], [role="link"], [tabindex="0"]';
            const elements = [];
            document.querySelectorAll(selectors).forEach((el, i) => {
                if (el.offsetParent === null) return; // Skip hidden
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                
                // Get text content
                const text = (el.textContent || el.placeholder || el.value || el.ariaLabel || '').trim().slice(0, 80);
                
                // Build multiple selector strategies (priority order)
                const selectorStrategies = [];
                
                // 1. ID (highest precision)
                if (el.id) {
                    selectorStrategies.push('#' + el.id);
                }
                
                // 2. Name attribute
                if (el.name) {
                    selectorStrategies.push(`${el.tagName.toLowerCase()}[name="${el.name}"]`);
                }
                
                // 3. Data-testid or data-id (common testing patterns)
                if (el.dataset.testid) {
                    selectorStrategies.push(`[data-testid="${el.dataset.testid}"]`);
                }
                if (el.dataset.id) {
                    selectorStrategies.push(`[data-id="${el.dataset.id}"]`);
                }
                
                // 4. Aria-label (accessibility)
                if (el.ariaLabel) {
                    selectorStrategies.push(`[aria-label="${el.ariaLabel}"]`);
                }
                
                // 5. Link with href
                if (el.tagName === 'A' && el.href) {
                    // Use partial href match for stability
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('javascript:')) {
                        selectorStrategies.push(`a[href="${href}"]`);
                    }
                }
                
                // 6. First class name (less precise but common)
                if (el.className && typeof el.className === 'string') {
                    const firstClass = el.className.split(' ')[0];
                    if (firstClass && !/^[0-9]/.test(firstClass)) {
                        selectorStrategies.push(`${el.tagName.toLowerCase()}.${firstClass}`);
                    }
                }
                
                elements.push({
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    text: text,
                    // Provide the best selector (first in priority list)
                    selector: selectorStrategies[0] || '',
                    // Also provide all strategies for fallback
                    selectors: selectorStrategies,
                    // Include actual href for links
                    href: el.tagName === 'A' ? el.href : null,
                    // For form elements
                    placeholder: el.placeholder || '',
                    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
                });
            });
            return elements.slice(0, 50); // Increased limit for better coverage
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
        import os
        
        # Initialize session recording
        if self.record_session:
            from .sessions import SessionManager
            self._session_manager = SessionManager()
            session = self._session_manager.create_session(goal, {"engine": "cdp", "model": self.model})
            self._current_session_id = session["session_id"]
            if self.verbose:
                logger.info(f"Session ID: {self._current_session_id}")
        
        # Setup screenshot directory
        if self.screenshot_dir:
            os.makedirs(self.screenshot_dir, exist_ok=True)
        
        self._total_retries = 0
        
        try:
            # Connect to Chrome
            logger.info(f"Connecting to Chrome on port {self.port}")
            await self._connect_to_page(start_url)
            
            # Create browser agent - use vision model if enabled
            agent_model = self.model
            if self.enable_vision and "gpt" in self.model.lower():
                agent_model = "gpt-4o"  # Upgrade to vision-capable model
            agent = BrowserAgent(model=agent_model, max_steps=self.max_steps, verbose=self.verbose)
            
            # Main automation loop
            for step in range(self.max_steps):
                # Get page state
                state = await self._get_page_state()
                
                if self.verbose:
                    logger.info(f"Step {step}: {state.url}")
                
                # Update session URL
                if self.record_session and self._session_manager:
                    self._session_manager.update_session(self._current_session_id, current_url=state.url)
                
                # Capture screenshot if enabled
                screenshot_path = None
                screenshot_base64 = None
                if self.screenshot_dir or self.enable_vision:
                    try:
                        result = await self._send("Runtime.evaluate", {
                            "expression": "JSON.stringify({width: window.innerWidth, height: window.innerHeight})"
                        })
                        screenshot_result = await self._send("Page.captureScreenshot", {"format": "png"})
                        if screenshot_result:
                            screenshot_base64 = screenshot_result.get("data", "")
                            if self.screenshot_dir:
                                screenshot_path = os.path.join(
                                    self.screenshot_dir, 
                                    f"step_{step:03d}.png"
                                )
                                import base64
                                with open(screenshot_path, "wb") as f:
                                    f.write(base64.b64decode(screenshot_base64))
                    except Exception as e:
                        logger.debug(f"Screenshot capture failed: {e}")
                
                # Build observation
                observation = {
                    "task": goal,
                    "original_goal": goal,
                    "url": state.url,
                    "title": state.title,
                    "elements": state.elements,
                    "step_number": step,
                }
                
                # Add screenshot for vision analysis if enabled
                if self.enable_vision and screenshot_base64:
                    observation["screenshot"] = screenshot_base64
                
                # Get action from agent
                action = agent.process_observation(observation)
                action = normalize_action(action)
                
                if self.verbose:
                    logger.info(f"  Action: {action.get('action')} | Done: {action.get('done')}")
                
                # Check for completion
                if action.get("done"):
                    # Record final step
                    if self.record_session and self._session_manager:
                        self._session_manager.add_step(
                            self._current_session_id,
                            step + 1,
                            observation={"url": state.url, "title": state.title},
                            action=action,
                            thought=action.get("thought", ""),
                            action_result={"success": True},
                            success=True,
                            screenshot_path=screenshot_path,
                        )
                        self._session_manager.update_session(
                            self._current_session_id, 
                            status="completed"
                        )
                    
                    return {
                        "success": True,
                        "summary": action.get("summary", "Task completed"),
                        "steps": step + 1,
                        "final_url": state.url,
                        "session_id": self._current_session_id,
                        "total_retries": self._total_retries,
                    }
                
                # Execute action with retry logic (multi-strategy)
                result = None
                retry_count = 0
                action_success = False
                original_action = action.copy()
                
                for attempt in range(self.max_retries + 1):
                    result = await self._execute_action(action)
                    
                    if result.get("success"):
                        action_success = True
                        break
                    
                    # Retry with alternative strategies
                    retry_count += 1
                    self._total_retries += 1
                    
                    if attempt < self.max_retries:
                        logger.warning(f"Action failed (attempt {attempt + 1}), retrying: {result.get('error')}")
                        
                        # Strategy 1: Try text-based selection
                        if attempt == 0:
                            text_content = original_action.get("value", "") or action.get("thought", "")
                            if text_content:
                                # Find element by text in current page state
                                matching_element = None
                                for el in state.elements:
                                    if text_content.lower() in (el.get("text", "") or "").lower():
                                        matching_element = el
                                        break
                                if matching_element and matching_element.get("selector"):
                                    action["selector"] = matching_element["selector"]
                                    logger.info(f"  Retry: Using text-matched selector: {action['selector']}")
                        
                        # Strategy 2: Try alternative selectors from element data
                        elif attempt == 1:
                            selector = original_action.get("selector", "")
                            # Search for this selector in elements and get fallback
                            for el in state.elements:
                                if el.get("selector") == selector and el.get("selectors"):
                                    if len(el["selectors"]) > 1:
                                        action["selector"] = el["selectors"][1]
                                        logger.info(f"  Retry: Using fallback selector: {action['selector']}")
                                        break
                        
                        # Strategy 3: Use href for link clicks
                        elif attempt == 2:
                            if original_action.get("action") == "click":
                                for el in state.elements:
                                    if el.get("href") and el.get("text", "").lower() in original_action.get("thought", "").lower():
                                        action["action"] = "navigate"
                                        action["url"] = el["href"]
                                        logger.info(f"  Retry: Converting click to navigate: {action['url']}")
                                        break
                        
                        await asyncio.sleep(0.5)
                    else:
                        logger.warning(f"Action failed after {self.max_retries + 1} attempts: {result.get('error')}")
                
                # Record step
                if self.record_session and self._session_manager:
                    self._session_manager.add_step(
                        self._current_session_id,
                        step + 1,
                        observation={"url": state.url, "title": state.title, "element_count": len(state.elements)},
                        action=action,
                        thought=action.get("thought", ""),
                        action_result=result,
                        success=action_success,
                        retry_count=retry_count,
                        screenshot_path=screenshot_path,
                    )
                
                await asyncio.sleep(1)  # Brief pause between steps
            
            # Max steps reached
            if self.record_session and self._session_manager:
                self._session_manager.update_session(
                    self._current_session_id,
                    status="failed",
                    error="Max steps reached"
                )
            
            return {
                "success": False,
                "error": "Max steps reached",
                "steps": self.max_steps,
                "session_id": self._current_session_id,
                "total_retries": self._total_retries,
            }
            
        except Exception as e:
            # Record failure
            if self.record_session and self._session_manager:
                self._session_manager.update_session(
                    self._current_session_id,
                    status="failed",
                    error=str(e)
                )
            raise
            
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
    max_retries: int = 3,
    enable_vision: bool = False,
    record_session: bool = True,
    screenshot_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Run browser agent using direct CDP (no extension required).
    
    Args:
        goal: Task to accomplish
        url: Starting URL
        model: LLM model to use
        port: Chrome debug port
        max_steps: Maximum automation steps
        verbose: Enable verbose logging
        max_retries: Max retries per action
        enable_vision: Enable vision-based analysis
        record_session: Log to session database
        screenshot_dir: Save screenshots to directory
        
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
        verbose=verbose,
        max_retries=max_retries,
        enable_vision=enable_vision,
        record_session=record_session,
        screenshot_dir=screenshot_dir,
    )
    return await agent.run(goal, url)


async def run_hybrid(
    goal: str,
    url: str = "https://www.google.com",
    model: str = "gpt-4o-mini",
    max_steps: int = 15,
    verbose: bool = False,
    prefer_extension: bool = True,
) -> Dict[str, Any]:
    """Run browser agent with automatic engine selection (Hybrid Mode).
    
    Automatically selects the best engine based on:
    - Extension availability (checks if bridge server is running)
    - CDP availability (checks Chrome on port 9222)
    - Task complexity (simple navigation vs complex interaction)
    
    Args:
        goal: Task to accomplish
        url: Starting URL
        model: LLM model to use
        max_steps: Maximum automation steps
        verbose: Enable verbose logging
        prefer_extension: Prefer extension mode when available
        
    Returns:
        Result with success status, summary, and engine used
        
    Example:
        result = await run_hybrid(
            "Search for PraisonAI on Google",
            url="https://google.com"
        )
    """
    engine_used = "cdp"
    
    # Check if extension bridge server is available
    extension_available = False
    if prefer_extension:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8765/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    extension_available = resp.status == 200
        except Exception:
            pass
    
    # Check if CDP is available
    cdp_available = False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:9222/json", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                cdp_available = resp.status == 200
    except Exception:
        pass
    
    if verbose:
        logger.info(f"Engine availability - Extension: {extension_available}, CDP: {cdp_available}")
    
    # Select engine based on availability and preference
    if prefer_extension and extension_available:
        engine_used = "extension"
        if verbose:
            logger.info("Using Extension mode via bridge server")
        
        # Run via extension bridge
        try:
            from .server import run_browser_agent
            result = await run_browser_agent(goal=goal, url=url, model=model)
            result["engine"] = "extension"
            return result
        except Exception as e:
            logger.warning(f"Extension mode failed, falling back to CDP: {e}")
    
    if cdp_available:
        engine_used = "cdp"
        if verbose:
            logger.info("Using CDP mode")
        
        agent = CDPBrowserAgent(
            port=9222,
            model=model,
            max_steps=max_steps,
            verbose=verbose,
            max_retries=3,
            record_session=True,
        )
        result = await agent.run(goal, url)
        result["engine"] = "cdp"
        return result
    
    # Last resort: try Playwright if available
    try:
        from .playwright_agent import PlaywrightBrowserAgent
        if verbose:
            logger.info("Using Playwright mode (headless)")
        
        agent = PlaywrightBrowserAgent(
            model=model,
            max_steps=max_steps,
            headless=True,
        )
        result = await agent.run(goal, url)
        result["engine"] = "playwright"
        return result
    except ImportError:
        pass
    
    return {
        "success": False,
        "error": "No browser engine available. Start Chrome with --remote-debugging-port=9222 or run the extension bridge server.",
        "engine": None,
    }

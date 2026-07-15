"""CDP Utilities - Direct CDP control without extension.

Provides utility functions for browser interaction via Chrome DevTools Protocol.
These mirror Antigravity's browser tools:
- get_pages / list_browser_pages
- get_dom / browser_get_dom  
- read_page / read_browser_page
- get_console / capture_browser_console_logs
- execute_js / execute_browser_javascript

Usage:
    from praisonai.browser.cdp_utils import (
        get_pages, get_dom, read_page, get_console, execute_js
    )
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger("praisonai.browser.cdp_utils")


@dataclass
class PageInfo:
    """Information about a browser page/tab."""
    id: str
    url: str
    title: str
    type: str
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "type": self.type,
            "description": self.description,
        }


async def get_pages(port: int = 9222) -> List[PageInfo]:
    """List all browser pages/tabs.
    
    Equivalent to Antigravity's list_browser_pages.
    
    Args:
        port: Chrome debug port
        
    Returns:
        List of PageInfo objects
        
    Example:
        pages = await get_pages()
        for page in pages:
            print(f"{page.id[:8]}  {page.title}  {page.url}")
    """
    try:
        import aiohttp
    except ImportError:
        raise ImportError("aiohttp required: pip install aiohttp")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:{port}/json") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Chrome not responding on port {port}")
                targets = await resp.json()
        
        pages = []
        for t in targets:
            pages.append(PageInfo(
                id=t.get("id", ""),
                url=t.get("url", ""),
                title=t.get("title", ""),
                type=t.get("type", ""),
                description=t.get("description", ""),
            ))
        return pages
    except Exception as e:
        logger.error(f"Failed to get pages: {e}")
        raise


async def _connect_to_page(page_id: str, port: int = 9222):
    """Connect to a specific page via WebSocket."""
    try:
        import aiohttp
        import websockets
    except ImportError:
        raise ImportError("Required: pip install aiohttp websockets")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://localhost:{port}/json") as resp:
            targets = await resp.json()
    
    page = next((t for t in targets if t.get("id") == page_id), None)
    if not page:
        raise ValueError(f"Page not found: {page_id}")
    
    ws_url = page.get("webSocketDebuggerUrl")
    if not ws_url:
        raise ValueError(f"Page has no WebSocket URL: {page_id}")
    
    return await websockets.connect(ws_url)


async def execute_js(
    page_id: str,
    code: str,
    port: int = 9222,
    await_promise: bool = True,
) -> Any:
    """Execute JavaScript in a browser page.
    
    Equivalent to Antigravity's execute_browser_javascript.
    
    Args:
        page_id: Page ID from get_pages()
        code: JavaScript code to execute
        port: Chrome debug port
        await_promise: If True, await promise results
        
    Returns:
        Result of JavaScript execution
        
    Example:
        result = await execute_js(page_id, "document.title")
        # "Google"
    """
    ws = await _connect_to_page(page_id, port)
    try:
        msg_id = 1
        await ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": code,
                "returnByValue": True,
                "awaitPromise": await_promise,
            }
        }))
        
        response = json.loads(await ws.recv())
        if "error" in response:
            raise RuntimeError(f"CDP error: {response['error']}")
        
        result = response.get("result", {}).get("result", {})
        if result.get("type") == "undefined":
            return None
        return result.get("value", result)
    finally:
        await ws.close()


async def get_dom(
    page_id: str,
    port: int = 9222,
    depth: int = 4,
) -> Dict[str, Any]:
    """Get DOM tree from a browser page.
    
    Equivalent to Antigravity's browser_get_dom.
    
    Args:
        page_id: Page ID from get_pages()
        port: Chrome debug port
        depth: How deep to traverse DOM tree
        
    Returns:
        DOM tree as nested dict
        
    Example:
        dom = await get_dom(page_id)
        print(dom["nodeName"])  # "#document"
    """
    ws = await _connect_to_page(page_id, port)
    try:
        # Enable DOM
        await ws.send(json.dumps({"id": 1, "method": "DOM.enable"}))
        await ws.recv()
        
        # Get document
        await ws.send(json.dumps({"id": 2, "method": "DOM.getDocument", "params": {"depth": depth}}))
        response = json.loads(await ws.recv())
        
        if "error" in response:
            raise RuntimeError(f"CDP error: {response['error']}")
        
        return response.get("result", {}).get("root", {})
    finally:
        await ws.close()


async def read_page(
    page_id: str,
    port: int = 9222,
) -> str:
    """Read page content as text.
    
    Equivalent to Antigravity's read_browser_page.
    
    Args:
        page_id: Page ID from get_pages()
        port: Chrome debug port
        
    Returns:
        Page text content
        
    Example:
        content = await read_page(page_id)
        print(content[:100])
    """
    # Use JavaScript to extract text
    return await execute_js(
        page_id,
        """
        (function() {
            // Get main content, falling back to body
            const main = document.querySelector('main') || 
                         document.querySelector('article') ||
                         document.querySelector('#content') ||
                         document.body;
            
            // Clone to avoid modifying page
            const clone = main.cloneNode(true);
            
            // Remove scripts, styles, hidden elements
            clone.querySelectorAll('script, style, noscript, [hidden]').forEach(el => el.remove());
            
            // Get text, clean up whitespace
            return clone.textContent.replace(/\\s+/g, ' ').trim().slice(0, 10000);
        })()
        """,
        port=port,
    )


async def get_console(
    page_id: str,
    port: int = 9222,
    timeout: float = 2.0,
) -> List[Dict[str, str]]:
    """Get console logs from a browser page.
    
    Equivalent to Antigravity's capture_browser_console_logs.
    
    Args:
        page_id: Page ID from get_pages()
        port: Chrome debug port
        timeout: How long to capture logs
        
    Returns:
        List of log entries with level and text
        
    Example:
        logs = await get_console(page_id)
        for log in logs:
            print(f"[{log['level']}] {log['text']}")
    """
    ws = await _connect_to_page(page_id, port)
    logs = []
    try:
        # Enable Console
        await ws.send(json.dumps({"id": 1, "method": "Console.enable"}))
        await ws.recv()
        
        # Enable Runtime for more detailed logs
        await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
        await ws.recv()
        
        # Collect logs for timeout duration
        import time
        start = time.time()
        while time.time() - start < timeout:
            try:
                # Non-blocking receive with short timeout
                import asyncio
                response = await asyncio.wait_for(ws.recv(), timeout=0.2)
                data = json.loads(response)
                
                method = data.get("method", "")
                params = data.get("params", {})
                
                if method == "Console.messageAdded":
                    msg = params.get("message", {})
                    logs.append({
                        "level": msg.get("level", "log"),
                        "text": msg.get("text", ""),
                    })
                elif method == "Runtime.consoleAPICalled":
                    args = params.get("args", [])
                    text = " ".join(str(a.get("value", a.get("description", ""))) for a in args)
                    logs.append({
                        "level": params.get("type", "log"),
                        "text": text,
                    })
            except asyncio.TimeoutError:
                continue
        
        return logs
    finally:
        await ws.close()


async def wait_for_element(
    page_id: str,
    selector: str,
    port: int = 9222,
    timeout: float = 10.0,
    poll_interval: float = 0.5,
) -> bool:
    """Wait for an element to appear on the page.
    
    Args:
        page_id: Page ID from get_pages()
        selector: CSS selector to wait for
        port: Chrome debug port
        timeout: Maximum wait time in seconds
        poll_interval: How often to check
        
    Returns:
        True if element found, False if timeout
    """
    import time
    start = time.time()
    
    while time.time() - start < timeout:
        result = await execute_js(
            page_id,
            f"!!document.querySelector('{selector}')",
            port=port,
        )
        if result:
            return True
        await asyncio.sleep(poll_interval)
    
    return False


# Synchronous wrappers for CLI usage
def get_pages_sync(port: int = 9222) -> List[PageInfo]:
    """Synchronous wrapper for get_pages."""
    return asyncio.run(get_pages(port))


def execute_js_sync(page_id: str, code: str, port: int = 9222) -> Any:
    """Synchronous wrapper for execute_js."""
    return asyncio.run(execute_js(page_id, code, port))


def get_dom_sync(page_id: str, port: int = 9222, depth: int = 4) -> Dict[str, Any]:
    """Synchronous wrapper for get_dom."""
    return asyncio.run(get_dom(page_id, port, depth))


def read_page_sync(page_id: str, port: int = 9222) -> str:
    """Synchronous wrapper for read_page."""
    return asyncio.run(read_page(page_id, port))


def get_console_sync(page_id: str, port: int = 9222, timeout: float = 2.0) -> List[Dict[str, str]]:
    """Synchronous wrapper for get_console."""
    return asyncio.run(get_console(page_id, port, timeout))

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

# Suppress verbose LiteLLM and HTTP client debug logs
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


# Site-specific fallback selectors for common websites
GOOGLE_SEARCH_SELECTORS = [
    'textarea[name="q"]',
    'input[name="q"]',
    '#APjFqb',
    '[aria-label="Search"]',
    'input[type="text"]',
    'textarea[title="Search"]',
]

GOOGLE_SUBMIT_SELECTORS = [
    'input[name="btnK"]',
    'button[type="submit"]',
    '[aria-label="Google Search"]',
    'input[value="Google Search"]',
]

# Cookie consent dialog selectors - these dialogs block interaction
GOOGLE_CONSENT_SELECTORS = [
    # English
    'button:has-text("Accept all")',  # Not valid CSS, but we use text matching
    'button:has-text("Reject all")',
    # Fallback to aria-label and button text content matching via JS
    '[aria-label="Accept all"]',
    '[aria-label="Reject all"]',
    # Common button patterns in Google consent
    'button[jsname="b3VHJd"]',  # "Accept all" button jsname
    'button[jsname="cOuczf"]',  # "Reject all" button jsname
    # Div-based buttons (Google uses divs with role="button")
    '[role="button"][aria-label*="Accept"]',
    '[role="button"][aria-label*="Reject"]',
]

# Generic consent/cookie dialog patterns for other sites
GENERIC_CONSENT_SELECTORS = [
    # Common consent button patterns
    'button[id*="accept"]',
    'button[id*="consent"]',
    'button[class*="accept"]',
    'button[class*="consent"]',
    '[data-testid*="accept"]',
    '[data-testid*="consent"]',
    # GDPR-specific
    '#onetrust-accept-btn-handler',
    '.cc-accept',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
    # Common text-based (will use JS text matching)
    'button:has-text("I agree")',
    'button:has-text("Got it")',
    'button:has-text("OK")',
]


@dataclass
class CDPPageState:
    """Page state captured via CDP."""
    url: str
    title: str
    elements: List[Dict[str, Any]]
    viewport: Dict[str, int]
    overlay_info: Optional[Dict[str, Any]] = None  # Info about blocking overlays/dialogs


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
        debug: bool = False,
        record_video: bool = False,
        video_fps: int = 5,
        verify_actions: bool = True,
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
            debug: Enable debug mode with detailed logging
            record_video: Enable real-time video recording via CDP screencast
            video_fps: Frames per second for video recording (default 5)
            verify_actions: Verify actions with before/after screenshots (default True)
        """
        self.port = port
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        self.max_retries = max_retries
        self.enable_vision = enable_vision
        self.record_session = record_session
        self.screenshot_dir = screenshot_dir
        self.debug = debug
        self.record_video = record_video
        self.video_fps = video_fps
        self.verify_actions = verify_actions
        self.ws = None
        self._message_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._session_manager = None
        self._current_session_id: Optional[str] = None
        self._total_retries = 0
        self._action_history: List[Dict[str, Any]] = []  # Track actions for stuck detection
        self._last_url: str = ""  # Track URL changes
        self._video_encoder = None  # FFmpegVideoEncoder instance
        self._screencast_active = False
    
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
        
        # Find an existing page target
        # Accept even chrome:// pages like newtab since we'll navigate away
        page = None
        for t in targets:
            if t.get("type") == "page":
                url = t.get("url", "")
                # Skip extension pages but allow newtab and other regular pages
                if url.startswith("chrome-extension://"):
                    continue
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
        - Overlay/modal detection for consent dialogs
        - Prioritized consent button extraction
        """
        # Get URL and title
        result = await self._send("Runtime.evaluate", {
            "expression": "JSON.stringify({url: location.href, title: document.title})"
        })
        info = json.loads(result.get("result", {}).get("value", "{}"))
        
        # Enhanced interactive elements extraction with overlay detection
        elements_js = """
        (() => {
            const result = { elements: [], overlay: null };
            
            // Detect blocking overlay/modal (cookie consent, etc.)
            const overlaySelectors = [
                '[role="dialog"]',
                '[role="alertdialog"]',
                '[aria-modal="true"]',
                '.consent-modal',
                '.cookie-consent',
                '#consent',
                '[class*="consent"]',
                '[class*="cookie-banner"]',
                '[class*="cookie-notice"]',
                '[id*="consent"]',
                // Google-specific consent
                'div[jsname="cpjPV"]',
                'div[data-g-class="modal"]',
            ];
            
            for (const sel of overlaySelectors) {
                try {
                    const overlay = document.querySelector(sel);
                    if (overlay && overlay.offsetParent !== null) {
                        const rect = overlay.getBoundingClientRect();
                        if (rect.width > 200 && rect.height > 100) {
                            result.overlay = {
                                detected: true,
                                type: 'consent_dialog',
                                selector: sel,
                                text: overlay.textContent?.slice(0, 200) || ''
                            };
                            break;
                        }
                    }
                } catch(e) {}
            }
            
            // Check for consent-related keywords in page
            const pageText = document.body?.textContent?.toLowerCase() || '';
            const hasConsentKeywords = ['cookie', 'consent', 'accept all', 'reject all', 'before you continue'].some(
                kw => pageText.includes(kw)
            );
            if (hasConsentKeywords && !result.overlay) {
                result.overlay = { detected: true, type: 'possible_consent', selector: null, text: 'Consent keywords detected' };
            }
            
            // Find consent buttons FIRST (prioritize these)
            const consentButtonSelectors = [
                'button',
                '[role="button"]',
                'div[tabindex="0"]',
            ];
            
            const consentKeywords = ['accept all', 'reject all', 'accept', 'agree', 'i agree', 'consent', 'got it', 'ok', 'allow'];
            const consentButtons = [];
            
            for (const sel of consentButtonSelectors) {
                document.querySelectorAll(sel).forEach(el => {
                    if (el.offsetParent === null) return;
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;
                    
                    const text = (el.textContent || el.ariaLabel || '').trim().toLowerCase();
                    const isConsent = consentKeywords.some(kw => text.includes(kw));
                    
                    if (isConsent) {
                        // Build selector for this consent button
                        let bestSelector = '';
                        if (el.id) bestSelector = '#' + el.id;
                        else if (el.ariaLabel) bestSelector = `[aria-label="${el.ariaLabel}"]`;
                        else if (el.getAttribute('jsname')) bestSelector = `[jsname="${el.getAttribute('jsname')}"]`;
                        else if (el.className && typeof el.className === 'string') {
                            const cls = el.className.split(' ')[0];
                            if (cls) bestSelector = `${el.tagName.toLowerCase()}.${cls}`;
                        }
                        
                        consentButtons.push({
                            index: -1, // Will be set later
                            tag: el.tagName.toLowerCase(),
                            type: 'consent_button',
                            text: (el.textContent || '').trim().slice(0, 80),
                            selector: bestSelector,
                            selectors: [bestSelector].filter(Boolean),
                            href: null,
                            placeholder: '',
                            rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                            isConsentButton: true
                        });
                    }
                });
            }
            
            // Now get regular elements
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
                
                // 5. jsname (Google-specific)
                const jsname = el.getAttribute('jsname');
                if (jsname) {
                    selectorStrategies.push(`[jsname="${jsname}"]`);
                }
                
                // 6. Link with href
                if (el.tagName === 'A' && el.href) {
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('javascript:')) {
                        selectorStrategies.push(`a[href="${href}"]`);
                    }
                }
                
                // 7. First class name (less precise but common)
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
                    selector: selectorStrategies[0] || '',
                    selectors: selectorStrategies,
                    href: el.tagName === 'A' ? el.href : null,
                    placeholder: el.placeholder || '',
                    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
                });
            });
            
            // If overlay detected, put consent buttons first
            if (result.overlay?.detected && consentButtons.length > 0) {
                // Reindex and prepend consent buttons
                consentButtons.forEach((btn, idx) => btn.index = idx);
                elements.forEach((el, idx) => el.index = consentButtons.length + idx);
                result.elements = [...consentButtons, ...elements].slice(0, 60);
            } else {
                result.elements = elements.slice(0, 50);
            }
            
            return result;
        })()
        """
        result = await self._send("Runtime.evaluate", {
            "expression": f"JSON.stringify({elements_js})",
            "returnByValue": True
        })
        page_data = json.loads(result.get("result", {}).get("value", "{}"))
        elements = page_data.get("elements", [])
        overlay_info = page_data.get("overlay")
        
        # Log overlay detection in debug mode
        if self.debug and overlay_info and overlay_info.get("detected"):
            logger.info(f"[DEBUG] Overlay/dialog detected: {overlay_info.get('type')} - {overlay_info.get('selector')}")
        
        # Get viewport
        result = await self._send("Runtime.evaluate", {
            "expression": "JSON.stringify({width: window.innerWidth, height: window.innerHeight})"
        })
        viewport = json.loads(result.get("result", {}).get("value", "{}"))
        
        return CDPPageState(
            url=info.get("url", ""),
            title=info.get("title", ""),
            elements=elements,
            viewport=viewport,
            overlay_info=overlay_info
        )
    
    def _is_stuck(self, current_url: str) -> bool:
        """Detect if agent is stuck in a loop.
        
        Returns True if:
        - Same URL for 3+ steps with failures
        - Same selector attempted 3+ times
        - No URL change in 5+ steps
        """
        if len(self._action_history) < 3:
            return False
        
        last_3 = self._action_history[-3:]
        
        # Check for same selector 3 times
        selectors = [a.get("selector") for a in last_3 if a.get("selector")]
        if len(selectors) >= 3 and len(set(selectors)) == 1:
            if self.debug:
                logger.info(f"[DEBUG] Stuck: Same selector 3 times: {selectors[0]}")
            return True
        
        # Check for 3 consecutive failures
        failures = sum(1 for a in last_3 if not a.get("success", True))
        if failures >= 3:
            if self.debug:
                logger.info("[DEBUG] Stuck: 3 consecutive failures")
            return True
        
        # Check for no URL change in 5+ steps
        if len(self._action_history) >= 5:
            last_5_urls = [a.get("url") for a in self._action_history[-5:]]
            if len(set(last_5_urls)) == 1 and last_5_urls[0] == current_url:
                # Only stuck if we've had failures
                recent_failures = sum(1 for a in self._action_history[-5:] if not a.get("success", True))
                if recent_failures >= 2:
                    if self.debug:
                        logger.info("[DEBUG] Stuck: Same URL for 5 steps with failures")
                    return True
        
        return False
    
    def _format_action_history(self) -> str:
        """Format action history as readable text for LLM context.
        
        Returns:
            Human-readable summary of previous actions with success/failure status.
        """
        if not self._action_history:
            return "No previous actions taken."
        
        lines = ["Previous actions in this session:"]
        for i, a in enumerate(self._action_history[-10:]):
            status = "✓" if a.get("success", True) else "✗"
            action = a.get("action", "unknown")
            selector = a.get("selector", "")
            if selector and len(selector) > 25:
                selector = selector[:25] + "..."
            text = a.get("text", "")
            if text and len(text) > 20:
                text = text[:20] + "..."
            
            # Build concise step description
            if action == "type" and text:
                desc = f'{action}("{text}")'
            elif selector:
                desc = f'{action}({selector})'
            else:
                desc = action
            
            lines.append(f"  {i+1}. {status} {desc}")
        
        return "\n".join(lines)
    
    def _get_site_specific_selector(self, action: Dict, url: str, overlay_info: Optional[Dict] = None) -> Optional[str]:
        """Get site-specific fallback selector for common websites.
        
        Args:
            action: Current action dict
            url: Current page URL
            overlay_info: Overlay detection info from page state
            
        Returns:
            Fallback selector to try, or None
        """
        action_type = action.get("action", "").lower()
        
        # PRIORITY 1: If overlay/consent dialog detected, return consent button selector
        if overlay_info and overlay_info.get("detected"):
            if self.debug:
                logger.info(f"[DEBUG] Overlay detected, trying consent button selectors")
            # Return first available consent button selector for clicking
            if "google.com" in url:
                for selector in GOOGLE_CONSENT_SELECTORS:
                    if self.debug:
                        logger.info(f"[DEBUG] Trying Google consent selector: {selector}")
                    # Skip pseudo-selectors that aren't valid CSS
                    if ":has-text" not in selector:
                        return selector
            else:
                for selector in GENERIC_CONSENT_SELECTORS:
                    if self.debug:
                        logger.info(f"[DEBUG] Trying generic consent selector: {selector}")
                    if ":has-text" not in selector:
                        return selector
        
        # PRIORITY 2: Google-specific selectors for normal actions
        if "google.com" in url:
            if action_type == "type":
                # Try Google search box selectors
                for selector in GOOGLE_SEARCH_SELECTORS:
                    if self.debug:
                        logger.info(f"[DEBUG] Trying Google selector: {selector}")
                    return selector
            elif action_type == "click" and "search" in action.get("thought", "").lower():
                # Try Google submit button selectors
                for selector in GOOGLE_SUBMIT_SELECTORS:
                    if self.debug:
                        logger.info(f"[DEBUG] Trying Google submit selector: {selector}")
                    return selector
        
        return None
    
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
    
    async def _start_screencast(self, output_dir: str) -> bool:
        """Start CDP screencast for real-time video recording.
        
        Args:
            output_dir: Directory to save video output
            
        Returns:
            True if screencast started successfully
        """
        if not self.record_video:
            return False
        
        try:
            from .video import FFmpegVideoEncoder
            import os
            
            os.makedirs(output_dir, exist_ok=True)
            video_path = os.path.join(output_dir, "recording.webm")
            
            self._video_encoder = FFmpegVideoEncoder(
                output_path=video_path,
                fps=self.video_fps,
                width=1280,
                height=720,
            )
            
            if not self._video_encoder.available:
                logger.warning("FFmpeg not available, falling back to screenshot-based recording")
                self._video_encoder = None
                return False
            
            if not self._video_encoder.start():
                self._video_encoder = None
                return False
            
            # Start CDP screencast
            await self._send("Page.startScreencast", {
                "format": "jpeg",
                "quality": 80,
                "maxWidth": 1280,
                "maxHeight": 720,
                "everyNthFrame": max(1, 60 // self.video_fps),  # Sample from 60fps
            })
            
            self._screencast_active = True
            if self.debug:
                logger.info(f"[DEBUG] Started video recording to {video_path}")
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to start screencast: {e}")
            return False
    
    async def _handle_screencast_frame(self, frame_data: str, session_id: int) -> None:
        """Handle incoming screencast frame.
        
        Args:
            frame_data: Base64-encoded image data
            session_id: Frame session ID for acknowledgment
        """
        if not self._screencast_active or not self._video_encoder:
            return
        
        try:
            import base64
            
            # Decode and write frame
            image_bytes = base64.b64decode(frame_data)
            self._video_encoder.write_frame(image_bytes)
            
            # Acknowledge frame to continue receiving
            await self._send("Page.screencastFrameAck", {"sessionId": session_id})
            
        except Exception as e:
            if self.debug:
                logger.warning(f"Failed to handle screencast frame: {e}")
    
    async def _capture_screencast_frame(self) -> None:
        """Capture a single screencast frame (for polling mode)."""
        if not self._screencast_active or not self._video_encoder:
            return
        
        try:
            result = await self._send("Page.captureScreenshot", {"format": "jpeg", "quality": 80})
            if result and result.get("data"):
                import base64
                image_bytes = base64.b64decode(result["data"])
                self._video_encoder.write_frame(image_bytes)
        except Exception as e:
            if self.debug:
                logger.warning(f"Failed to capture frame: {e}")
    
    async def _stop_screencast(self) -> Optional[str]:
        """Stop CDP screencast and finalize video.
        
        Returns:
            Path to output video if successful
        """
        video_path = None
        
        try:
            if self._screencast_active:
                await self._send("Page.stopScreencast", {})
                self._screencast_active = False
                
            if self._video_encoder:
                video_path = self._video_encoder.finish()
                if video_path and self.debug:
                    logger.info(f"[DEBUG] Video saved: {video_path}")
                self._video_encoder = None
                
        except Exception as e:
            logger.warning(f"Error stopping screencast: {e}")
        
        return video_path
    
    async def _capture_vision_screenshot(self, name_prefix: str = "step") -> Optional[str]:
        """Capture screenshot for LLM vision analysis.
        
        This method captures a high-quality screenshot that will be sent to the LLM
        for visual understanding of the current page state.
        
        Args:
            name_prefix: Prefix for debug logging
            
        Returns:
            Base64-encoded PNG image data, or None if capture fails
        """
        try:
            result = await self._send("Page.captureScreenshot", {
                "format": "png",
                "quality": 100,
                "captureBeyondViewport": False,  # Only visible viewport
            })
            
            if result and result.get("data"):
                if self.debug:
                    logger.info(f"[DEBUG] Vision screenshot captured: {name_prefix}")
                return result["data"]
            
            return None
            
        except Exception as e:
            if self.debug:
                logger.warning(f"[DEBUG] Vision screenshot failed ({name_prefix}): {e}")
            return None
    
    async def _verify_action_success(
        self, 
        action: Dict[str, Any], 
        screenshot_before: Optional[str], 
        screenshot_after: Optional[str],
        expected_change: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify action success by comparing before/after screenshots with LLM.
        
        Uses vision-capable LLM to analyze whether the action produced the expected
        visual change on the page.
        
        Args:
            action: The action that was executed
            screenshot_before: Base64 screenshot before action
            screenshot_after: Base64 screenshot after action
            expected_change: Optional description of expected change
            
        Returns:
            Dict with verification result: {success: bool, confidence: float, reason: str}
        """
        if not screenshot_before or not screenshot_after:
            return {"success": True, "confidence": 0.5, "reason": "No screenshots for verification"}
        
        # Skip verification if LLM doesn't support vision
        if "gpt" not in self.model.lower() or "o" not in self.model.lower():
            return {"success": True, "confidence": 0.5, "reason": "Vision not supported by model"}
        
        try:
            # Use LiteLLM for verification
            from litellm import completion
            
            action_type = action.get("action", "unknown")
            action_detail = action.get("text", action.get("selector", ""))
            
            verification_prompt = f"""Compare these two browser screenshots (before and after an action) and verify if the action succeeded.

ACTION PERFORMED: {action_type}
{"ACTION DETAIL: " + action_detail if action_detail else ""}
{"EXPECTED CHANGE: " + expected_change if expected_change else ""}

Analyze both images and determine:
1. Did the page change visually after the action?
2. Is the change consistent with what the action should have done?
3. Are there any error messages or unexpected states?

Respond in this exact JSON format:
{{"success": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""

            response = completion(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": verification_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{screenshot_before}"}
                            },
                            {
                                "type": "image_url", 
                                "image_url": {"url": f"data:image/png;base64,{screenshot_after}"}
                            },
                        ],
                    }
                ],
                max_tokens=200,
            )
            
            import json
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                # Handle markdown code blocks
                if "```" in result_text:
                    result_text = result_text.split("```")[1]
                    if result_text.startswith("json"):
                        result_text = result_text[4:]
                
                result = json.loads(result_text.strip())
                
                if self.debug:
                    logger.info(f"[DEBUG] Action verification: success={result.get('success')}, confidence={result.get('confidence')}")
                
                return {
                    "success": result.get("success", True),
                    "confidence": result.get("confidence", 0.5),
                    "reason": result.get("reason", "")
                }
                
            except json.JSONDecodeError:
                # Fallback: check if response contains "success" or "failed"
                success = "success" in result_text.lower() and "fail" not in result_text.lower()
                return {"success": success, "confidence": 0.5, "reason": result_text[:100]}
                
        except Exception as e:
            if self.debug:
                logger.warning(f"[DEBUG] Action verification error: {e}")
            return {"success": True, "confidence": 0.3, "reason": f"Verification error: {e}"}
    
    async def _wait_for_stable_frame(self, max_wait: float = 2.0, stability_threshold: float = 0.3) -> Optional[str]:
        """Wait for page to stabilize and capture stable screenshot.
        
        Captures multiple screenshots and waits until the page stops changing
        (useful after navigation or dynamic content loading).
        
        Args:
            max_wait: Maximum seconds to wait for stability
            stability_threshold: Time with no changes to consider stable
            
        Returns:
            Base64 screenshot of stable page, or latest if timeout
        """
        import time
        import hashlib
        
        start_time = time.time()
        last_hash = None
        last_stable_time = start_time
        latest_screenshot = None
        
        while (time.time() - start_time) < max_wait:
            try:
                screenshot = await self._capture_vision_screenshot("stable_check")
                
                if screenshot:
                    latest_screenshot = screenshot
                    
                    # Hash screenshot to detect changes
                    current_hash = hashlib.md5(screenshot[:1000].encode()).hexdigest()
                    
                    if current_hash == last_hash:
                        # Page hasn't changed
                        if (time.time() - last_stable_time) >= stability_threshold:
                            if self.debug:
                                logger.info("[DEBUG] Page stable, captured stable frame")
                            return screenshot
                    else:
                        # Page changed, reset stable timer
                        last_hash = current_hash
                        last_stable_time = time.time()
                
                await asyncio.sleep(0.1)  # Small delay between checks
                
            except Exception as e:
                if self.debug:
                    logger.warning(f"[DEBUG] Stable frame check error: {e}")
                break
        
        if self.debug:
            logger.info("[DEBUG] Page stability timeout, using latest frame")
        
        return latest_screenshot
    
    # Frame buffer for continuous screencast mode
    _latest_screencast_frame: Optional[str] = None
    _frame_buffer: List[str] = []
    _max_frame_buffer: int = 10
    
    async def _handle_screencast_frame_for_vision(self, frame_data: str, session_id: int) -> None:
        """Handle incoming screencast frame for both video encoding and vision buffer.
        
        Maintains a rolling buffer of recent frames for stable frame detection.
        
        Args:
            frame_data: Base64-encoded image data
            session_id: Frame session ID for acknowledgment
        """
        # Store latest frame for quick access
        self._latest_screencast_frame = frame_data
        
        # Add to buffer (rolling)
        if len(self._frame_buffer) >= self._max_frame_buffer:
            self._frame_buffer.pop(0)
        self._frame_buffer.append(frame_data)
        
        # Also handle for video encoding
        await self._handle_screencast_frame(frame_data, session_id)
    
    def _get_latest_vision_frame(self) -> Optional[str]:
        """Get the most recent screencast frame for vision analysis.
        
        Returns:
            Latest base64 frame from screencast buffer, or None
        """
        return self._latest_screencast_frame

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
        
        # Get profiler if enabled
        try:
            from .profiling import get_profiler
            profiler = get_profiler()
        except ImportError:
            profiler = None
        
        try:
            # Connect to Chrome
            logger.info(f"Connecting to Chrome on port {self.port}")
            await self._connect_to_page(start_url)
            
            # Create browser agent - use vision model if enabled
            agent_model = self.model
            if self.enable_vision and "gpt" in self.model.lower():
                agent_model = "gpt-4o"  # Upgrade to vision-capable model
            agent = BrowserAgent(model=agent_model, max_steps=self.max_steps, verbose=self.verbose)
            
            # Reset action history for this run
            self._action_history = []
            
            # Start video recording if enabled - use screenshot_dir for output
            if self.record_video and self.screenshot_dir:
                await self._start_screencast(self.screenshot_dir)
                if self.debug:
                    logger.info(f"[DEBUG] Video recording enabled, output dir: {self.screenshot_dir}")
            
            # Main automation loop
            for step in range(self.max_steps):
                # Track step start time for profiling
                import time as _time
                step_start = _time.perf_counter()
                
                # Start profiler step context if enabled
                step_ctx = profiler.step(step) if profiler else None
                if step_ctx:
                    step_ctx.__enter__()
                
                # Capture video frame (polling mode for reliable capture)
                if self._screencast_active:
                    await self._capture_screencast_frame()
                # Get page state
                state = await self._get_page_state()
                
                if self.verbose or self.debug:
                    logger.info(f"Step {step}: {state.url}")
                
                if self.debug:
                    logger.info(f"[DEBUG] Elements found: {len(state.elements)}")
                    for i, el in enumerate(state.elements[:5]):
                        logger.info(f"[DEBUG]   [{i}] {el.get('tag')} - {el.get('text', '')[:30]} - {el.get('selector', '')}")
                
                # Update session URL
                if self.record_session and self._session_manager:
                    self._session_manager.update_session(self._current_session_id, current_url=state.url)
                
                # Capture screenshot if enabled (with profiling)
                screenshot_path = None
                screenshot_base64 = None
                screenshot_start = _time.perf_counter()
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
                screenshot_duration = _time.perf_counter() - screenshot_start
                
                # Build observation with action history and overlay info
                observation = {
                    "task": goal,
                    "original_goal": goal,
                    "url": state.url,
                    "title": state.title,
                    "elements": state.elements,
                    "step_number": step,
                    "action_history": self._action_history[-10:],  # Raw for parsing
                    "action_summary": self._format_action_history(),  # Readable for LLM
                    "overlay_info": state.overlay_info,  # Pass overlay detection info
                    "max_steps": self.max_steps,
                    "steps_remaining": self.max_steps - step,
                    "mode": "cdp",  # Technology mode: cdp or extension
                    "vision_enabled": self.enable_vision,
                }
                
                # Add last action error if available
                if self._action_history and not self._action_history[-1].get("success", True):
                    observation["last_action_error"] = self._action_history[-1].get("error", "Previous action failed")
                
                # Add screenshot for vision analysis if enabled
                if self.enable_vision and screenshot_base64:
                    observation["screenshot"] = screenshot_base64
                
                # Check if agent is stuck (repeated same-URL actions with failures)  
                if self._is_stuck(state.url):
                    if self.debug:
                        logger.info("[DEBUG] Agent appears stuck, adding extra context")
                    # Add stuck context to observation for LLM
                    observation["stuck_detected"] = True
                    observation["last_action_error"] = "Agent appears stuck. Try a different approach or action."
                
                # FULLY DYNAMIC: Let LLM decide ALL actions including consent handling
                # LLM has access to: screenshot, elements (including consent buttons), action history
                llm_start = _time.perf_counter()
                action = agent.process_observation(observation)
                action = normalize_action(action)
                llm_duration = _time.perf_counter() - llm_start
                
                if self.verbose or self.debug:
                    logger.info(f"  Action: {action.get('action')} | Done: {action.get('done')}")
                
                if self.debug:
                    logger.info(f"[DEBUG] Full action: {action}")
                
                # Check for completion
                if action.get("done"):
                    # Record final step timing before returning
                    if profiler and step_ctx:
                        if profiler._current_step:
                            profiler._current_step.llm_time = llm_duration
                            profiler._current_step.screenshot_time = screenshot_duration
                        step_ctx.__exit__(None, None, None)
                    
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
                action_start = _time.perf_counter()
                result = None
                retry_count = 0
                action_success = False
                original_action = action.copy()
                
                # Phase 1: Capture BEFORE screenshot for action verification (if enabled)
                screenshot_before = None
                if self.verify_actions and self.enable_vision:
                    screenshot_before = await self._capture_vision_screenshot(f"before_step_{step}")
                    if self.debug and screenshot_before:
                        logger.info(f"[DEBUG] <SCREENSHOT_BEFORE step={step}> captured ({len(screenshot_before)//1024}KB)")
                elif self.debug and not self.verify_actions:
                    logger.info("[DEBUG] Skipping BEFORE screenshot (--no-verify)")
                
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
                
                # Track action execution time
                action_duration = _time.perf_counter() - action_start
                
                # Phase 2: Capture AFTER screenshot and verify action success (if enabled)
                screenshot_after = None
                verification_result = None
                if self.verify_actions and self.enable_vision and action_success:
                    # Wait for page to stabilize before capturing AFTER screenshot
                    screenshot_after = await self._wait_for_stable_frame(max_wait=1.5, stability_threshold=0.3)
                    if self.debug and screenshot_after:
                        logger.info(f"[DEBUG] <SCREENSHOT_AFTER step={step}> captured ({len(screenshot_after)//1024}KB)")
                    
                    # Save AFTER screenshot to file if directory specified
                    if screenshot_after and self.screenshot_dir:
                        try:
                            import base64
                            after_path = os.path.join(
                                self.screenshot_dir,
                                f"step_{step:03d}_after.png"
                            )
                            with open(after_path, "wb") as f:
                                f.write(base64.b64decode(screenshot_after))
                        except Exception as e:
                            logger.debug(f"Failed to save AFTER screenshot: {e}")
                    
                    # Verify action success using LLM vision
                    if screenshot_before and screenshot_after:
                        verification_result = await self._verify_action_success(
                            action=action,
                            screenshot_before=screenshot_before,
                            screenshot_after=screenshot_after,
                            expected_change=action.get("thought", "")
                        )
                        
                        if self.debug:
                            logger.info(f"[DEBUG] Action verification: {verification_result}")
                        
                        # If verification fails with high confidence, log warning
                        if verification_result and not verification_result.get("success") and verification_result.get("confidence", 0) > 0.7:
                            logger.warning(f"Action may have failed: {verification_result.get('reason', 'Unknown')}")
                elif self.debug and not self.verify_actions:
                    logger.info("[DEBUG] Skipping AFTER screenshot and verification (--no-verify)")
                
                # Track action in history for stuck detection and reporting
                import time as time_module
                self._action_history.append({
                    "action": action.get("action"),
                    "selector": action.get("selector"),
                    "text": action.get("text") or action.get("value"),  # For type actions
                    "thought": action.get("thought", ""),
                    "url": state.url,
                    "success": action_success,
                    "step": step,
                    "timestamp": time_module.time(),
                    "vision_used": self.enable_vision and screenshot_base64 is not None,
                    "verified": verification_result.get("success") if verification_result else None,
                    "verification_confidence": verification_result.get("confidence") if verification_result else None,
                })
                
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
                
                # Record step timing to profiler if enabled
                step_duration = _time.perf_counter() - step_start
                if profiler and step_ctx:
                    # Update step profile with detailed timings
                    if profiler._current_step:
                        profiler._current_step.llm_time = llm_duration if 'llm_duration' in dir() else 0
                        profiler._current_step.screenshot_time = screenshot_duration if 'screenshot_duration' in dir() else 0
                        profiler._current_step.action_time = action_duration if 'action_duration' in dir() else 0
                    # Exit step context to record total time
                    step_ctx.__exit__(None, None, None)
                
                # Brief pause between steps - capture video frames during wait
                if self._screencast_active:
                    # Capture multiple frames for smooth video (5 frames in 1 second)
                    for _ in range(5):
                        await self._capture_screencast_frame()
                        await asyncio.sleep(0.2)
                else:
                    await asyncio.sleep(0.5)  # Reduced pause for faster iteration
            
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
            # Stop video recording if active
            video_path = await self._stop_screencast()
            if video_path:
                logger.info(f"Video saved: {video_path}")
            
            # Generate session report
            if self._action_history and self.debug:
                try:
                    from .report import generate_session_report
                    import time
                    
                    generate_session_report(
                        action_history=self._action_history,
                        goal=goal,
                        success=len(self._action_history) > 0 and self._action_history[-1].get("success", False),
                        final_url=self._last_url,
                        duration_seconds=time.time() - (self._action_history[0].get("timestamp", time.time()) if self._action_history else time.time()),
                        tech_flags={
                            "cdp": True,
                            "vision": self.enable_vision,
                            "extension": False,
                        },
                    )
                except Exception as e:
                    if self.debug:
                        logger.warning(f"Report generation failed: {e}")
            
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
    debug: bool = False,
    record_video: bool = False,
    video_fps: int = 5,
    verify_actions: bool = True,
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
        debug: Enable debug mode with detailed logging
        record_video: Enable real-time video recording (requires FFmpeg)
        video_fps: Frames per second for video (default 5)
        verify_actions: Verify each action with before/after screenshots (default True)
        
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
        debug=debug,
        record_video=record_video,
        video_fps=video_fps,
        verify_actions=verify_actions,
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

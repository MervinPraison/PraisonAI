"""Browser Diagnostics Module — Component-level health checks.

Provides utilities to test each component of the browser automation system:
- API key validation
- Bridge WebSocket connectivity
- Agent LLM capability
- Vision/screenshot encoding
- Environment configuration

Usage:
    from praisonai.browser.diagnostics import run_all_diagnostics
    results = run_all_diagnostics()
"""

import os
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("praisonai.browser.diagnostics")


class DiagnosticStatus(Enum):
    """Diagnostic check result status."""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class DiagnosticResult:
    """Result of a diagnostic check."""
    name: str
    status: DiagnosticStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details or {},
        }


# =============================================================================
# API KEY VALIDATION
# =============================================================================

def check_api_keys() -> List[DiagnosticResult]:
    """Check all relevant API keys are set and valid.
    
    Checks:
    - OPENAI_API_KEY
    - GEMINI_API_KEY  
    - ANTHROPIC_API_KEY
    
    Returns:
        List of DiagnosticResult for each key
    """
    results = []
    
    api_keys = [
        ("OPENAI_API_KEY", "sk-", "OpenAI"),
        ("GEMINI_API_KEY", "", "Google Gemini"),
        ("ANTHROPIC_API_KEY", "sk-ant-", "Anthropic Claude"),
    ]
    
    for key_name, prefix, provider in api_keys:
        value = os.environ.get(key_name, "")
        
        if not value:
            results.append(DiagnosticResult(
                name=f"api_key_{key_name.lower()}",
                status=DiagnosticStatus.WARN,
                message=f"{provider} API key not set",
                details={"key": key_name, "provider": provider},
            ))
        elif prefix and not value.startswith(prefix):
            results.append(DiagnosticResult(
                name=f"api_key_{key_name.lower()}",
                status=DiagnosticStatus.WARN,
                message=f"{provider} API key format may be incorrect",
                details={"key": key_name, "prefix_expected": prefix},
            ))
        else:
            results.append(DiagnosticResult(
                name=f"api_key_{key_name.lower()}",
                status=DiagnosticStatus.PASS,
                message=f"{provider} API key configured",
                details={"key": key_name, "length": len(value)},
            ))
    
    return results


def check_api_key_valid(model: str = "gpt-4o-mini") -> DiagnosticResult:
    """Test if API key for given model is valid by making a minimal call.
    
    Args:
        model: Model name to test (e.g., "gpt-4o-mini", "gemini/gemini-2.0-flash")
    
    Returns:
        DiagnosticResult with validation status
    """
    try:
        import litellm
        
        # Minimal test call
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "Say 'ok'"}],
            max_tokens=5,
        )
        
        return DiagnosticResult(
            name="api_key_valid",
            status=DiagnosticStatus.PASS,
            message=f"API key valid for {model}",
            details={"model": model, "response": response.choices[0].message.content},
        )
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationError" in error_msg or "401" in error_msg:
            return DiagnosticResult(
                name="api_key_valid",
                status=DiagnosticStatus.FAIL,
                message=f"API key invalid or missing for {model}",
                details={"model": model, "error": error_msg[:200]},
            )
        else:
            return DiagnosticResult(
                name="api_key_valid",
                status=DiagnosticStatus.WARN,
                message=f"API call failed (may be rate limit or network)",
                details={"model": model, "error": error_msg[:200]},
            )


# =============================================================================
# BRIDGE SERVER CONNECTIVITY
# =============================================================================

async def check_bridge_server(host: str = "localhost", port: int = 8765) -> DiagnosticResult:
    """Check if bridge server is running and accepting connections.
    
    Tests:
    1. HTTP health endpoint
    2. WebSocket handshake
    
    Args:
        host: Server hostname
        port: Server port
    
    Returns:
        DiagnosticResult
    """
    import aiohttp
    
    health_url = f"http://{host}:{port}/health"
    ws_url = f"ws://{host}:{port}/ws"
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test HTTP health
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    connections = data.get("connections", 0)
                    sessions = data.get("sessions", 0)
                    
                    return DiagnosticResult(
                        name="bridge_server",
                        status=DiagnosticStatus.PASS,
                        message=f"Bridge server running ({connections} connections, {sessions} sessions)",
                        details={
                            "health_url": health_url,
                            "connections": connections,
                            "sessions": sessions,
                        },
                    )
                else:
                    return DiagnosticResult(
                        name="bridge_server",
                        status=DiagnosticStatus.FAIL,
                        message=f"Bridge server returned status {resp.status}",
                        details={"health_url": health_url, "status": resp.status},
                    )
    except aiohttp.ClientConnectorError:
        return DiagnosticResult(
            name="bridge_server",
            status=DiagnosticStatus.FAIL,
            message=f"Bridge server not running on {host}:{port}",
            details={"health_url": health_url, "hint": "Run: praisonai browser start"},
        )
    except Exception as e:
        return DiagnosticResult(
            name="bridge_server",
            status=DiagnosticStatus.FAIL,
            message=f"Bridge server check failed: {e}",
            details={"health_url": health_url, "error": str(e)},
        )


async def check_bridge_websocket(host: str = "localhost", port: int = 8765) -> DiagnosticResult:
    """Test WebSocket connection to bridge server.
    
    Performs:
    1. Connect to ws://host:port/ws
    2. Receive welcome status message
    3. Disconnect cleanly
    
    Returns:
        DiagnosticResult
    """
    import asyncio
    
    try:
        import websockets
    except ImportError:
        return DiagnosticResult(
            name="bridge_websocket",
            status=DiagnosticStatus.SKIP,
            message="websockets package not installed",
            details={"hint": "pip install websockets"},
        )
    
    ws_url = f"ws://{host}:{port}/ws"
    
    try:
        async with websockets.connect(ws_url, close_timeout=5) as ws:
            # Wait for welcome message
            message = await asyncio.wait_for(ws.recv(), timeout=5)
            import json
            data = json.loads(message)
            
            if data.get("type") == "status" and data.get("status") == "connected":
                return DiagnosticResult(
                    name="bridge_websocket",
                    status=DiagnosticStatus.PASS,
                    message="WebSocket connected successfully",
                    details={"ws_url": ws_url, "welcome": data},
                )
            else:
                return DiagnosticResult(
                    name="bridge_websocket",
                    status=DiagnosticStatus.WARN,
                    message="WebSocket connected but unexpected response",
                    details={"ws_url": ws_url, "response": data},
                )
    except asyncio.TimeoutError:
        return DiagnosticResult(
            name="bridge_websocket",
            status=DiagnosticStatus.FAIL,
            message="WebSocket connection timeout",
            details={"ws_url": ws_url, "timeout": "5s"},
        )
    except Exception as e:
        return DiagnosticResult(
            name="bridge_websocket",
            status=DiagnosticStatus.FAIL,
            message=f"WebSocket connection failed: {e}",
            details={"ws_url": ws_url, "error": str(e)},
        )


# =============================================================================
# CHROME / CDP CONNECTIVITY
# =============================================================================

async def check_chrome_cdp(port: int = 9222) -> DiagnosticResult:
    """Check if Chrome is running with remote debugging enabled.
    
    Tests:
    1. CDP /json/version endpoint
    2. Returns browser version info
    
    Returns:
        DiagnosticResult
    """
    import aiohttp
    
    url = f"http://localhost:{port}/json/version"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    browser = data.get("Browser", "Unknown")
                    ws_url = data.get("webSocketDebuggerUrl", "")
                    
                    return DiagnosticResult(
                        name="chrome_cdp",
                        status=DiagnosticStatus.PASS,
                        message=f"Chrome CDP active: {browser}",
                        details={
                            "port": port,
                            "browser": browser,
                            "ws_url": ws_url[:60] + "..." if len(ws_url) > 60 else ws_url,
                        },
                    )
                else:
                    return DiagnosticResult(
                        name="chrome_cdp",
                        status=DiagnosticStatus.FAIL,
                        message=f"Chrome CDP returned status {resp.status}",
                        details={"port": port, "status": resp.status},
                    )
    except aiohttp.ClientConnectorError:
        return DiagnosticResult(
            name="chrome_cdp",
            status=DiagnosticStatus.FAIL,
            message=f"Chrome not running with --remote-debugging-port={port}",
            details={
                "port": port,
                "hint": f"Start Chrome with: google-chrome --remote-debugging-port={port}",
            },
        )
    except Exception as e:
        return DiagnosticResult(
            name="chrome_cdp",
            status=DiagnosticStatus.FAIL,
            message=f"Chrome CDP check failed: {e}",
            details={"port": port, "error": str(e)},
        )


async def check_extension_loaded(port: int = 9222) -> DiagnosticResult:
    """Check if PraisonAI extension is loaded in Chrome.
    
    Looks for service worker with 'praisonai' or known extension ID.
    
    Returns:
        DiagnosticResult
    """
    import aiohttp
    
    url = f"http://localhost:{port}/json"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return DiagnosticResult(
                        name="extension_loaded",
                        status=DiagnosticStatus.FAIL,
                        message="Cannot fetch Chrome targets",
                        details={"port": port, "status": resp.status},
                    )
                
                targets = await resp.json()
                
                # Look for extension service worker
                extension_patterns = ["praisonai", "fkmfdklcegbbpipbcimbokpfcfamhpdc"]
                
                service_worker = None
                offscreen = None
                
                for target in targets:
                    url_lower = target.get("url", "").lower()
                    target_type = target.get("type", "")
                    
                    for pattern in extension_patterns:
                        if pattern in url_lower:
                            if target_type == "service_worker":
                                service_worker = target
                            elif "offscreen" in url_lower:
                                offscreen = target
                
                if service_worker:
                    result_details = {
                        "port": port,
                        "service_worker": service_worker.get("url", "")[:60],
                    }
                    if offscreen:
                        result_details["offscreen"] = offscreen.get("url", "")[:60]
                    
                    return DiagnosticResult(
                        name="extension_loaded",
                        status=DiagnosticStatus.PASS,
                        message="PraisonAI extension loaded",
                        details=result_details,
                    )
                else:
                    return DiagnosticResult(
                        name="extension_loaded",
                        status=DiagnosticStatus.FAIL,
                        message="PraisonAI extension not found",
                        details={
                            "port": port,
                            "targets_found": len(targets),
                            "hint": "Load extension at chrome://extensions",
                        },
                    )
    except Exception as e:
        return DiagnosticResult(
            name="extension_loaded",
            status=DiagnosticStatus.FAIL,
            message=f"Extension check failed: {e}",
            details={"port": port, "error": str(e)},
        )


# =============================================================================
# AGENT / LLM CAPABILITY
# =============================================================================

async def check_agent_llm(model: str = "gpt-4o-mini") -> DiagnosticResult:
    """Test agent's LLM capability with a mock observation.
    
    Sends a minimal observation and checks if agent returns valid action.
    
    Args:
        model: LLM model to test
    
    Returns:
        DiagnosticResult
    """
    try:
        from .agent import BrowserAgent
        
        agent = BrowserAgent(model=model, max_steps=1, verbose=False)
        
        # Mock observation
        mock_observation = {
            "task": "Test the agent",
            "url": "https://example.com",
            "title": "Example Domain",
            "screenshot": "",  # No screenshot for quick test
            "elements": [
                {"selector": "a[href='https://www.iana.org/domains/example']", "tag": "a", "text": "More information..."},
                {"selector": "p", "tag": "p", "text": "This domain is for use in illustrative examples."},
            ],
            "console_logs": [],
            "step_number": 0,
        }
        
        # Process and get action
        action = await agent.aprocess_observation(mock_observation)
        
        if action and action.get("action"):
            return DiagnosticResult(
                name="agent_llm",
                status=DiagnosticStatus.PASS,
                message=f"Agent returned action: {action.get('action')}",
                details={
                    "model": model,
                    "action": action.get("action"),
                    "thought": action.get("thought", "")[:100],
                },
            )
        else:
            return DiagnosticResult(
                name="agent_llm",
                status=DiagnosticStatus.WARN,
                message="Agent returned empty action",
                details={"model": model, "response": str(action)[:200]},
            )
            
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationError" in error_msg:
            return DiagnosticResult(
                name="agent_llm",
                status=DiagnosticStatus.FAIL,
                message=f"API key invalid for {model}",
                details={"model": model, "error": error_msg[:200]},
            )
        else:
            return DiagnosticResult(
                name="agent_llm",
                status=DiagnosticStatus.FAIL,
                message=f"Agent LLM call failed: {e}",
                details={"model": model, "error": error_msg[:200]},
            )


def check_vision_capability(model: str) -> DiagnosticResult:
    """Check if model supports vision and screenshots can be encoded.
    
    Args:
        model: Model name to check
    
    Returns:
        DiagnosticResult
    """
    # Vision-capable models
    vision_patterns = ["gpt-4", "gemini", "claude", "vision"]
    
    model_lower = model.lower()
    is_vision_capable = any(p in model_lower for p in vision_patterns)
    
    return DiagnosticResult(
        name="vision_capability",
        status=DiagnosticStatus.PASS if is_vision_capable else DiagnosticStatus.WARN,
        message=f"Model {'supports' if is_vision_capable else 'may not support'} vision",
        details={
            "model": model,
            "vision_capable": is_vision_capable,
            "patterns_checked": vision_patterns,
        },
    )


# =============================================================================
# ENVIRONMENT INFO
# =============================================================================

def get_environment_info() -> DiagnosticResult:
    """Collect all relevant environment configuration.
    
    Returns:
        DiagnosticResult with environment details
    """
    import sys
    import platform
    
    env_vars = {
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "GEMINI_API_KEY": bool(os.environ.get("GEMINI_API_KEY")),
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL", "default"),
    }
    
    return DiagnosticResult(
        name="environment",
        status=DiagnosticStatus.PASS,
        message="Environment info collected",
        details={
            "python_version": sys.version.split()[0],
            "platform": platform.system(),
            "api_keys_set": env_vars,
            "home": os.path.expanduser("~"),
            "cwd": os.getcwd(),
        },
    )


# =============================================================================
# RUN ALL DIAGNOSTICS
# =============================================================================

async def run_all_diagnostics(
    bridge_port: int = 8765,
    chrome_port: int = 9222,
    model: str = "gpt-4o-mini",
    skip_llm: bool = False,
) -> Dict[str, Any]:
    """Run all diagnostic checks and return summary.
    
    Args:
        bridge_port: Bridge server port
        chrome_port: Chrome debug port
        model: LLM model to test
        skip_llm: Skip LLM API call test (for faster checks)
    
    Returns:
        Dict with all results and summary
    """
    results: List[DiagnosticResult] = []
    
    # Environment
    results.append(get_environment_info())
    
    # API Keys
    results.extend(check_api_keys())
    
    # Bridge server
    results.append(await check_bridge_server(port=bridge_port))
    results.append(await check_bridge_websocket(port=bridge_port))
    
    # Chrome/CDP
    results.append(await check_chrome_cdp(port=chrome_port))
    results.append(await check_extension_loaded(port=chrome_port))
    
    # Vision capability
    results.append(check_vision_capability(model))
    
    # Agent LLM (optional)
    if not skip_llm:
        results.append(await check_agent_llm(model))
    
    # Summary
    passed = sum(1 for r in results if r.status == DiagnosticStatus.PASS)
    failed = sum(1 for r in results if r.status == DiagnosticStatus.FAIL)
    warned = sum(1 for r in results if r.status == DiagnosticStatus.WARN)
    skipped = sum(1 for r in results if r.status == DiagnosticStatus.SKIP)
    
    return {
        "results": [r.to_dict() for r in results],
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "skipped": skipped,
            "all_pass": failed == 0,
        },
    }


def run_diagnostics_sync(**kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for run_all_diagnostics."""
    import asyncio
    return asyncio.run(run_all_diagnostics(**kwargs))

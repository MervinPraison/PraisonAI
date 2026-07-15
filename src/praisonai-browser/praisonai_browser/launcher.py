"""Browser Launcher — Launch Chrome with extension for CLI automation.

Enables running browser agent from CLI without manual sidepanel interaction.
"""

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("praisonai.browser.launcher")


def find_chrome_executable() -> Optional[str]:
    """Find Chrome/Chromium executable on the system."""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        # Chrome 137+ removed --load-extension for branded Chrome
        # Prioritize Chrome for Testing which still supports it
        home = os.path.expanduser("~")
        candidates = [
            # Chrome for Testing (supports --load-extension in Chrome 137+)
            os.path.join(home, ".praisonai/chrome-for-testing/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
            os.path.join(home, ".praisonai/chrome-for-testing/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
            # Chromium also supports --load-extension
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            # Fallback to branded Chrome (--load-extension may not work on 137+)
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        ]
    elif system == "Windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
    
    # Also check PATH
    for name in ["google-chrome", "chrome", "chromium", "chromium-browser"]:
        path = shutil.which(name)
        if path:
            candidates.insert(0, path)
    
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    
    return None


def find_extension_path() -> Optional[str]:
    """Find the PraisonAI Chrome extension dist folder."""
    # Check common locations
    candidates = [
        # Relative to current working directory
        "praisonai-chrome-extension/dist",
        "../praisonai-chrome-extension/dist",
        # Relative to home
        os.path.expanduser("~/praisonai-chrome-extension/dist"),
        # Relative to this file's package
        str(Path(__file__).parent.parent.parent.parent.parent / "praisonai-chrome-extension" / "dist"),
    ]
    
    for candidate in candidates:
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "manifest.json")):
            return os.path.abspath(candidate)
    
    return None


class BrowserLauncher:
    """Launch Chrome with PraisonAI extension and run goals.
    
    Example:
        launcher = BrowserLauncher()
        result = launcher.run("Search for PraisonAI", start_url="https://google.com")
    """
    
    # Default persistent profile path
    DEFAULT_PROFILE_PATH = os.path.expanduser("~/.praisonai/browser_profile")
    
    def __init__(
        self,
        extension_path: Optional[str] = None,
        chrome_path: Optional[str] = None,
        server_port: int = 8765,
        model: str = "gpt-4o-mini",
        max_steps: int = 20,
        verbose: bool = False,
        profile_path: Optional[str] = None,
        use_temp_profile: bool = False,
    ):
        """Initialize browser launcher.
        
        Args:
            extension_path: Path to extension dist folder
            chrome_path: Path to Chrome executable
            server_port: Port for WebSocket server
            model: LLM model to use
            max_steps: Maximum steps per session
            verbose: Enable verbose logging
            profile_path: Chrome profile path (default: ~/.praisonai/browser_profile)
            use_temp_profile: If True, use temp profile instead of persistent (deleted after run)
        """
        self.extension_path = extension_path or find_extension_path()
        self.chrome_path = chrome_path or find_chrome_executable()
        self.server_port = server_port
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        self.use_temp_profile = use_temp_profile
        
        # Default to persistent profile unless use_temp_profile is True
        if use_temp_profile:
            self.profile_path = None  # Will be set to temp dir later
        else:
            self.profile_path = profile_path or self.DEFAULT_PROFILE_PATH
        
        self._chrome_process: Optional[subprocess.Popen] = None
        self._server_process: Optional[subprocess.Popen] = None
        self._temp_profile: Optional[str] = None
        self._using_persistent_profile: bool = not use_temp_profile
        
        if not self.extension_path:
            raise ValueError(
                "Extension not found. Build it first with: "
                "cd praisonai-chrome-extension && npm run build"
            )
        
        if not self.chrome_path:
            raise ValueError(
                "Chrome/Chromium not found. Install Chrome or specify path with chrome_path."
            )
    
    def run(
        self,
        goal: str,
        start_url: str = "https://www.google.com",
        timeout: int = 120,
        headless: bool = False,
    ) -> dict:
        """Run browser agent with a goal.
        
        Args:
            goal: The task/goal to execute
            start_url: URL to start at
            timeout: Maximum time in seconds
            headless: Run in headless mode (experimental)
            
        Returns:
            dict with status and session info
        """
        try:
            return asyncio.run(self._run_async(goal, start_url, timeout, headless))
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            return {"status": "interrupted", "goal": goal}
        finally:
            self._cleanup()
    
    async def _run_async(
        self,
        goal: str,
        start_url: str,
        timeout: int,
        headless: bool,
    ) -> dict:
        """Async implementation of run."""
        import websockets
        import aiohttp
        
        # Check if extension is already connected
        async def check_existing_connection():
            """Check if an extension is already connected to server."""
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://localhost:{self.server_port}/health") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data.get("connections", 0) >= 1
            except Exception:
                pass
            return False
        
        extension_already_connected = await check_existing_connection()
        
        if extension_already_connected:
            logger.info("Extension already connected, using existing Chrome")
        else:
            # Use persistent profile if specified, otherwise create temp profile
            if self.profile_path:
                # Create persistent profile directory if it doesn't exist
                os.makedirs(self.profile_path, exist_ok=True)
                profile_dir = self.profile_path
                self._using_persistent_profile = True
                logger.info(f"Using persistent profile: {profile_dir}")
            else:
                # Create temp profile for Chrome
                self._temp_profile = tempfile.mkdtemp(prefix="praisonai_chrome_")
                profile_dir = self._temp_profile
            
            # Launch Chrome with extension
            logger.info(f"Launching Chrome with extension: {self.extension_path}")
            chrome_args = [
                self.chrome_path,
                f"--load-extension={self.extension_path}",
                f"--disable-extensions-except={self.extension_path}",  # Critical: only load our extension
                f"--user-data-dir={profile_dir}",
                "--enable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-popup-blocking",
                "--disable-translate",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-device-discovery-notifications",
                "--disable-features=HttpsUpgrades",
                start_url,
            ]
            
            if headless:
                chrome_args.insert(1, "--headless=new")
            
            self._chrome_process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        
        # Wait for extension to connect to server
        logger.info("Waiting for extension to connect...")
        import aiohttp
        
        async def wait_for_extension(max_wait=25):
            """Poll /health until 1+ connections (extension)."""
            health_url = f"http://localhost:{self.server_port}/health"
            start = time.time()
            while time.time() - start < max_wait:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(health_url) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                connections = data.get("connections", 0)
                                logger.debug(f"Server connections: {connections}")
                                if connections >= 1:  # Just need extension connected
                                    return True
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            return False
        
        # Give Chrome time to start, then wait for extension
        await asyncio.sleep(5)  # Initial Chrome startup
        extension_connected = await wait_for_extension()
        if not extension_connected:
            logger.warning("Extension did not connect in time, proceeding anyway")
        
        # Connect to the bridge server and send goal
        ws_url = f"ws://localhost:{self.server_port}/ws"
        
        try:
            async with websockets.connect(ws_url, ping_interval=30) as ws:
                # Start session - server will broadcast to extension
                await ws.send(
                    f'{{"type": "start_session", "goal": "{goal}", "model": "{self.model}"}}'
                )
                
                start_time = time.time()
                session_id = None
                
                while time.time() - start_time < timeout:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=10)
                        import json
                        data = json.loads(message)
                        
                        if data.get("type") == "status":
                            session_id = data.get("session_id")
                            status = data.get("status")
                            logger.info(f"Session {session_id}: {status}")
                            
                            if status in ("completed", "stopped", "failed"):
                                return {
                                    "status": status,
                                    "session_id": session_id,
                                    "goal": goal,
                                    "message": data.get("message", ""),
                                }
                        
                        elif data.get("type") == "action":
                            action = data.get("action")
                            if data.get("done"):
                                return {
                                    "status": "completed",
                                    "session_id": session_id,
                                    "goal": goal,
                                    "thought": data.get("thought", ""),
                                }
                            logger.info(f"Action: {action}")
                        
                        elif data.get("type") == "error":
                            logger.error(f"Error: {data.get('error')}")
                            return {
                                "status": "error",
                                "goal": goal,
                                "error": data.get("error"),
                            }
                    
                    except asyncio.TimeoutError:
                        continue
                
                return {
                    "status": "timeout",
                    "session_id": session_id,
                    "goal": goal,
                }
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return {
                "status": "error",
                "goal": goal,
                "error": str(e),
            }
    
    def _cleanup(self):
        """Clean up Chrome process and temp profile (preserves persistent profiles)."""
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
            self._chrome_process = None
        
        # Only delete temp profiles, preserve persistent profiles
        if self._temp_profile and os.path.exists(self._temp_profile) and not self._using_persistent_profile:
            try:
                shutil.rmtree(self._temp_profile)
            except Exception:
                pass
            self._temp_profile = None


"""Browser Server — FastAPI WebSocket server for Chrome Extension communication.

Bridges the Chrome Extension to PraisonAI agents for browser automation.
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger("praisonai.browser.server")


@dataclass
class ClientConnection:
    """Represents a connected WebSocket client."""
    websocket: object  # WebSocket instance
    session_id: Optional[str] = None
    connected_at: float = 0.0


class BrowserServer:
    """WebSocket server for browser automation.
    
    Handles communication between Chrome Extension and PraisonAI agents.
    
    Example:
        server = BrowserServer(port=8765)
        server.start()  # Blocks
        
        # Or run async
        await server.run_async()
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        model: str = "gpt-4o-mini",
        max_steps: int = 20,
        verbose: bool = False,
    ):
        """Initialize browser server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            model: LLM model for browser agent
            max_steps: Maximum steps per session
            verbose: Enable verbose logging
        """
        self.host = host
        self.port = port
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        
        self._app = None
        self._connections: Dict[str, ClientConnection] = {}
        self._agents: Dict[str, object] = {}  # BrowserAgent per session
        self._sessions = None  # SessionManager
        self._running = False
    
    def _get_app(self):
        """Create FastAPI app with WebSocket endpoint."""
        try:
            from fastapi import FastAPI, WebSocket, WebSocketDisconnect
            from fastapi.middleware.cors import CORSMiddleware
        except ImportError:
            raise ImportError(
                "fastapi is required. Install it with: pip install fastapi uvicorn"
            )
        
        if self._app is not None:
            return self._app
        
        app = FastAPI(
            title="PraisonAI Browser Server",
            description="WebSocket server for browser automation",
            version="1.0.0",
        )
        
        # Enable CORS for extension
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @app.get("/health")
        async def health():
            return {
                "status": "ok",
                "connections": len(self._connections),
                "sessions": len(self._agents),
            }
        
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self._handle_connection(websocket)
        
        self._app = app
        return app
    
    async def _handle_connection(self, websocket):
        """Handle a WebSocket connection."""
        from fastapi import WebSocket, WebSocketDisconnect
        import json
        import time
        import uuid
        
        await websocket.accept()
        
        # Create connection tracking
        conn_id = str(uuid.uuid4())[:8]
        conn = ClientConnection(
            websocket=websocket,
            connected_at=time.time(),
        )
        self._connections[conn_id] = conn
        
        logger.info(f"[SERVER][ENTRY] _handle_connection:server.py client_id={conn_id}, total_connections={len(self._connections)}")
        
        # Send welcome message
        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "message": "Connected to PraisonAI Browser Server",
            "session_id": "",
        })
        
        try:
            while True:
                # Receive message
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                    response = await self._process_message(message, conn)
                    if response:
                        await websocket.send_json(response)
                except json.JSONDecodeError as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Invalid JSON: {e}",
                        "code": "PARSE_ERROR",
                    })
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e),
                        "code": "PROCESSING_ERROR",
                    })
        
        except WebSocketDisconnect:
            logger.info(f"[SERVER][EXIT] _handle_connection:server.py client_id={conn_id} disconnected normally")
        except Exception as e:
            logger.error(f"[SERVER][ERROR] _handle_connection:server.py client_id={conn_id} error={e}")
        finally:
            # Cleanup
            if conn_id in self._connections:
                del self._connections[conn_id]
            if conn.session_id and conn.session_id in self._agents:
                del self._agents[conn.session_id]
    
    async def _process_message(
        self,
        message: Dict,
        conn: ClientConnection,
    ) -> Optional[Dict]:
        """Process incoming WebSocket message."""
        msg_type = message.get("type", "")
        logger.info(f"[SERVER][MSG] _process_message:server.py type={msg_type}, connections={len(self._connections)}")
        
        if msg_type == "start_session":
            print(f"[SERVER] start_session received, connections={len(self._connections)}", flush=True)
            logger.info(f"[SERVER][ROUTE] Routing start_session to _handle_start_session, connections={len(self._connections)}")
            return await self._handle_start_session(message, conn)
        
        elif msg_type == "observation":
            return await self._handle_observation(message, conn)
        
        elif msg_type == "stop_session":
            return await self._handle_stop_session(message, conn)
        
        elif msg_type == "ping":
            return {"type": "pong"}
        
        elif msg_type == "heartbeat":
            # Extension sends heartbeat every 20s to keep WebSocket alive
            return {"type": "heartbeat_ack", "status": "ok"}
        
        else:
            return {
                "type": "error",
                "error": f"Unknown message type: {msg_type}",
                "code": "UNKNOWN_TYPE",
            }
    
    async def _handle_start_session(
        self,
        message: Dict,
        conn: ClientConnection,
    ) -> Dict:
        """Start a new automation session."""
        from .agent import BrowserAgent
        from .sessions import SessionManager
        
        goal = message.get("goal", "")
        model = message.get("model", self.model)
        max_steps = message.get("max_steps", self.max_steps)
        
        logger.info(f"[SERVER][ENTRY] _handle_start_session:server.py goal='{goal[:50]}...', model={model}, max_steps={max_steps}")
        
        if not goal:
            logger.error(f"[SERVER][ERROR] _handle_start_session:server.py → Missing goal")
            return {
                "type": "error",
                "error": "Goal is required",
                "code": "MISSING_GOAL",
            }
        
        # Initialize session manager
        if self._sessions is None:
            self._sessions = SessionManager()
        
        # Create session
        logger.debug(f"[SERVER][CALL] SessionManager.create_session:server.py goal='{goal[:30]}...'")
        session = self._sessions.create_session(goal)
        session_id = session["session_id"]
        conn.session_id = session_id
        
        # Create agent for this session
        logger.debug(f"[SERVER][CALL] BrowserAgent.__init__:server.py model={model}, max_steps={max_steps}")
        agent = BrowserAgent(
            model=model,
            max_steps=max_steps,
            verbose=self.verbose,
        )
        self._agents[session_id] = agent
        
        logger.info(f"[SERVER][DATA] _handle_start_session:server.py session_id={session_id}, agent_model={agent.model}")
        
        # Send start_automation to ONE extension client (first available without a session)
        # Only send to ONE to prevent duplicate debugger attachment
        start_msg = {
            "type": "start_automation",
            "goal": goal,
            "session_id": session_id,
        }
        sent_to_extension = False
        
        logger.debug(f"[SERVER][SCAN] _handle_start_session:server.py checking {len(self._connections)} connections for available extension")
        
        # *** FIX: Aggressively clear ALL stale session_ids before looking ***
        # This handles crashed CLI runs that leave stale state
        for client_id, client_conn in self._connections.items():
            # Clear session_id on all connections that aren't the current CLI caller
            # This ensures fresh state for each new CLI run
            if client_conn != conn and client_conn.session_id:
                logger.info(f"Clearing stale session_id on client {client_id[:8]}")
                client_conn.session_id = None
        
        # First, log all connections for debugging
        logger.info(f"Looking for available extension. Connections: {len(self._connections)}")
        for client_id, client_conn in self._connections.items():
            has_session = "has session" if client_conn.session_id else "no session"
            is_caller = "caller" if client_conn == conn else "not caller"
            logger.debug(f"  Client {client_id[:8]}: {has_session}, {is_caller}")


        # Try to find an available extension
        logger.info(f"[DEBUG] Scanning {len(self._connections)} connections for available extension")
        logger.info(f"[DEBUG] Current conn id: {id(conn)}")
        for client_id, client_conn in self._connections.items():
            is_self = client_conn == conn
            is_same_id = id(client_conn) == id(conn)
            has_websocket = client_conn.websocket is not None
            has_session = client_conn.session_id is not None
            logger.info(f"[DEBUG] Client {client_id[:8]}: is_self={is_self}, same_id={is_same_id}, websocket={has_websocket}, session={has_session}, conn_id={id(client_conn)}")

            # Only send to extensions (not CLI) that don't have an active session
            print(f"[SERVER] Checking client {client_id[:8]}: conn!=self={client_conn != conn}, ws={client_conn.websocket is not None}, no_session={not client_conn.session_id}", flush=True)
            if client_conn != conn and client_conn.websocket and not client_conn.session_id:
                try:
                    print(f"[SERVER] SENDING start_automation to {client_id[:8]}", flush=True)
                    logger.info(f"[SERVER][START] _handle_start_session:server.py → Sending start_automation to extension {client_id[:8]}")
                    # Use send_text with JSON to ensure compatibility
                    import json as json_mod
                    await client_conn.websocket.send_text(json_mod.dumps(start_msg))
                    print(f"[SERVER] SENT start_automation successfully", flush=True)
                    # Set the extension's session_id so we can broadcast actions to CLI
                    client_conn.session_id = session_id
                    logger.info(f"[SERVER][START] start_automation sent successfully to {client_id[:8]}, session={session_id[:8]}")
                    sent_to_extension = True
                    break  # Only send to ONE extension
                except Exception as e:
                    logger.error(f"[SERVER][START] Failed to send start_automation to {client_id[:8]}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
        
        # *** FIX: If no extension found, it might have stale session_id - clear and retry ***
        if not sent_to_extension:
            logger.warning("[SERVER][START] No available extension found. Clearing stale session_ids and retrying...")

            for client_id, client_conn in self._connections.items():
                if client_conn != conn and client_conn.session_id:
                    logger.info(f"Clearing stale session_id on client {client_id[:8]}")
                    client_conn.session_id = None
            
            # Wait for extension to complete CDP cleanup
            import asyncio
            await asyncio.sleep(1.0)
            
            # Retry
            for client_id, client_conn in self._connections.items():
                if client_conn != conn and client_conn.websocket:
                    try:
                        await client_conn.websocket.send_json(start_msg)
                        client_conn.session_id = session_id
                        logger.info(f"Retry: Sent start_automation to extension {client_id[:8]}")
                        sent_to_extension = True
                        break
                    except Exception as e:
                        logger.error(f"Retry failed for {client_id}: {e}")
        
        return {
            "type": "status",
            "status": "running",
            "session_id": session_id,
            "message": f"Session started with goal: {goal}",
        }
    
    async def _handle_observation(
        self,
        message: Dict,
        conn: ClientConnection,
    ) -> Dict:
        """Process observation and return action."""
        import time
        start_time = time.time()
        
        step_number = message.get('step_number', 0)
        url = message.get('url', 'unknown')[:50]
        has_screenshot = bool(message.get('screenshot'))
        elements_count = len(message.get('elements', []))
        
        logger.info(f"[SERVER][ENTRY] _handle_observation:server.py step={step_number}, url='{url}...', screenshot={has_screenshot}, elements={elements_count}")
        
        session_id = message.get("session_id", conn.session_id)
        
        if not session_id or session_id not in self._agents:
            logger.error(f"[SERVER][ERROR] _handle_observation:server.py → No active session: session_id={session_id}, exists_in_agents={session_id in self._agents if session_id else False}")
            return {
                "type": "error",
                "error": "No active session",
                "code": "NO_SESSION",
            }
        
        agent = self._agents[session_id]
        logger.debug(f"[SERVER][DATA] _handle_observation:server.py agent_type={type(agent).__name__}, agent_model={getattr(agent, 'model', 'unknown')}")
        
        # Process observation through agent
        try:
            logger.debug(f"[SERVER][CALL] agent.aprocess_observation:server.py step={step_number}")
            action = await agent.aprocess_observation(message)
            elapsed = time.time() - start_time
            logger.info(f"[SERVER][RECV] agent.aprocess_observation:server.py → action={action.get('action', 'N/A')}, done={action.get('done', False)}, time={elapsed:.2f}s")
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[SERVER][ERROR] agent.aprocess_observation:server.py → {type(e).__name__}: {e}, time={elapsed:.2f}s")
            action = {
                "action": "wait",
                "thought": f"Error: {e}",
                "done": False,
                "error": str(e),
            }

        
        # Update session
        if self._sessions:
            step_number = message.get("step_number", 0)
            self._sessions.update_session(
                session_id,
                current_url=message.get("url", ""),
            )
            self._sessions.add_step(
                session_id,
                step_number,
                observation=message,
                action=action,
                thought=action.get("thought", ""),
            )
            
            # Check if done or max steps
            if action.get("done") or step_number >= self.max_steps:
                status = "completed" if action.get("done") else "stopped"
                self._sessions.update_session(session_id, status=status)
        
        # Build action response
        action_response = {
            "type": "action",
            "session_id": session_id,
            **action,
        }
        
        # Broadcast action to ALL clients that have this session
        # This includes CLI client that initiated the session
        logger.debug(f"[SERVER][SEND] _handle_observation:server.py broadcasting to {len(self._connections)} connections")
        for client_id, client_conn in self._connections.items():
            if client_conn.session_id == session_id and client_conn != conn:
                try:
                    await client_conn.websocket.send_json(action_response)
                    logger.debug(f"[SERVER][SEND] _handle_observation:server.py → sent to client {client_id[:8]}")
                except Exception as e:
                    logger.error(f"[SERVER][ERROR] broadcast:server.py → {e}")
        
        # Also send completion status if done
        if action.get("done") or message.get("step_number", 0) >= self.max_steps:
            status = "completed" if action.get("done") else "stopped"
            status_msg = {
                "type": "status",
                "status": status,
                "session_id": session_id,
                "message": action.get("thought", "Task complete"),
            }
            for client_id, client_conn in self._connections.items():
                if client_conn.session_id == session_id:
                    try:
                        await client_conn.websocket.send_json(status_msg)
                    except Exception:
                        pass
        
        return action_response
    
    async def _handle_stop_session(
        self,
        message: Dict,
        conn: ClientConnection,
    ) -> Dict:
        """Stop current session."""
        session_id = message.get("session_id", conn.session_id)
        
        if session_id:
            if session_id in self._agents:
                del self._agents[session_id]
            if self._sessions:
                self._sessions.update_session(session_id, status="stopped")
            
            # *** FIX: Clear session_id on ALL connections with this session ***
            # This allows subsequent sessions to find available extensions
            for client_id, client_conn in self._connections.items():
                if client_conn.session_id == session_id:
                    logger.info(f"Clearing session_id on client {client_id[:8]}")
                    client_conn.session_id = None
        
        return {
            "type": "status",
            "status": "stopped",
            "session_id": session_id or "",
            "message": "Session stopped",
        }
    
    def start(self):
        """Start the server (blocking)."""
        try:
            import uvicorn
        except ImportError:
            raise ImportError(
                "uvicorn is required. Install it with: pip install uvicorn"
            )
        
        app = self._get_app()
        self._running = True
        
        # Setup signal handlers
        def handle_signal(sig, frame):
            logger.info("Shutting down...")
            self._running = False
            sys.exit(0)
        
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        
        logger.info(f"Starting PraisonAI Browser Server on {self.host}:{self.port}")
        print(f"\n🌐 PraisonAI Browser Server")
        print(f"   WebSocket: ws://{self.host}:{self.port}/ws")
        print(f"   Health:    http://{self.host}:{self.port}/health")
        print(f"   Model:     {self.model}")
        print(f"\n   Press Ctrl+C to stop\n")
        
        uvicorn.run(
            app,
            host=self.host,
            port=self.port,
            log_level="info" if self.verbose else "warning",
        )
    
    async def run_async(self):
        """Run server asynchronously."""
        try:
            import uvicorn
        except ImportError:
            raise ImportError(
                "uvicorn is required. Install it with: pip install uvicorn"
            )
        
        app = self._get_app()
        self._running = True
        
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="info" if self.verbose else "warning",
        )
        server = uvicorn.Server(config)
        await server.serve()
    
    def stop(self):
        """Stop the server."""
        self._running = False
        
        # Cleanup sessions
        if self._sessions:
            for session_id in list(self._agents.keys()):
                self._sessions.update_session(session_id, status="stopped")
            self._sessions.close()
        
        self._agents.clear()
        self._connections.clear()


async def run_browser_agent(
    goal: str,
    url: str = "https://www.google.com",
    model: str = "gpt-4o-mini",
    max_steps: int = 20,
    timeout: float = 120.0,
    debug: bool = False,
    port: int = 8765,
) -> Dict:
    """Run browser agent via extension bridge server.
    
    This function connects to the bridge server WebSocket and sends
    goals to be executed by the Chrome extension.
    
    Args:
        goal: Task to accomplish
        url: Starting URL
        model: LLM model to use
        max_steps: Maximum steps
        timeout: Timeout in seconds
        debug: Enable debug logging
        port: Bridge server port
        
    Returns:
        Dict with success, summary, steps, etc.
        
    Example:
        result = await run_browser_agent(
            goal="Search for PraisonAI",
            url="https://google.com"
        )
    """
    import json
    import asyncio
    import uuid
    
    if debug:
        logger.setLevel(logging.DEBUG)
        logger.info(f"[DEBUG] run_browser_agent: goal='{goal}', url='{url}', model='{model}'")
    
    session_id = str(uuid.uuid4())
    result = {
        "success": False,
        "summary": "",
        "steps": 0,
        "error": "",
        "session_id": session_id,
        "engine": "extension",
    }
    
    try:
        import websockets
    except ImportError:
        result["error"] = "websockets package required. Install with: pip install websockets"
        logger.error(result["error"])
        return result
    
    ws_url = f"ws://localhost:{port}/ws"
    
    if debug:
        logger.info(f"[DEBUG] Connecting to bridge server at {ws_url}")
    
    try:
        async with websockets.connect(ws_url, close_timeout=10) as ws:
            if debug:
                logger.info(f"[DEBUG] Connected to bridge server")
            
            # Wait for welcome message
            welcome = await asyncio.wait_for(ws.recv(), timeout=5.0)
            welcome_data = json.loads(welcome)
            if debug:
                logger.info(f"[DEBUG] Welcome: {welcome_data}")
            
            # Start session
            start_msg = {
                "type": "start_session",
                "goal": goal,
                "url": url,
                "model": model,
                "max_steps": max_steps,
                "session_id": session_id,
            }
            
            if debug:
                logger.info(f"[DEBUG] Sending start_session: {start_msg}")
            
            await ws.send(json.dumps(start_msg))
            
            # Wait for session response
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            response_data = json.loads(response)
            
            if debug:
                logger.info(f"[DEBUG] Response: {response_data}")
            
            if response_data.get("type") == "error":
                result["error"] = response_data.get("error", "Unknown error")
                return result
            
            # Extract result
            result["success"] = response_data.get("status") == "completed"
            result["summary"] = response_data.get("summary", "")
            result["steps"] = response_data.get("steps", 0)
            result["final_url"] = response_data.get("final_url", "")
            
            if debug:
                logger.info(f"[DEBUG] Result: success={result['success']}, steps={result['steps']}")
            
            return result
            
    except asyncio.TimeoutError:
        result["error"] = f"Timeout after {timeout}s waiting for bridge server response"
        logger.error(result["error"])
        return result
    except ConnectionRefusedError:
        result["error"] = f"Cannot connect to bridge server at {ws_url}. Is it running?"
        logger.error(result["error"])
        return result
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Extension mode error: {e}")
        return result


async def run_browser_agent_with_progress(
    goal: str,
    url: str = "https://www.google.com",
    model: str = "gpt-4o-mini",
    max_steps: int = 20,
    timeout: float = 120.0,
    debug: bool = False,
    port: int = 8765,
    on_step: Optional[callable] = None,
) -> Dict:
    """Run browser agent via extension with progress callbacks.
    
    This function connects to the bridge server and waits for task completion
    by listening for all status updates and action responses.
    
    Args:
        goal: Task to accomplish
        url: Starting URL
        model: LLM model to use
        max_steps: Maximum steps
        timeout: Timeout in seconds
        debug: Enable debug logging
        port: Bridge server port
        on_step: Callback for step progress (receives step number)
        
    Returns:
        Dict with success, summary, steps, final_url, engine
    """
    import json
    import asyncio
    import time
    
    if debug:
        logger.setLevel(logging.DEBUG)
        logger.info(f"[Extension] Starting: goal='{goal[:50]}...', url='{url}'")
    
    result = {
        "success": False,
        "summary": "",
        "steps": 0,
        "error": "",
        "final_url": "",
        "engine": "extension",
    }
    
    try:
        import websockets
    except ImportError:
        result["error"] = "websockets package required. Install with: pip install websockets"
        return result
    
    ws_url = f"ws://localhost:{port}/ws"
    start_time = time.time()
    
    # Wait for extension to connect to bridge server before sending goal
    max_wait_for_extension = 15.0  # Wait up to 15 seconds for extension
    extension_connected = False
    
    try:
        import aiohttp
        wait_start = time.time()
        while time.time() - wait_start < max_wait_for_extension:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"http://localhost:{port}/health",
                        timeout=aiohttp.ClientTimeout(total=2)
                    ) as resp:
                        if resp.status == 200:
                            health = await resp.json()
                            connections = health.get("connections", 0)
                            if debug:
                                logger.debug(f"[Extension] Health: {connections} connections")
                            if connections >= 1:  # At least one extension connected
                                extension_connected = True
                                if debug:
                                    logger.info(f"[Extension] Extension connected!")
                                break
            except Exception as e:
                if debug:
                    logger.debug(f"[Extension] Health check: {e}")
            await asyncio.sleep(1.0)
        
        if not extension_connected:
            elapsed = int(time.time() - wait_start)
            result["error"] = f"Extension did not connect to bridge server within {elapsed}s"
            if debug:
                logger.warning(f"[Extension] No extension connected after {elapsed}s")
            return result
    except ImportError:
        if debug:
            logger.warning("[Extension] aiohttp not available, skipping extension check")
    
    try:
        async with websockets.connect(ws_url, close_timeout=10, ping_interval=30) as ws:
            if debug:
                logger.info(f"[Extension] Connected to bridge server")
            
            # Wait for welcome message
            welcome = await asyncio.wait_for(ws.recv(), timeout=5.0)
            welcome_data = json.loads(welcome)
            
            if welcome_data.get("type") == "status" and welcome_data.get("status") == "connected":
                if debug:
                    logger.info(f"[Extension] Received welcome")
            
            # Send start_session
            start_msg = {
                "type": "start_session",
                "goal": goal,
                "url": url,
                "model": model,
                "max_steps": max_steps,
            }
            await ws.send(json.dumps(start_msg))
            
            if debug:
                logger.info(f"[Extension] Sent start_session")
            
            session_id = None
            step_count = 0
            last_thought = ""
            session_start_time = time.time()  # Track start time for elapsed timestamps
            
            # Listen for messages until completion or timeout
            while time.time() - start_time < timeout:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    msg_type = data.get("type", "")
                    
                    if debug:
                        logger.debug(f"[Extension] Received: type={msg_type}, keys={list(data.keys())}")
                    
                    if msg_type == "status":
                        status = data.get("status", "")
                        session_id = data.get("session_id", session_id)
                        
                        if status == "running":
                            if debug:
                                logger.info(f"[Extension] Session {session_id[:8] if session_id else '?'}... started")
                        
                        elif status in ("completed", "stopped", "failed"):
                            result["success"] = status == "completed"
                            result["summary"] = data.get("message", last_thought)
                            result["steps"] = step_count
                            result["session_id"] = session_id
                            
                            if debug:
                                logger.info(f"[Extension] Task {status}: {result['summary'][:50]}...")
                            
                            # Try to get final URL
                            if not result["final_url"]:
                                result["final_url"] = url
                            
                            return result
                    
                    elif msg_type == "action":
                        step_count += 1
                        action = data.get("action", "unknown")
                        thought = data.get("thought", "")
                        done = data.get("done", False)
                        error = data.get("error", "")
                        selector = data.get("selector", "")
                        value = data.get("value", "")
                        
                        if thought:
                            last_thought = thought
                        
                        if on_step:
                            try:
                                on_step(step_count)
                            except Exception:
                                pass
                        
                        if debug:
                            # === SHOW FULL AGENT DECISION ===
                            # Calculate elapsed time from COMMAND start (not session start)
                            elapsed = time.time() - start_time
                            
                            # Action summary line with timestamp
                            action_info = f"[+{elapsed:.1f}s] Step {step_count}: {action}"
                            if selector:
                                selector_preview = selector[:40] + "..." if len(selector) > 40 else selector
                                action_info += f" → {selector_preview}"
                            if value:
                                value_preview = value[:30] + "..." if len(value) > 30 else value
                                action_info += f" = \"{value_preview}\""
                            action_info += f" (done={done})"
                            logger.info(action_info)
                            
                            # Show agent's thought process (WHY this decision)
                            if thought:
                                thought_preview = thought[:120] + "..." if len(thought) > 120 else thought
                                logger.debug(f"   💭 Thought: {thought_preview}")
                            
                            # === ANOMALY/ERROR DETECTION (CRITICAL!) ===
                            error_detected = data.get("error_detected")
                            if error_detected:
                                error_desc = data.get("error_description", "No description")
                                logger.warning(f"   ⚠️ ERROR DETECTED: {error_desc}")
                            
                            input_field_value = data.get("input_field_value")
                            if input_field_value:
                                logger.info(f"   📝 Input field shows: \"{input_field_value}\"")
                            
                            expected_vs_actual = data.get("expected_vs_actual")
                            if expected_vs_actual:
                                logger.warning(f"   ❌ Mismatch: {expected_vs_actual}")
                            
                            blockers = data.get("blockers")
                            if blockers:
                                logger.warning(f"   🚧 Blockers: {blockers}")
                            
                            retry_reason = data.get("retry_reason")
                            if retry_reason:
                                logger.info(f"   🔄 Retry: {retry_reason}")
                            
                            goal_progress = data.get("goal_progress")
                            if goal_progress is not None:
                                on_track = data.get("on_track", True)
                                track_icon = "✓" if on_track else "✗"
                                logger.info(f"   📊 Progress: {goal_progress}% [{track_icon} on track]")
                            
                            # Show error if present (from LLM error)
                            if error:
                                error_preview = error[:200] + "..." if len(error) > 200 else error
                                logger.error(f"   ⚠️ LLM Error: {error_preview}")

                        
                        if done:
                            result["success"] = True
                            result["summary"] = thought or f"Task completed in {step_count} steps"
                            result["steps"] = step_count
                            result["session_id"] = session_id
                            return result
                    
                    elif msg_type == "error":
                        result["error"] = data.get("error", "Unknown error")
                        logger.error(f"[Extension] Error: {result['error']}")
                        return result
                    
                except asyncio.TimeoutError:
                    # No message in 10s, continue waiting
                    if debug:
                        logger.debug(f"[Extension] Waiting... ({int(time.time() - start_time)}s elapsed)")
                    continue
            
            # Timeout reached
            result["error"] = f"Timeout after {timeout}s"
            result["steps"] = step_count
            if step_count > 0:
                result["summary"] = f"Partial completion: {step_count} steps before timeout"
            return result
            
    except ConnectionRefusedError:
        result["error"] = f"Cannot connect to bridge server at {ws_url}"
        return result
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[Extension] Error: {e}")
        return result


async def test_extension_mode(
    goal: str = "Go to google.com and confirm the page loaded",
    url: str = "https://www.google.com",
    debug: bool = True,
    timeout: float = 60.0,
) -> Dict:
    """Test extension mode end-to-end.
    
    This is a diagnostic function to verify extension mode works:
    1. Check if bridge server is running
    2. Send a simple goal
    3. Report success/failure with detailed debug info
    
    Args:
        goal: Test goal to execute
        url: Starting URL
        debug: Enable debug output
        timeout: Timeout in seconds
        
    Returns:
        Test result with diagnostics
    """
    import aiohttp
    
    result = {
        "bridge_server_running": False,
        "extension_connected": False,
        "goal_executed": False,
        "success": False,
        "error": "",
        "diagnostics": [],
    }
    
    # Step 1: Check bridge server
    logger.info("[TEST] Checking bridge server...")
    result["diagnostics"].append("Checking bridge server on localhost:8765")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8765/health", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    health = await resp.json()
                    result["bridge_server_running"] = True
                    result["diagnostics"].append(f"✓ Bridge server running: {health}")
                    logger.info(f"[TEST] ✓ Bridge server: {health}")
                else:
                    result["diagnostics"].append(f"✗ Bridge server returned {resp.status}")
                    result["error"] = "Bridge server not healthy"
                    return result
    except Exception as e:
        result["diagnostics"].append(f"✗ Cannot connect to bridge server: {e}")
        result["error"] = f"Bridge server not reachable: {e}"
        logger.error(f"[TEST] ✗ Bridge server: {e}")
        return result
    
    # Step 2: Try to execute goal via extension
    logger.info(f"[TEST] Executing goal: '{goal}'")
    result["diagnostics"].append(f"Sending goal: '{goal}'")
    
    try:
        exec_result = await run_browser_agent(
            goal=goal,
            url=url,
            debug=debug,
            timeout=timeout,
        )
        
        result["goal_executed"] = True
        result["success"] = exec_result.get("success", False)
        result["steps"] = exec_result.get("steps", 0)
        result["summary"] = exec_result.get("summary", "")
        result["error"] = exec_result.get("error", "")
        
        if result["success"]:
            result["diagnostics"].append(f"✓ Goal completed in {result['steps']} steps")
            logger.info(f"[TEST] ✓ Goal completed: {result['summary']}")
        else:
            result["diagnostics"].append(f"✗ Goal failed: {result['error']}")
            logger.warning(f"[TEST] ✗ Goal failed: {result['error']}")
            
    except Exception as e:
        result["diagnostics"].append(f"✗ Execution error: {e}")
        result["error"] = str(e)
        logger.error(f"[TEST] ✗ Execution error: {e}")
    
    return result



if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PraisonAI Browser Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM model")
    parser.add_argument("--max-steps", type=int, default=20, help="Max steps per session")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    server = BrowserServer(
        host=args.host,
        port=args.port,
        model=args.model,
        max_steps=args.max_steps,
        verbose=args.verbose,
    )
    server.start()

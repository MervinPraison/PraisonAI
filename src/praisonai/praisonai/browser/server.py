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
        
        logger.info(f"Client connected: {conn_id}")
        
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
            logger.info(f"Client disconnected: {conn_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
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
        
        if msg_type == "start_session":
            return await self._handle_start_session(message, conn)
        
        elif msg_type == "observation":
            return await self._handle_observation(message, conn)
        
        elif msg_type == "stop_session":
            return await self._handle_stop_session(message, conn)
        
        elif msg_type == "ping":
            return {"type": "pong"}
        
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
        
        if not goal:
            return {
                "type": "error",
                "error": "Goal is required",
                "code": "MISSING_GOAL",
            }
        
        # Initialize session manager
        if self._sessions is None:
            self._sessions = SessionManager()
        
        # Create session
        session = self._sessions.create_session(goal)
        session_id = session["session_id"]
        conn.session_id = session_id
        
        # Create agent for this session
        agent = BrowserAgent(
            model=model,
            max_steps=self.max_steps,
            verbose=self.verbose,
        )
        self._agents[session_id] = agent
        
        logger.info(f"Started session {session_id}: {goal[:50]}...")
        
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
        session_id = message.get("session_id", conn.session_id)
        
        if not session_id or session_id not in self._agents:
            return {
                "type": "error",
                "error": "No active session",
                "code": "NO_SESSION",
            }
        
        agent = self._agents[session_id]
        
        # Process observation through agent
        try:
            action = await agent.aprocess_observation(message)
        except Exception as e:
            logger.error(f"Agent error: {e}")
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
        
        return {
            "type": "action",
            "session_id": session_id,
            **action,
        }
    
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
            conn.session_id = None
        
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

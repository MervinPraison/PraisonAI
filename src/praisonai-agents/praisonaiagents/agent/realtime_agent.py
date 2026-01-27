"""RealtimeAgent - Real-time voice conversations using OpenAI Realtime API."""

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Union
import asyncio
import logging


@dataclass
class RealtimeConfig:
    """Configuration for RealtimeAgent.
    
    Attributes:
        voice: Voice to use for audio output (alloy, echo, fable, onyx, nova, shimmer)
        modalities: List of modalities to use (text, audio)
        turn_detection: Turn detection mode (server_vad, none)
        input_audio_format: Input audio format (pcm16, g711_ulaw, g711_alaw)
        output_audio_format: Output audio format (pcm16, g711_ulaw, g711_alaw)
        temperature: Sampling temperature (0.0 to 2.0)
        max_response_output_tokens: Maximum tokens for response
        instructions: System instructions for the session
    """
    voice: str = "alloy"
    modalities: List[str] = field(default_factory=lambda: ["text", "audio"])
    turn_detection: str = "server_vad"
    input_audio_format: str = "pcm16"
    output_audio_format: str = "pcm16"
    temperature: float = 0.8
    max_response_output_tokens: Optional[int] = None
    instructions: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class RealtimeAgent:
    """Agent for real-time voice conversations using OpenAI Realtime API.
    
    This agent enables bidirectional audio streaming for voice conversations,
    supporting both text and audio modalities with configurable voice settings.
    
    Example:
        ```python
        from praisonaiagents import RealtimeAgent
        
        agent = RealtimeAgent(
            name="VoiceAssistant",
            realtime={"voice": "nova"}
        )
        
        # Connect and start conversation
        await agent.aconnect()
        await agent.send_text("Hello!")
        ```
    """
    
    def __init__(
        self,
        name: str = "RealtimeAgent",
        llm: Optional[str] = None,
        realtime: Optional[Union[bool, Dict, RealtimeConfig]] = None,
        instructions: Optional[str] = None,
        verbose: bool = True,
        **kwargs
    ):
        """Initialize RealtimeAgent.
        
        Args:
            name: Agent name
            llm: LLM model (default: gpt-4o-realtime-preview)
            realtime: Realtime configuration (bool, dict, or RealtimeConfig)
            instructions: System instructions
            verbose: Enable verbose output
            **kwargs: Additional arguments
        """
        self.name = name
        self.llm = llm or "gpt-4o-realtime-preview"
        self.instructions = instructions
        self.verbose = verbose
        
        # Resolve configuration (Precedence Ladder)
        if realtime is None or realtime is True:
            self._realtime_config = RealtimeConfig()
        elif isinstance(realtime, dict):
            self._realtime_config = RealtimeConfig(**realtime)
        elif isinstance(realtime, RealtimeConfig):
            self._realtime_config = realtime
        else:
            self._realtime_config = RealtimeConfig()
        
        # Override instructions if provided
        if instructions:
            self._realtime_config.instructions = instructions
        
        # Lazy-loaded dependencies
        self._client = None
        self._console = None
        self._ws = None
        
        # Callbacks
        self._on_message_callbacks: List[Callable] = []
        self._on_audio_callbacks: List[Callable] = []
        self._on_error_callbacks: List[Callable] = []
        
        # Connection state
        self._connected = False
        
        # Configure logging
        self._logger = logging.getLogger(f"RealtimeAgent.{name}")
        if not verbose:
            self._logger.setLevel(logging.WARNING)
    
    @property
    def console(self):
        """Lazy load Rich console."""
        if self._console is None:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                pass
        return self._console
    
    def _log(self, message: str, style: str = ""):
        """Log message if verbose."""
        if self.verbose and self.console:
            self.console.print(f"[{style}]{message}[/{style}]" if style else message)
    
    # =========================================================================
    # Connection Methods
    # =========================================================================
    
    def connect(self, **kwargs) -> bool:
        """Connect to the Realtime API (sync wrapper).
        
        Returns:
            True if connected successfully
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, can't use run_until_complete
                self._log("Use aconnect() in async context", "yellow")
                return False
            return loop.run_until_complete(self.aconnect(**kwargs))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.aconnect(**kwargs))
    
    async def aconnect(self, **kwargs) -> bool:
        """Connect to the Realtime API asynchronously.
        
        Returns:
            True if connected successfully
        """
        if self._connected:
            self._log("Already connected", "yellow")
            return True
        
        try:
            # Lazy import websockets
            try:
                import websockets
            except ImportError:
                raise ImportError(
                    "websockets required for RealtimeAgent. "
                    "Install with: pip install websockets"
                )
            
            # Get API key
            import os
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable required")
            
            # Build WebSocket URL
            url = f"wss://api.openai.com/v1/realtime?model={self.llm}"
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            self._ws = await websockets.connect(url, extra_headers=headers)
            self._connected = True
            
            # Send session configuration
            config = self._realtime_config.to_dict()
            await self._send_event({
                "type": "session.update",
                "session": config
            })
            
            self._log(f"Connected to Realtime API with model {self.llm}", "green")
            return True
            
        except Exception as e:
            self._log(f"Connection failed: {e}", "red")
            for callback in self._on_error_callbacks:
                callback(e)
            return False
    
    def disconnect(self) -> bool:
        """Disconnect from the Realtime API (sync wrapper).
        
        Returns:
            True if disconnected successfully
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._log("Use adisconnect() in async context", "yellow")
                return False
            return loop.run_until_complete(self.adisconnect())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.adisconnect())
    
    async def adisconnect(self) -> bool:
        """Disconnect from the Realtime API asynchronously.
        
        Returns:
            True if disconnected successfully
        """
        if not self._connected or not self._ws:
            return True
        
        try:
            await self._ws.close()
            self._connected = False
            self._ws = None
            self._log("Disconnected from Realtime API", "yellow")
            return True
        except Exception as e:
            self._log(f"Disconnect error: {e}", "red")
            return False
    
    # =========================================================================
    # Send Methods
    # =========================================================================
    
    async def _send_event(self, event: Dict[str, Any]) -> bool:
        """Send an event to the Realtime API.
        
        Args:
            event: Event dictionary to send
            
        Returns:
            True if sent successfully
        """
        if not self._connected or not self._ws:
            self._log("Not connected", "red")
            return False
        
        try:
            import json
            await self._ws.send(json.dumps(event))
            return True
        except Exception as e:
            self._log(f"Send error: {e}", "red")
            return False
    
    def send_text(self, text: str) -> bool:
        """Send text message (sync wrapper).
        
        Args:
            text: Text message to send
            
        Returns:
            True if sent successfully
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._log("Use async send in async context", "yellow")
                return False
            return loop.run_until_complete(self.asend_text(text))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.asend_text(text))
    
    async def asend_text(self, text: str) -> bool:
        """Send text message asynchronously.
        
        Args:
            text: Text message to send
            
        Returns:
            True if sent successfully
        """
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}]
            }
        }
        if await self._send_event(event):
            # Request response
            return await self._send_event({"type": "response.create"})
        return False
    
    def send_audio(self, audio_data: bytes) -> bool:
        """Send audio data (sync wrapper).
        
        Args:
            audio_data: Raw audio bytes (PCM16 format)
            
        Returns:
            True if sent successfully
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return False
            return loop.run_until_complete(self.asend_audio(audio_data))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.asend_audio(audio_data))
    
    async def asend_audio(self, audio_data: bytes) -> bool:
        """Send audio data asynchronously.
        
        Args:
            audio_data: Raw audio bytes (PCM16 format)
            
        Returns:
            True if sent successfully
        """
        import base64
        encoded = base64.b64encode(audio_data).decode("utf-8")
        
        event = {
            "type": "input_audio_buffer.append",
            "audio": encoded
        }
        return await self._send_event(event)
    
    # =========================================================================
    # Callback Registration
    # =========================================================================
    
    def on_message(self, callback: Callable[[str], None]) -> None:
        """Register callback for text messages.
        
        Args:
            callback: Function to call with message text
        """
        self._on_message_callbacks.append(callback)
    
    def on_audio(self, callback: Callable[[bytes], None]) -> None:
        """Register callback for audio data.
        
        Args:
            callback: Function to call with audio bytes
        """
        self._on_audio_callbacks.append(callback)
    
    def on_error(self, callback: Callable[[Exception], None]) -> None:
        """Register callback for errors.
        
        Args:
            callback: Function to call with exception
        """
        self._on_error_callbacks.append(callback)
    
    # =========================================================================
    # Receive Methods
    # =========================================================================
    
    async def receive_loop(self) -> None:
        """Main receive loop for processing incoming events."""
        if not self._connected or not self._ws:
            return
        
        import json
        import base64
        
        try:
            async for message in self._ws:
                try:
                    event = json.loads(message)
                    event_type = event.get("type", "")
                    
                    # Handle text responses
                    if event_type == "response.text.delta":
                        text = event.get("delta", "")
                        for callback in self._on_message_callbacks:
                            callback(text)
                    
                    # Handle audio responses
                    elif event_type == "response.audio.delta":
                        audio_b64 = event.get("delta", "")
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            for callback in self._on_audio_callbacks:
                                callback(audio_bytes)
                    
                    # Handle errors
                    elif event_type == "error":
                        error = event.get("error", {})
                        self._log(f"API Error: {error}", "red")
                        for callback in self._on_error_callbacks:
                            callback(Exception(str(error)))
                    
                except json.JSONDecodeError:
                    pass
                    
        except Exception as e:
            self._log(f"Receive loop error: {e}", "red")
            for callback in self._on_error_callbacks:
                callback(e)
    
    # =========================================================================
    # Context Manager
    # =========================================================================
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.aconnect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.adisconnect()

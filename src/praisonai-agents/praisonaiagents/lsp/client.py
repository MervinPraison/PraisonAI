"""
LSP Client for PraisonAI Agents.

Provides Language Server Protocol client implementation.
"""

import os
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

from .types import (
    Diagnostic, DiagnosticSeverity, CompletionItem, Location,
    Position, Range, TextDocumentItem, TextDocumentIdentifier,
    TextDocumentPositionParams
)
from .config import LSPConfig

logger = logging.getLogger(__name__)


class LSPClient:
    """
    Language Server Protocol client.
    
    Communicates with language servers to provide code intelligence
    features like diagnostics, completions, and navigation.
    
    Example:
        client = LSPClient(language="python")
        await client.start()
        
        # Get diagnostics
        diagnostics = await client.get_diagnostics("/path/to/file.py")
        
        # Get completions
        completions = await client.get_completions(
            "/path/to/file.py", line=10, character=5
        )
        
        await client.stop()
    """
    
    def __init__(
        self,
        language: str,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        root_uri: Optional[str] = None
    ):
        """
        Initialize the LSP client.
        
        Args:
            language: Programming language (python, javascript, etc.)
            command: Language server command (uses default if not specified)
            args: Command arguments
            root_uri: Workspace root URI
        """
        self.config = LSPConfig(
            language=language,
            command=command,
            args=args or [],
            root_uri=root_uri
        )
        
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._diagnostics: Dict[str, List[Diagnostic]] = {}
        self._initialized = False
        self._reader_task: Optional[asyncio.Task] = None
    
    @property
    def is_running(self) -> bool:
        """Check if the language server is running."""
        return self._process is not None and self._process.returncode is None
    
    async def start(self) -> bool:
        """
        Start the language server.
        
        Returns:
            True if started successfully
        """
        if self.is_running:
            return True
        
        try:
            cmd = [self.config.command] + self.config.args
            
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Start reader task
            self._reader_task = asyncio.create_task(self._read_responses())
            
            # Initialize the server
            root_uri = self.config.root_uri or f"file://{os.getcwd()}"
            
            result = await self._send_request("initialize", {
                "processId": os.getpid(),
                "rootUri": root_uri,
                "capabilities": {
                    "textDocument": {
                        "completion": {"completionItem": {"snippetSupport": True}},
                        "hover": {},
                        "definition": {},
                        "references": {},
                        "publishDiagnostics": {}
                    }
                },
                "initializationOptions": self.config.initialization_options
            })
            
            if result:
                await self._send_notification("initialized", {})
                self._initialized = True
                logger.info(f"LSP server started: {self.config.command}")
                return True
            
            return False
            
        except FileNotFoundError:
            logger.error(f"Language server not found: {self.config.command}")
            return False
        except Exception as e:
            logger.error(f"Failed to start LSP server: {e}")
            return False
    
    async def stop(self):
        """Stop the language server."""
        if not self.is_running:
            return
        
        try:
            await self._send_request("shutdown", None)
            await self._send_notification("exit", None)
        except Exception:
            pass
        
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
        
        self._process = None
        self._initialized = False
    
    async def open_document(self, file_path: str, text: Optional[str] = None) -> bool:
        """
        Open a document in the language server.
        
        Args:
            file_path: Path to the file
            text: File content (reads from disk if not provided)
            
        Returns:
            True if successful
        """
        if not self._initialized:
            return False
        
        if text is None:
            try:
                with open(file_path, "r") as f:
                    text = f.read()
            except Exception as e:
                logger.error(f"Failed to read file: {e}")
                return False
        
        uri = f"file://{os.path.abspath(file_path)}"
        
        await self._send_notification("textDocument/didOpen", {
            "textDocument": TextDocumentItem(
                uri=uri,
                language_id=self.config.language,
                version=1,
                text=text
            ).to_dict()
        })
        
        return True
    
    async def close_document(self, file_path: str):
        """Close a document in the language server."""
        if not self._initialized:
            return
        
        uri = f"file://{os.path.abspath(file_path)}"
        
        await self._send_notification("textDocument/didClose", {
            "textDocument": TextDocumentIdentifier(uri=uri).to_dict()
        })
    
    async def get_diagnostics(self, file_path: str) -> List[Diagnostic]:
        """
        Get diagnostics for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of diagnostics
        """
        uri = f"file://{os.path.abspath(file_path)}"
        return self._diagnostics.get(uri, [])
    
    async def get_completions(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> List[CompletionItem]:
        """
        Get completions at a position.
        
        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            character: Character position (0-indexed)
            
        Returns:
            List of completion items
        """
        if not self._initialized:
            return []
        
        uri = f"file://{os.path.abspath(file_path)}"
        
        result = await self._send_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        })
        
        if result is None:
            return []
        
        items = result.get("items", result) if isinstance(result, dict) else result
        
        return [
            CompletionItem.from_dict(item)
            for item in (items if isinstance(items, list) else [])
        ]
    
    async def get_definition(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> List[Location]:
        """
        Get definition location(s) for a symbol.
        
        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            character: Character position (0-indexed)
            
        Returns:
            List of locations
        """
        if not self._initialized:
            return []
        
        uri = f"file://{os.path.abspath(file_path)}"
        
        result = await self._send_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        })
        
        if result is None:
            return []
        
        if isinstance(result, dict):
            return [Location.from_dict(result)]
        elif isinstance(result, list):
            return [Location.from_dict(loc) for loc in result]
        
        return []
    
    async def get_references(
        self,
        file_path: str,
        line: int,
        character: int,
        include_declaration: bool = True
    ) -> List[Location]:
        """
        Get references to a symbol.
        
        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            character: Character position (0-indexed)
            include_declaration: Include the declaration in results
            
        Returns:
            List of locations
        """
        if not self._initialized:
            return []
        
        uri = f"file://{os.path.abspath(file_path)}"
        
        result = await self._send_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": include_declaration}
        })
        
        if result is None:
            return []
        
        return [Location.from_dict(loc) for loc in result]
    
    async def get_hover(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> Optional[str]:
        """
        Get hover information for a position.
        
        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            character: Character position (0-indexed)
            
        Returns:
            Hover content as string
        """
        if not self._initialized:
            return None
        
        uri = f"file://{os.path.abspath(file_path)}"
        
        result = await self._send_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        })
        
        if result is None:
            return None
        
        contents = result.get("contents")
        if isinstance(contents, str):
            return contents
        elif isinstance(contents, dict):
            return contents.get("value", str(contents))
        elif isinstance(contents, list):
            return "\n".join(
                c.get("value", str(c)) if isinstance(c, dict) else str(c)
                for c in contents
            )
        
        return None
    
    async def _send_request(self, method: str, params: Any) -> Any:
        """Send a request and wait for response."""
        if not self.is_running:
            return None
        
        self._request_id += 1
        request_id = self._request_id
        
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future
        
        await self._send_message(message)
        
        try:
            result = await asyncio.wait_for(future, timeout=self.config.timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Request timed out: {method}")
            self._pending_requests.pop(request_id, None)
            return None
    
    async def _send_notification(self, method: str, params: Any):
        """Send a notification (no response expected)."""
        if not self.is_running:
            return
        
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        await self._send_message(message)
    
    async def _send_message(self, message: Dict[str, Any]):
        """Send a JSON-RPC message."""
        if self._process is None or self._process.stdin is None:
            return
        
        content = json.dumps(message)
        header = f"Content-Length: {len(content)}\r\n\r\n"
        
        self._process.stdin.write(header.encode() + content.encode())
        await self._process.stdin.drain()
    
    async def _read_responses(self):
        """Read responses from the language server."""
        if self._process is None or self._process.stdout is None:
            return
        
        try:
            while True:
                # Read header
                header = b""
                while b"\r\n\r\n" not in header:
                    chunk = await self._process.stdout.read(1)
                    if not chunk:
                        return
                    header += chunk
                
                # Parse content length
                content_length = 0
                for line in header.decode().split("\r\n"):
                    if line.startswith("Content-Length:"):
                        content_length = int(line.split(":")[1].strip())
                        break
                
                if content_length == 0:
                    continue
                
                # Read content
                content = await self._process.stdout.read(content_length)
                message = json.loads(content.decode())
                
                await self._handle_message(message)
                
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error reading LSP response: {e}")
    
    async def _handle_message(self, message: Dict[str, Any]):
        """Handle an incoming message."""
        if "id" in message:
            # Response to a request
            request_id = message["id"]
            if request_id in self._pending_requests:
                future = self._pending_requests.pop(request_id)
                if "error" in message:
                    future.set_exception(
                        RuntimeError(message["error"].get("message", "Unknown error"))
                    )
                else:
                    future.set_result(message.get("result"))
        
        elif "method" in message:
            # Notification from server
            method = message["method"]
            params = message.get("params", {})
            
            if method == "textDocument/publishDiagnostics":
                uri = params.get("uri", "")
                diagnostics = [
                    Diagnostic.from_dict(d)
                    for d in params.get("diagnostics", [])
                ]
                self._diagnostics[uri] = diagnostics

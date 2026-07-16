"""
MCP Elicitation Implementation

Implements the Elicitation API per MCP 2025-11-25 specification.
Elicitation allows servers to request additional information from users.

Features:
- Form mode: Structured data with JSON schema validation
- URL mode: External URLs for sensitive interactions
- CLI integration for interactive prompts
- Non-interactive CI mode support
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ElicitationMode(str, Enum):
    """Elicitation modes per MCP 2025-11-25."""
    FORM = "form"
    URL = "url"


class ElicitationAction(str, Enum):
    """Elicitation response actions per MCP 2025-11-25."""
    ACCEPT = "accept"  # User accepted and provided data
    DECLINE = "decline"  # User explicitly declined
    CANCEL = "cancel"  # User cancelled the request


# Backwards compatibility alias
class ElicitationStatus(str, Enum):
    """Elicitation response status (deprecated, use ElicitationAction)."""
    COMPLETED = "accept"  # Maps to accept
    CANCELLED = "cancel"  # Maps to cancel
    TIMEOUT = "cancel"  # Maps to cancel
    ERROR = "decline"  # Maps to decline


@dataclass
class ElicitationSchema:
    """
    Schema for form-mode elicitation.
    
    Supports JSON Schema for validation with extensions for:
    - String, number, boolean, enum types
    - Default values
    - Required fields
    """
    type: str = "object"
    properties: Dict[str, Any] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    title: Optional[str] = None
    description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type,
            "properties": self.properties,
        }
        if self.required:
            result["required"] = self.required
        if self.title:
            result["title"] = self.title
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class ElicitationRequest:
    """
    MCP Elicitation request per 2025-11-25 specification.
    
    Represents a request for user input during server operations.
    Supports form mode (structured data) and URL mode (external URLs).
    """
    message: str
    mode: ElicitationMode = ElicitationMode.FORM
    requested_schema: Optional[ElicitationSchema] = None
    url: Optional[str] = None
    elicitation_id: Optional[str] = None  # Required for URL mode
    timeout: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Backwards compatibility alias
    @property
    def schema(self) -> Optional[ElicitationSchema]:
        return self.requested_schema
    
    @property
    def id(self) -> str:
        return self.elicitation_id or ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP elicitation/create params format."""
        result = {
            "message": self.message,
        }
        
        # Mode is optional for form (defaults to form if omitted)
        if self.mode == ElicitationMode.URL:
            result["mode"] = self.mode.value
        
        if self.mode == ElicitationMode.FORM and self.requested_schema:
            result["requestedSchema"] = self.requested_schema.to_dict()
        
        if self.mode == ElicitationMode.URL:
            if self.url:
                result["url"] = self.url
            if self.elicitation_id:
                result["elicitationId"] = self.elicitation_id
        
        if self.metadata:
            result["_meta"] = self.metadata
        
        return result


@dataclass
class ElicitationResult:
    """
    MCP Elicitation result per 2025-11-25 specification.
    
    Contains the user's response to an elicitation request.
    Action can be: accept, decline, or cancel.
    """
    action: ElicitationAction
    content: Optional[Dict[str, Any]] = None  # Only when action=accept
    validation_error: Optional[str] = None
    
    # Backwards compatibility aliases
    @property
    def status(self) -> ElicitationStatus:
        if self.action == ElicitationAction.ACCEPT:
            return ElicitationStatus.COMPLETED
        elif self.action == ElicitationAction.DECLINE:
            return ElicitationStatus.ERROR
        return ElicitationStatus.CANCELLED
    
    @property
    def data(self) -> Optional[Dict[str, Any]]:
        return self.content
    
    @property
    def error(self) -> Optional[str]:
        return self.validation_error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP ElicitResult format."""
        result = {
            "action": self.action.value,
        }
        
        if self.action == ElicitationAction.ACCEPT and self.content:
            result["content"] = self.content
        
        if self.validation_error:
            result["validationError"] = self.validation_error
        
        return result
    
    @classmethod
    def accept(cls, content: Dict[str, Any]) -> "ElicitationResult":
        """Create an accept result."""
        return cls(action=ElicitationAction.ACCEPT, content=content)
    
    @classmethod
    def decline(cls, error: Optional[str] = None) -> "ElicitationResult":
        """Create a decline result."""
        return cls(action=ElicitationAction.DECLINE, validation_error=error)
    
    @classmethod
    def cancel(cls) -> "ElicitationResult":
        """Create a cancel result."""
        return cls(action=ElicitationAction.CANCEL)


class ElicitationHandler:
    """
    Handles elicitation requests.
    
    Provides different handlers for:
    - Interactive CLI mode
    - Non-interactive CI mode
    - Custom handlers
    """
    
    def __init__(
        self,
        interactive: bool = True,
        default_timeout: int = 300,
        ci_mode: bool = False,
        ci_defaults: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize elicitation handler.
        
        Args:
            interactive: Whether to prompt for user input
            default_timeout: Default timeout in seconds
            ci_mode: CI mode (fail or use defaults)
            ci_defaults: Default values for CI mode
        """
        self.interactive = interactive
        self.default_timeout = default_timeout
        self.ci_mode = ci_mode
        self.ci_defaults = ci_defaults or {}
        
        self._pending_requests: Dict[str, ElicitationRequest] = {}
        self._custom_handler: Optional[Callable] = None
    
    def set_custom_handler(self, handler: Callable) -> None:
        """Set a custom elicitation handler."""
        self._custom_handler = handler
    
    async def elicit(self, request: ElicitationRequest) -> ElicitationResult:
        """
        Process an elicitation request.
        
        Args:
            request: Elicitation request
            
        Returns:
            Elicitation result
        """
        req_id = request.elicitation_id or request.id
        self._pending_requests[req_id] = request
        
        try:
            if self._custom_handler:
                return await self._custom_handler(request)
            
            if self.ci_mode:
                return await self._handle_ci_mode(request)
            
            if self.interactive:
                return await self._handle_interactive(request)
            
            return ElicitationResult.decline("No elicitation handler available")
        
        finally:
            if req_id in self._pending_requests:
                del self._pending_requests[req_id]
    
    async def _handle_ci_mode(self, request: ElicitationRequest) -> ElicitationResult:
        """Handle elicitation in CI mode."""
        if request.mode == ElicitationMode.URL:
            # URL mode cannot be handled in CI
            return ElicitationResult.decline("URL elicitation not supported in CI mode")
        
        # Try to use defaults
        if request.requested_schema:
            data = {}
            for prop_name, prop_schema in request.requested_schema.properties.items():
                if prop_name in self.ci_defaults:
                    data[prop_name] = self.ci_defaults[prop_name]
                elif "default" in prop_schema:
                    data[prop_name] = prop_schema["default"]
                elif prop_name in request.requested_schema.required:
                    return ElicitationResult.decline(
                        f"Required field '{prop_name}' has no default in CI mode"
                    )
            
            return ElicitationResult.accept(data)
        
        return ElicitationResult.accept({})
    
    async def _handle_interactive(self, request: ElicitationRequest) -> ElicitationResult:
        """Handle elicitation interactively."""
        if request.mode == ElicitationMode.URL:
            return await self._handle_url_elicitation(request)
        
        return await self._handle_form_elicitation(request)
    
    async def _handle_form_elicitation(self, request: ElicitationRequest) -> ElicitationResult:
        """Handle form-mode elicitation."""
        try:
            print(f"\n[Elicitation] {request.message}")
            
            if not request.requested_schema:
                # Simple confirmation
                response = input("Continue? [y/N]: ").strip().lower()
                if response in ("y", "yes"):
                    return ElicitationResult.accept({"confirmed": True})
                return ElicitationResult.cancel()
            
            # Collect form data
            data = {}
            for prop_name, prop_schema in request.requested_schema.properties.items():
                prop_type = prop_schema.get("type", "string")
                prop_desc = prop_schema.get("description", prop_name)
                default = prop_schema.get("default")
                required = prop_name in request.requested_schema.required
                
                prompt = f"  {prop_desc}"
                if default is not None:
                    prompt += f" [{default}]"
                if required:
                    prompt += " (required)"
                prompt += ": "
                
                # Handle enum type
                if "enum" in prop_schema:
                    options = prop_schema["enum"]
                    print(f"  Options: {', '.join(str(o) for o in options)}")
                
                value = input(prompt).strip()
                
                if not value and default is not None:
                    value = default
                elif not value and required:
                    return ElicitationResult.decline(
                        f"Required field '{prop_name}' not provided"
                    )
                
                # Type conversion
                if value:
                    if prop_type == "integer":
                        value = int(value)
                    elif prop_type == "number":
                        value = float(value)
                    elif prop_type == "boolean":
                        value = value.lower() in ("true", "yes", "1", "y")
                
                if value is not None:
                    data[prop_name] = value
            
            return ElicitationResult.accept(data)
        
        except KeyboardInterrupt:
            return ElicitationResult.cancel()
        except Exception as e:
            return ElicitationResult.decline(str(e))
    
    async def _handle_url_elicitation(self, request: ElicitationRequest) -> ElicitationResult:
        """Handle URL-mode elicitation."""
        try:
            print(f"\n[Elicitation] {request.message}")
            print(f"  Please visit: {request.url}")
            
            # Wait for user confirmation
            response = input("Press Enter when complete, or 'c' to cancel: ").strip().lower()
            
            if response == "c":
                return ElicitationResult.cancel()
            
            return ElicitationResult.accept({"url_visited": True})
        
        except KeyboardInterrupt:
            return ElicitationResult.cancel()
        except Exception as e:
            return ElicitationResult.decline(str(e))
    
    def cancel(self, request_id: str) -> bool:
        """Cancel a pending elicitation request."""
        if request_id in self._pending_requests:
            del self._pending_requests[request_id]
            return True
        return False


# Global elicitation handler
_elicitation_handler: Optional[ElicitationHandler] = None


def get_elicitation_handler() -> ElicitationHandler:
    """Get the global elicitation handler."""
    global _elicitation_handler
    if _elicitation_handler is None:
        _elicitation_handler = ElicitationHandler()
    return _elicitation_handler


def set_elicitation_handler(handler: ElicitationHandler) -> None:
    """Set the global elicitation handler."""
    global _elicitation_handler
    _elicitation_handler = handler


def create_form_request(
    message: str,
    properties: Dict[str, Any],
    required: Optional[List[str]] = None,
    title: Optional[str] = None,
    timeout: Optional[int] = None,
) -> ElicitationRequest:
    """
    Create a form-mode elicitation request per MCP 2025-11-25.
    
    Args:
        message: Message to display to user
        properties: JSON Schema properties (requestedSchema)
        required: Required field names
        title: Form title
        timeout: Request timeout
        
    Returns:
        ElicitationRequest
    """
    schema = ElicitationSchema(
        properties=properties,
        required=required or [],
        title=title,
    )
    
    return ElicitationRequest(
        message=message,
        mode=ElicitationMode.FORM,
        requested_schema=schema,
        timeout=timeout,
    )


def create_url_request(
    message: str,
    url: str,
    elicitation_id: Optional[str] = None,
    timeout: Optional[int] = None,
) -> ElicitationRequest:
    """
    Create a URL-mode elicitation request per MCP 2025-11-25.
    
    Args:
        message: Message to display to user
        url: URL to visit
        elicitation_id: Unique ID for the elicitation (auto-generated if not provided)
        timeout: Request timeout
        
    Returns:
        ElicitationRequest
    """
    import uuid
    
    return ElicitationRequest(
        message=message,
        mode=ElicitationMode.URL,
        url=url,
        elicitation_id=elicitation_id or f"elicit-{uuid.uuid4().hex[:12]}",
        timeout=timeout,
    )

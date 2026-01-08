"""
InteractiveCore - Unified runtime for all interactive modes.

This is the single source of truth for interactive execution.
All frontends (Rich REPL, Textual TUI) consume events from this core.
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .config import InteractiveConfig, ApprovalMode
from .events import (
    InteractiveEvent,
    InteractiveEventType,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalDecision,
)

logger = logging.getLogger(__name__)


class InteractiveCore:
    """
    Unified interactive runtime core.
    
    This class provides:
    - Event-based communication with frontends
    - Session management (create, resume, continue, export, import)
    - Tool dispatch with unified configuration
    - Permission/approval management
    
    All interactive modes use this same core:
    - `praisonai run --interactive` → RichFrontend
    - `praisonai chat` → RichFrontend
    - `praisonai tui launch` → TextualFrontend
    """
    
    def __init__(self, config: Optional[InteractiveConfig] = None):
        """Initialize the interactive core.
        
        Args:
            config: Configuration for the interactive session.
                   If None, uses defaults from environment.
        """
        self.config = config or InteractiveConfig.from_env()
        
        # Event handlers
        self._event_handlers: List[Callable[[InteractiveEvent], None]] = []
        self._filtered_handlers: Dict[Callable, Set[InteractiveEventType]] = {}
        
        # Session state
        self._session_store = None
        self._current_session_id: Optional[str] = None
        
        # Tools (lazy loaded)
        self._tools: Optional[List] = None
        
        # Permission management
        self._approval_patterns: Set[str] = set()
        self._session_approvals: Set[str] = set()
        self._load_persistent_approvals()
    
    @property
    def session_store(self):
        """Get the session store (lazy loaded)."""
        if self._session_store is None:
            from ..session import get_session_store
            self._session_store = get_session_store()
        return self._session_store
    
    @property
    def current_session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._current_session_id
    
    @property
    def permission_manager(self):
        """Get the permission manager."""
        return self  # Self implements permission methods
    
    @property
    def tools(self) -> List:
        """Get the tools list (lazy loaded)."""
        if self._tools is None:
            self._tools = self.get_tools()
        return self._tools
    
    # ========== Event Subscription ==========
    
    def subscribe(
        self,
        handler: Callable[[InteractiveEvent], None],
        event_types: Optional[List[InteractiveEventType]] = None,
    ) -> Callable[[], None]:
        """Subscribe to events.
        
        Args:
            handler: Callback function to receive events.
            event_types: Optional filter for specific event types.
                        If None, receives all events.
        
        Returns:
            Unsubscribe function.
        """
        self._event_handlers.append(handler)
        
        if event_types:
            self._filtered_handlers[handler] = set(event_types)
        
        def unsubscribe():
            if handler in self._event_handlers:
                self._event_handlers.remove(handler)
            self._filtered_handlers.pop(handler, None)
        
        return unsubscribe
    
    def _emit(self, event: InteractiveEvent) -> None:
        """Emit an event to all subscribed handlers."""
        for handler in self._event_handlers:
            # Check filter
            if handler in self._filtered_handlers:
                if event.type not in self._filtered_handlers[handler]:
                    continue
            
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler: {e}")
    
    # ========== Session Management ==========
    
    def create_session(self, title: Optional[str] = None) -> str:
        """Create a new session.
        
        Args:
            title: Optional title for the session.
        
        Returns:
            The new session ID.
        """
        session_id = str(uuid.uuid4())[:8]
        
        # Create session in store using get_or_create
        session = self.session_store.get_or_create(session_id)
        session.metadata["title"] = title or f"Session {session_id}"
        session.metadata["workspace"] = self.config.workspace
        self.session_store.save(session)
        
        self._current_session_id = session_id
        self._session_approvals.clear()
        
        # Emit event
        self._emit(InteractiveEvent(
            type=InteractiveEventType.SESSION_CREATED,
            data={"session_id": session_id, "title": title},
            source="core"
        ))
        
        return session_id
    
    def resume_session(self, session_id: str) -> bool:
        """Resume an existing session.
        
        Args:
            session_id: ID of the session to resume.
        
        Returns:
            True if session was found and resumed, False otherwise.
        """
        session = self.session_store.load(session_id)
        
        if session is None:
            return False
        
        self._current_session_id = session_id
        self._session_approvals.clear()
        
        # Emit event
        self._emit(InteractiveEvent(
            type=InteractiveEventType.SESSION_RESUMED,
            data={"session_id": session_id},
            source="core"
        ))
        
        return True
    
    def continue_session(self) -> Optional[str]:
        """Find and resume the most recent session.
        
        Returns:
            The session ID if found, None otherwise.
        """
        sessions = self.session_store.list_sessions()
        
        if not sessions:
            return None
        
        # Sort by timestamp (most recent first)
        sorted_sessions = sorted(
            sessions,
            key=lambda s: s.get("updated_at", s.get("created_at", 0)),
            reverse=True
        )
        
        if sorted_sessions:
            session_id = sorted_sessions[0].get("session_id")
            if session_id and self.resume_session(session_id):
                return session_id
        
        return None
    
    def get_session(self, session_id: str):
        """Get session by ID."""
        return self.session_store.load(session_id)
    
    # ========== Prompt Execution ==========
    
    async def prompt(
        self,
        message: str,
        session_id: Optional[str] = None,
        files: Optional[List[str]] = None,
    ) -> str:
        """Execute a prompt and return the response.
        
        Args:
            message: The user's message.
            session_id: Optional session ID. If None, uses current or creates new.
            files: Optional list of file paths to attach.
        
        Returns:
            The assistant's response text.
        """
        # Ensure we have a session
        if session_id:
            if not self.resume_session(session_id):
                session_id = self.create_session()
        elif self._current_session_id is None:
            session_id = self.create_session()
        else:
            session_id = self._current_session_id
        
        # Emit message start
        self._emit(InteractiveEvent(
            type=InteractiveEventType.MESSAGE_START,
            data={"message": message, "session_id": session_id},
            source="user"
        ))
        
        try:
            # Process file attachments
            file_context = ""
            all_files = (files or []) + self.config.files
            if all_files:
                file_context = self._process_file_attachments(all_files)
                if file_context:
                    message = f"{file_context}\n\n{message}"
            
            # Execute the prompt
            response = await self._execute_prompt(message, session_id)
            
            # Emit message end
            self._emit(InteractiveEvent(
                type=InteractiveEventType.MESSAGE_END,
                data={"response": response, "session_id": session_id},
                source="assistant"
            ))
            
            return response
            
        except Exception as e:
            # Emit error
            self._emit(InteractiveEvent(
                type=InteractiveEventType.ERROR,
                data={"error": str(e), "session_id": session_id},
                source="core"
            ))
            raise
    
    async def _execute_prompt(self, message: str, session_id: str) -> str:
        """Execute the prompt using the agent.
        
        This is the internal implementation that actually runs the agent.
        """
        try:
            from praisonaiagents import Agent
        except ImportError:
            try:
                # Fallback: try direct import
                from praisonaiagents.agent.agent import Agent
            except ImportError:
                return "Error: praisonaiagents not available"
        
        # Get session for chat history
        session = self.session_store.load(session_id)
        history = session.get_chat_history(max_messages=50) if session else []
        
        # Build agent config
        agent_config = {
            "name": "InteractiveAgent",
            "role": "Assistant",
            "goal": "Help the user with their request",
            "backstory": "You are a helpful AI assistant",
            "tools": self.get_tools(),
        }
        
        if self.config.model:
            agent_config["llm"] = {"model": self.config.model}
        
        if self.config.memory:
            agent_config["memory"] = True
        
        # Enable autonomy for intelligent task handling (agent-centric)
        if self.config.autonomy:
            if self.config.autonomy_config:
                agent_config["autonomy"] = self.config.autonomy_config
            else:
                agent_config["autonomy"] = True
        
        # Create agent and execute
        agent = Agent(**agent_config)
        
        # Add history context if available
        context = ""
        if history:
            context = "\n".join([
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in history[-10:]  # Last 10 messages
            ])
            context = f"Previous conversation:\n{context}\n\n"
        
        # Execute
        response = agent.chat(context + message)
        
        # Store in session
        session = self.session_store.load(session_id)
        if session:
            session.add_user_message(message)
            session.add_assistant_message(response)
            self.session_store.save(session)
        
        return response
    
    def _process_file_attachments(self, files: List[str]) -> str:
        """Process file attachments and return context string."""
        context_parts = []
        
        for filepath in files:
            path = Path(filepath)
            if path.exists() and path.is_file():
                try:
                    content = path.read_text()
                    context_parts.append(
                        f"<file path=\"{filepath}\">\n{content}\n</file>"
                    )
                except Exception as e:
                    logger.warning(f"Could not read file {filepath}: {e}")
        
        if context_parts:
            return "<attached_files>\n" + "\n".join(context_parts) + "\n</attached_files>"
        return ""
    
    # ========== Tool Management ==========
    
    def get_tools(self) -> List:
        """Get the list of tools based on configuration."""
        try:
            from ..features.interactive_tools import get_interactive_tools, ToolConfig
            
            tool_config = ToolConfig(
                workspace=self.config.workspace,
                enable_acp=self.config.enable_acp,
                enable_lsp=self.config.enable_lsp,
                approval_mode=self.config.approval_mode if isinstance(
                    self.config.approval_mode, str
                ) else self.config.approval_mode.value,
            )
            
            disable = []
            if not self.config.enable_acp:
                disable.append("acp")
            if not self.config.enable_lsp:
                disable.append("lsp")
            
            return get_interactive_tools(
                config=tool_config,
                disable=disable if disable else None,
            )
        except ImportError as e:
            logger.warning(f"Could not load interactive tools: {e}")
            return self._get_basic_tools()
    
    def _get_basic_tools(self) -> List:
        """Get basic tools as fallback."""
        tools = []
        try:
            from praisonaiagents.tools import read_file, write_file, list_files
            tools.extend([read_file, write_file, list_files])
        except ImportError:
            pass
        return tools
    
    # ========== Permission/Approval Management ==========
    
    def _load_persistent_approvals(self) -> None:
        """Load persistent approval patterns from file."""
        approvals_file = Path.home() / ".praison" / "approvals.json"
        
        if approvals_file.exists():
            try:
                with open(approvals_file) as f:
                    data = json.load(f)
                    self._approval_patterns = set(data.get("patterns", []))
            except Exception as e:
                logger.warning(f"Could not load approvals: {e}")
    
    def _save_persistent_approvals(self) -> None:
        """Save persistent approval patterns to file."""
        approvals_dir = Path.home() / ".praison"
        approvals_dir.mkdir(parents=True, exist_ok=True)
        approvals_file = approvals_dir / "approvals.json"
        
        try:
            with open(approvals_file, "w") as f:
                json.dump({"patterns": list(self._approval_patterns)}, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save approvals: {e}")
    
    def add_approval_pattern(self, pattern: str, persistent: bool = True) -> None:
        """Add an approval pattern.
        
        Args:
            pattern: Pattern to add (e.g., "file_read:*")
            persistent: If True, save to disk for future sessions.
        """
        if persistent:
            self._approval_patterns.add(pattern)
            self._save_persistent_approvals()
        else:
            self._session_approvals.add(pattern)
    
    def check_permission(self, request: ApprovalRequest) -> Optional[ApprovalDecision]:
        """Check if an action is pre-approved.
        
        Args:
            request: The approval request to check.
        
        Returns:
            ApprovalDecision if pre-approved, None if needs user input.
        """
        # Auto mode approves everything
        if self.config.approval_mode == "auto" or self.config.approval_mode == ApprovalMode.AUTO:
            return ApprovalDecision.ONCE
        
        # Reject mode rejects everything
        if self.config.approval_mode == "reject" or self.config.approval_mode == ApprovalMode.REJECT:
            return ApprovalDecision.REJECT
        
        # Check persistent patterns
        for pattern in self._approval_patterns:
            if request.matches_pattern(pattern):
                return ApprovalDecision.ALWAYS
        
        # Check session patterns
        for pattern in self._session_approvals:
            if request.matches_pattern(pattern):
                return ApprovalDecision.ALWAYS_SESSION
        
        # Needs user input
        return None
    
    def _emit_approval_request(self, request: ApprovalRequest) -> None:
        """Emit an approval request event."""
        self._emit(InteractiveEvent(
            type=InteractiveEventType.APPROVAL_ASKED,
            data=request.to_dict(),
            source="core"
        ))
    
    def _emit_approval_response(self, response: ApprovalResponse) -> None:
        """Emit an approval response event."""
        # Handle "always" decisions
        if response.decision == ApprovalDecision.ALWAYS and response.remember_pattern:
            self.add_approval_pattern(response.remember_pattern, persistent=True)
        elif response.decision == ApprovalDecision.ALWAYS_SESSION and response.remember_pattern:
            self.add_approval_pattern(response.remember_pattern, persistent=False)
        
        self._emit(InteractiveEvent(
            type=InteractiveEventType.APPROVAL_ANSWERED,
            data=response.to_dict(),
            source="user"
        ))
    
    # ========== Session Export/Import ==========
    
    def export_session(self, session_id: str) -> Dict[str, Any]:
        """Export a session to a dictionary.
        
        Args:
            session_id: ID of the session to export.
        
        Returns:
            Dictionary containing session data.
        """
        session = self.session_store.load(session_id)
        
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        
        # Get full session data from session object
        return {
            "session_id": session_id,
            "title": session.metadata.get("title", "Untitled"),
            "messages": session.get_chat_history(),
            "metadata": session.metadata,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
    
    def export_session_to_file(self, session_id: str, filepath: str) -> None:
        """Export a session to a JSON file.
        
        Args:
            session_id: ID of the session to export.
            filepath: Path to the output file.
        """
        data = self.export_session(session_id)
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def import_session(self, data: Dict[str, Any]) -> str:
        """Import a session from a dictionary.
        
        Args:
            data: Session data dictionary.
        
        Returns:
            The imported session ID.
        """
        session_id = data.get("session_id", str(uuid.uuid4())[:8])
        
        # Create session using get_or_create
        session = self.session_store.get_or_create(session_id)
        session.metadata["title"] = data.get("title", "Imported Session")
        session.metadata.update(data.get("metadata", {}))
        
        # Add messages
        for msg in data.get("messages", []):
            if msg.get("role") == "user":
                session.add_user_message(msg.get("content", ""))
            elif msg.get("role") == "assistant":
                session.add_assistant_message(msg.get("content", ""))
        
        self.session_store.save(session)
        return session_id
    
    def import_session_from_file(self, filepath: str) -> str:
        """Import a session from a JSON file.
        
        Args:
            filepath: Path to the input file.
        
        Returns:
            The imported session ID.
        """
        with open(filepath) as f:
            data = json.load(f)
        
        return self.import_session(data)

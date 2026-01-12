"""
History Store for Dynamic Context Discovery.

Persists conversation history to artifacts for loss recovery during summarization.
Implements HistoryStoreProtocol.

Usage:
    from praisonai.context import HistoryStore
    
    store = HistoryStore(base_dir="~/.praison/runs")
    
    # Append messages
    store.append({"role": "user", "content": "Hello"}, agent_id="agent1", run_id="run123")
    
    # Get reference for summary pointer
    ref = store.get_ref(agent_id="agent1", run_id="run123")
    
    # Search history
    matches = store.search("error", agent_id="agent1", run_id="run123")
"""

import json
import re
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from praisonaiagents.context.artifacts import (
    ArtifactRef,
    GrepMatch,
    compute_checksum,
)

logger = logging.getLogger(__name__)


class HistoryStore:
    """
    Filesystem-backed conversation history storage.
    
    Stores history as JSONL files (one message per line) for efficient
    appending and searching.
    
    Directory layout:
    ~/.praison/runs/{run_id}/history/{agent_id}.jsonl
    
    Features:
    - Append-only for performance
    - JSONL format for streaming reads
    - Regex search support
    - Turn-based retrieval
    """
    
    def __init__(self, base_dir: str = "~/.praison/runs"):
        """
        Initialize the history store.
        
        Args:
            base_dir: Base directory for history storage
        """
        self.base_dir = Path(base_dir).expanduser().resolve()
    
    def _get_history_path(self, run_id: str, agent_id: str) -> Path:
        """Get the path to the history file."""
        history_dir = self.base_dir / run_id / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        return history_dir / f"{agent_id}.jsonl"
    
    def append(
        self,
        message: Dict[str, Any],
        agent_id: str,
        run_id: str,
    ) -> None:
        """
        Append a message to history.
        
        Args:
            message: The message dict (role, content, etc.)
            agent_id: ID of the agent
            run_id: ID of the run/session
        """
        history_path = self._get_history_path(run_id, agent_id)
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message = {**message, "timestamp": time.time()}
        
        # Append as JSONL
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(message, default=str) + "\n")
    
    def get_ref(self, agent_id: str, run_id: str) -> Optional[ArtifactRef]:
        """
        Get artifact reference for history file.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            
        Returns:
            ArtifactRef if history exists, None otherwise
        """
        history_path = self._get_history_path(run_id, agent_id)
        
        if not history_path.exists():
            return None
        
        # Get file stats
        stat = history_path.stat()
        size_bytes = stat.st_size
        
        # Count messages for summary
        message_count = 0
        with open(history_path, "r", encoding="utf-8") as f:
            for _ in f:
                message_count += 1
        
        # Compute checksum
        content = history_path.read_bytes()
        checksum = compute_checksum(content)
        
        return ArtifactRef(
            path=str(history_path),
            summary=f"Conversation history with {message_count} messages",
            size_bytes=size_bytes,
            mime_type="application/jsonl",
            checksum=checksum,
            created_at=stat.st_mtime,
            artifact_id=f"history_{agent_id}",
            agent_id=agent_id,
            run_id=run_id,
        )
    
    def search(
        self,
        query: str,
        agent_id: str,
        run_id: str,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search history for matching messages.
        
        Args:
            query: Search query (supports regex)
            agent_id: ID of the agent
            run_id: ID of the run/session
            max_results: Maximum results to return
            
        Returns:
            List of matching message dicts
        """
        history_path = self._get_history_path(run_id, agent_id)
        
        if not history_path.exists():
            return []
        
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            # Fall back to literal search
            pattern = re.compile(re.escape(query), re.IGNORECASE)
        
        matches = []
        with open(history_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                try:
                    message = json.loads(line)
                    content = message.get("content", "")
                    if isinstance(content, str) and pattern.search(content):
                        message["_line_number"] = line_num
                        matches.append(message)
                        if len(matches) >= max_results:
                            break
                except json.JSONDecodeError:
                    continue
        
        return matches
    
    def get_messages(
        self,
        agent_id: str,
        run_id: str,
        start_turn: int = 0,
        end_turn: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get messages from history.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            start_turn: Starting turn number (0-indexed)
            end_turn: Ending turn number (None for all)
            
        Returns:
            List of message dicts
        """
        history_path = self._get_history_path(run_id, agent_id)
        
        if not history_path.exists():
            return []
        
        messages = []
        with open(history_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < start_turn:
                    continue
                if end_turn is not None and i >= end_turn:
                    break
                try:
                    message = json.loads(line)
                    messages.append(message)
                except json.JSONDecodeError:
                    continue
        
        return messages
    
    def get_last_messages(
        self,
        agent_id: str,
        run_id: str,
        count: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get the last N messages from history.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            count: Number of messages to return
            
        Returns:
            List of message dicts (most recent last)
        """
        history_path = self._get_history_path(run_id, agent_id)
        
        if not history_path.exists():
            return []
        
        # Read all messages (could be optimized for large files)
        all_messages = []
        with open(history_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    message = json.loads(line)
                    all_messages.append(message)
                except json.JSONDecodeError:
                    continue
        
        return all_messages[-count:]
    
    def grep(
        self,
        pattern: str,
        agent_id: str,
        run_id: str,
        context_lines: int = 0,
        max_matches: int = 50,
    ) -> List[GrepMatch]:
        """
        Search history with grep-like interface.
        
        Args:
            pattern: Regex pattern to search for
            agent_id: ID of the agent
            run_id: ID of the run/session
            context_lines: Number of context messages before/after
            max_matches: Maximum matches to return
            
        Returns:
            List of GrepMatch objects
        """
        history_path = self._get_history_path(run_id, agent_id)
        
        if not history_path.exists():
            return []
        
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)
        
        # Read all lines for context
        all_lines = []
        with open(history_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        matches = []
        for i, line in enumerate(all_lines):
            try:
                message = json.loads(line)
                content = message.get("content", "")
                if isinstance(content, str) and regex.search(content):
                    # Get context
                    start = max(0, i - context_lines)
                    end = min(len(all_lines), i + context_lines + 1)
                    
                    match = GrepMatch(
                        line_number=i + 1,
                        line_content=line.rstrip("\n"),
                        context_before=[ln.rstrip("\n") for ln in all_lines[start:i]],
                        context_after=[ln.rstrip("\n") for ln in all_lines[i+1:end]],
                    )
                    matches.append(match)
                    
                    if len(matches) >= max_matches:
                        break
            except json.JSONDecodeError:
                continue
        
        return matches
    
    def clear(self, agent_id: str, run_id: str) -> bool:
        """
        Clear history for an agent.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            
        Returns:
            True if cleared successfully
        """
        history_path = self._get_history_path(run_id, agent_id)
        
        if history_path.exists():
            history_path.unlink()
            return True
        return False
    
    def export(
        self,
        agent_id: str,
        run_id: str,
        format: str = "jsonl",
    ) -> str:
        """
        Export history in specified format.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            format: Export format (jsonl, json, text)
            
        Returns:
            Exported content as string
        """
        messages = self.get_messages(agent_id, run_id)
        
        if format == "jsonl":
            return "\n".join(json.dumps(m, default=str) for m in messages)
        elif format == "json":
            return json.dumps(messages, indent=2, default=str)
        elif format == "text":
            lines = []
            for m in messages:
                role = m.get("role", "unknown")
                content = m.get("content", "")
                lines.append(f"[{role}]: {content}")
            return "\n\n".join(lines)
        else:
            raise ValueError(f"Unknown format: {format}")


def create_history_pointer(ref: ArtifactRef) -> str:
    """
    Create a history pointer string for inclusion in summaries.
    
    This pointer allows agents to recover full conversation history
    after summarization.
    
    Args:
        ref: ArtifactRef to the history file
        
    Returns:
        Formatted pointer string
    """
    return (
        f"[Full conversation history available at: {ref.path}]\n"
        f"[{ref.summary}]\n"
        f"[Use history_search or history_tail tools to retrieve details]"
    )


def create_history_tools(
    store: Optional[HistoryStore] = None,
    base_dir: str = "~/.praison/runs",
):
    """
    Create tools for agents to interact with history.
    
    Returns a list of tool functions that can be passed to Agent(tools=[...]).
    
    Tools created:
    - history_search: Search conversation history
    - history_tail: Get recent messages
    - history_get: Get messages by turn range
    
    Example:
        tools = create_history_tools()
        agent = Agent(name="MyAgent", tools=tools)
    """
    history_store = store or HistoryStore(base_dir=base_dir)
    
    def history_search(
        query: str,
        agent_id: str = "default",
        run_id: str = "default",
        max_results: int = 10,
    ) -> str:
        """
        Search conversation history for matching messages.
        
        Args:
            query: Search query (supports regex patterns)
            agent_id: ID of the agent whose history to search
            run_id: ID of the run/session
            max_results: Maximum number of results to return
            
        Returns:
            Formatted string with matching messages
        """
        matches = history_store.search(
            query=query,
            agent_id=agent_id,
            run_id=run_id,
            max_results=max_results,
        )
        
        if not matches:
            return f"No messages found matching: {query}"
        
        result_lines = [f"Found {len(matches)} matching messages:"]
        for m in matches:
            role = m.get("role", "unknown")
            content = m.get("content", "")[:200]
            line_num = m.get("_line_number", "?")
            result_lines.append(f"\n[{line_num}] {role}: {content}...")
        
        return "\n".join(result_lines)
    
    def history_tail(
        agent_id: str = "default",
        run_id: str = "default",
        count: int = 10,
    ) -> str:
        """
        Get the most recent messages from conversation history.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            count: Number of recent messages to return
            
        Returns:
            Formatted string with recent messages
        """
        messages = history_store.get_last_messages(
            agent_id=agent_id,
            run_id=run_id,
            count=count,
        )
        
        if not messages:
            return "No history found."
        
        result_lines = [f"Last {len(messages)} messages:"]
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            result_lines.append(f"\n[{role}]: {content}")
        
        return "\n".join(result_lines)
    
    def history_get(
        agent_id: str = "default",
        run_id: str = "default",
        start_turn: int = 0,
        end_turn: Optional[int] = None,
    ) -> str:
        """
        Get messages from history by turn range.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            start_turn: Starting turn number (0-indexed)
            end_turn: Ending turn number (None for all remaining)
            
        Returns:
            Formatted string with messages
        """
        messages = history_store.get_messages(
            agent_id=agent_id,
            run_id=run_id,
            start_turn=start_turn,
            end_turn=end_turn,
        )
        
        if not messages:
            return "No messages in specified range."
        
        result_lines = [f"Messages {start_turn} to {end_turn or 'end'}:"]
        for i, m in enumerate(messages, start=start_turn):
            role = m.get("role", "unknown")
            content = m.get("content", "")
            result_lines.append(f"\n[{i}] {role}: {content}")
        
        return "\n".join(result_lines)
    
    return [history_search, history_tail, history_get]

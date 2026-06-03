"""
Context Compressor for PraisonAI Agents.

Provides LLM-driven context compression with session lineage tracking.
Implements the architecture described in issue #1806.
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
import json
import uuid
from datetime import datetime

from ..llm.protocols import LLMProviderProtocol
from .tokens import estimate_messages_tokens, get_estimator


@dataclass
class CompressResult:
    """Result of context compression operation."""
    messages: List[Dict[str, Any]]
    tokens_saved: int
    original_tokens: int
    final_tokens: int
    compression_ratio: float
    session_id: Optional[str] = None
    parent_session_id: Optional[str] = None
    summary_token_count: int = 0
    head_preserved_count: int = 0
    tail_preserved_count: int = 0
    middle_compressed_count: int = 0
    
    @property
    def compression_efficiency(self) -> float:
        """Percentage of tokens saved."""
        if self.original_tokens == 0:
            return 0.0
        return (self.tokens_saved / self.original_tokens) * 100


@dataclass
class CompressionSession:
    """Tracks compression lineage and session state."""
    session_id: str
    parent_session_id: Optional[str]
    created_at: datetime
    original_message_count: int
    compressed_message_count: int
    original_tokens: int
    compressed_tokens: int
    summary_text: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "created_at": self.created_at.isoformat(),
            "original_message_count": self.original_message_count,
            "compressed_message_count": self.compressed_message_count,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "summary_text": self.summary_text,
        }


class ContextCompressor:
    """
    LLM-driven context compression with session lineage tracking.
    
    Implements intelligent compression that:
    1. Protects head and tail messages (system prompt + recent context)
    2. Compresses the middle using LLM summarization
    3. Tracks session lineage for traceability
    4. Falls back to deterministic summaries on LLM failure
    
    Example:
        compressor = ContextCompressor(llm=agent.llm)
        result = await compressor.compress(
            messages,
            protect_last_n_tokens=20_000,
            summary_target_tokens=750
        )
    """
    
    def __init__(
        self,
        llm: Optional[LLMProviderProtocol] = None,
        tokenizer: Optional[Any] = None,
        auxiliary_model: Optional[str] = None,
        enable_session_tracking: bool = True,
    ):
        """
        Initialize context compressor.
        
        Args:
            llm: LLM client for summarization (optional)
            tokenizer: Token estimator (optional, defaults to heuristic)
            auxiliary_model: Specific model for summarization (optional)
            enable_session_tracking: Track compression lineage
        """
        self.llm = llm
        self.tokenizer = tokenizer or get_estimator()
        self.auxiliary_model = auxiliary_model
        self.enable_session_tracking = enable_session_tracking
        self._session_history: List[CompressionSession] = []
    
    async def compress(
        self,
        messages: List[Dict[str, Any]],
        *,
        protect_last_n_tokens: int = 20_000,
        summary_target_tokens: int = 750,
        auxiliary_model: Optional[str] = None,
    ) -> CompressResult:
        """
        Compress messages using LLM-driven summarization.
        
        Args:
            messages: Messages to compress
            protect_last_n_tokens: Tokens to preserve at end (recent context)
            summary_target_tokens: Target token count for summary
            auxiliary_model: Override model for summarization
            
        Returns:
            CompressResult with compressed messages and metadata
        """
        original_tokens = self._count_tokens(messages)
        
        # Protect head (system prompt + initial framing)
        head = self._protect_head(messages)
        
        # Find tail boundary (protect recent context)
        tail = self._find_tail_by_tokens(messages, protect_last_n_tokens)
        
        # Extract middle for compression
        head_count = len(head)
        tail_start = len(messages) - len(tail)
        middle = messages[head_count:tail_start] if tail_start > head_count else []
        
        # Create session tracking
        session_id = None
        parent_session_id = None
        if self.enable_session_tracking:
            session_id = str(uuid.uuid4())
            # In a real implementation, you might pass in the current session ID as parent
            parent_session_id = None  # Could be passed in as parameter
        
        # Compress middle section
        if middle:
            summary_text = await self._summarize_with_llm(
                middle, 
                summary_target_tokens,
                auxiliary_model or self.auxiliary_model
            )
            
            if summary_text:
                summary_msg = {
                    "role": "system", 
                    "content": f"[Context Summary]\n{summary_text}",
                    "_compression_metadata": {
                        "original_message_count": len(middle),
                        "summary_tokens": self._count_tokens([{"content": summary_text}]),
                        "compressed_at": datetime.utcnow().isoformat(),
                        "session_id": session_id,
                        "parent_session_id": parent_session_id,
                    }
                }
                compressed_messages = head + [summary_msg] + tail
            else:
                # Fallback: use deterministic summary
                fallback_summary = self._create_fallback_summary(middle)
                summary_msg = {
                    "role": "system",
                    "content": f"[Fallback Summary]\n{fallback_summary}",
                    "_compression_metadata": {
                        "original_message_count": len(middle),
                        "fallback": True,
                        "compressed_at": datetime.utcnow().isoformat(),
                        "session_id": session_id,
                    }
                }
                compressed_messages = head + [summary_msg] + tail
        else:
            # No middle to compress
            compressed_messages = head + tail
            summary_text = None
        
        final_tokens = self._count_tokens(compressed_messages)
        tokens_saved = original_tokens - final_tokens
        
        # Record session if tracking enabled
        if self.enable_session_tracking and session_id:
            compression_session = CompressionSession(
                session_id=session_id,
                parent_session_id=parent_session_id,
                created_at=datetime.utcnow(),
                original_message_count=len(messages),
                compressed_message_count=len(compressed_messages),
                original_tokens=original_tokens,
                compressed_tokens=final_tokens,
                summary_text=summary_text,
            )
            self._session_history.append(compression_session)
        
        return CompressResult(
            messages=compressed_messages,
            tokens_saved=max(0, tokens_saved),
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            compression_ratio=final_tokens / original_tokens if original_tokens > 0 else 1.0,
            session_id=session_id,
            parent_session_id=parent_session_id,
            summary_token_count=self._count_tokens([{"content": summary_text}]) if summary_text else 0,
            head_preserved_count=len(head),
            tail_preserved_count=len(tail),
            middle_compressed_count=len(middle),
        )
    
    def _protect_head(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Protect head messages (system prompt + initial framing).
        
        Returns first system message and first user/assistant exchange.
        """
        head = []
        
        # Always include first system message
        for msg in messages:
            if msg.get("role") == "system":
                head.append(msg)
                break
        
        # Include first framing exchange (first user + first assistant response)
        user_found = False
        assistant_found = False
        
        for msg in messages:
            role = msg.get("role")
            
            if role == "user" and not user_found:
                head.append(msg)
                user_found = True
            elif role == "assistant" and user_found and not assistant_found:
                head.append(msg)
                assistant_found = True
                break
        
        return head
    
    def _find_tail_by_tokens(
        self, 
        messages: List[Dict[str, Any]], 
        protect_tokens: int
    ) -> List[Dict[str, Any]]:
        """
        Find tail messages to preserve based on token count.
        
        Args:
            messages: All messages
            protect_tokens: Number of tokens to preserve from end
            
        Returns:
            Tail messages within token budget
        """
        tail = []
        current_tokens = 0
        
        # Work backwards from end, but don't include head messages
        head_msg_ids = {id(msg) for msg in self._protect_head(messages)}
        
        for msg in reversed(messages):
            # Skip if this message is already in head
            if id(msg) in head_msg_ids:
                continue
                
            msg_tokens = self._count_tokens([msg])
            if current_tokens + msg_tokens <= protect_tokens:
                tail.insert(0, msg)  # Insert at beginning to maintain order
                current_tokens += msg_tokens
            else:
                break
        
        return tail
    
    async def _summarize_with_llm(
        self, 
        messages: List[Dict[str, Any]], 
        max_tokens: int,
        model: Optional[str] = None
    ) -> Optional[str]:
        """
        Use LLM to create intelligent summary.
        
        Args:
            messages: Messages to summarize
            max_tokens: Maximum tokens for summary
            model: Model to use for summarization
            
        Returns:
            Summary string or None if failed
        """
        if not self.llm:
            return None
        
        try:
            # Build context from messages
            context_parts = []
            file_refs = set()
            tool_calls = []
            decisions = []
            
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                
                # Extract structured information
                if role == "tool":
                    tool_name = msg.get("name", "unknown")
                    tool_calls.append(f"Called {tool_name}")
                    
                    # Extract file references
                    if isinstance(content, str):
                        # Simple heuristic for file paths
                        import re
                        file_matches = re.findall(r'[^\s]+\.[a-zA-Z]{1,4}(?:\s|$|:)', content)
                        file_refs.update(file_matches)
                
                elif role == "assistant" and content:
                    # Look for decision-like patterns
                    if any(keyword in content.lower() for keyword in 
                           ["i will", "let me", "i'll", "decided to", "plan to"]):
                        decisions.append(content[:200] + "..." if len(content) > 200 else content)
                
                # Add to context
                if isinstance(content, str) and content.strip():
                    # Truncate very long content
                    truncated = content[:1000] if len(content) > 1000 else content
                    context_parts.append(f"[{role}]: {truncated}")
            
            # Build structured prompt
            summary_prompt = f"""Summarize this conversation history concisely, preserving key information for context continuity. Focus on:

1. **Resolved Tasks**: What was accomplished
2. **In-Progress Tasks**: What is currently being worked on  
3. **Key Tool Usage**: Important tool calls and results
4. **File References**: Files that were accessed or modified
5. **Decisions Made**: Important choices or directions taken

Conversation History:
{chr(10).join(context_parts[:20])}  # Limit to prevent prompt overflow

Tool Calls Made: {", ".join(tool_calls) if tool_calls else "None"}
Files Referenced: {", ".join(list(file_refs)[:10]) if file_refs else "None"}

Provide a concise summary under {max_tokens} tokens that preserves the essential context for continuing this conversation."""

            # Make LLM call
            if hasattr(self.llm, 'complete'):
                # Direct completion method
                response = await self.llm.complete(
                    prompt=summary_prompt,
                    max_tokens=max_tokens,
                    model=model
                )
                return response.get("content") or response.get("text")
            
            elif hasattr(self.llm, 'chat'):
                # Chat completion method
                response = await self.llm.chat(
                    messages=[{"role": "user", "content": summary_prompt}],
                    max_tokens=max_tokens,
                    model=model
                )
                return response.get("content")
            
            else:
                # Try common OpenAI-compatible interface
                response = self.llm.chat.completions.create(
                    model=model or "gpt-4o-mini",
                    messages=[{"role": "user", "content": summary_prompt}],
                    max_tokens=max_tokens,
                    temperature=0.3,
                )
                return response.choices[0].message.content
                
        except Exception as e:
            # Log error but don't raise - fallback will handle
            import logging
            logging.warning(f"LLM summarization failed: {e}")
            return None
    
    def _create_fallback_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Create deterministic fallback summary when LLM fails.
        
        Args:
            messages: Messages to summarize
            
        Returns:
            Structured fallback summary
        """
        tool_calls = []
        files_touched = set()
        message_counts = {"user": 0, "assistant": 0, "tool": 0, "system": 0}
        
        for msg in messages:
            role = msg.get("role", "unknown")
            message_counts[role] = message_counts.get(role, 0) + 1
            
            if role == "tool":
                tool_name = msg.get("name", "unknown")
                tool_calls.append(tool_name)
                
                # Extract file references from content
                content = msg.get("content", "")
                if isinstance(content, str):
                    import re
                    file_matches = re.findall(r'[^\s]+\.[a-zA-Z]{1,4}', content)
                    files_touched.update(file_matches)
        
        summary_parts = [
            f"Previous conversation: {len(messages)} messages",
            f"Message breakdown: {dict(message_counts)}",
        ]
        
        if tool_calls:
            summary_parts.append(f"Tools used: {', '.join(set(tool_calls))}")
        
        if files_touched:
            file_list = list(files_touched)[:5]  # Limit to 5 files
            more_indicator = f" (+{len(files_touched) - 5} more)" if len(files_touched) > 5 else ""
            summary_parts.append(f"Files referenced: {', '.join(file_list)}{more_indicator}")
        
        return "\n".join(summary_parts)
    
    def _count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count tokens in messages using configured estimator."""
        if hasattr(self.tokenizer, 'estimate_messages'):
            return self.tokenizer.estimate_messages(messages)
        elif hasattr(self.tokenizer, 'estimate'):
            # Fallback: count content tokens
            total = 0
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str):
                    total += self.tokenizer.estimate(content)
                total += 10  # Role overhead
            return total
        else:
            # Ultimate fallback: use heuristic
            return estimate_messages_tokens(messages)
    
    def get_session_history(self) -> List[CompressionSession]:
        """Get compression session history for lineage tracking."""
        return self._session_history.copy()
    
    def get_session_by_id(self, session_id: str) -> Optional[CompressionSession]:
        """Get specific compression session by ID."""
        for session in self._session_history:
            if session.session_id == session_id:
                return session
        return None
    
    def clear_session_history(self) -> None:
        """Clear compression session history."""
        self._session_history.clear()
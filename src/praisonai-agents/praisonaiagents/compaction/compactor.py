"""
Context Compactor for PraisonAI Agents.

Manages context window by compacting messages when needed.
"""

from typing import List, Dict, Any, Optional

from .config import CompactionConfig
from .strategy import CompactionStrategy
from .result import CompactionResult


class ContextCompactor:
    """
    Compacts conversation context to fit within token limits.
    
    Example:
        compactor = ContextCompactor(max_tokens=8000)
        
        # Check if compaction needed
        if compactor.needs_compaction(messages):
            result = compactor.compact(messages)
            messages = result.messages
    """
    
    def __init__(
        self,
        max_tokens: int = 8000,
        target_tokens: Optional[int] = None,
        strategy: CompactionStrategy = CompactionStrategy.TRUNCATE,
        preserve_system: bool = True,
        preserve_recent: int = 5
    ):
        """
        Initialize the compactor.
        
        Args:
            max_tokens: Maximum tokens before compaction
            target_tokens: Target tokens after compaction
            strategy: Compaction strategy to use
            preserve_system: Keep system messages
            preserve_recent: Number of recent messages to preserve
        """
        self.max_tokens = max_tokens
        self.target_tokens = target_tokens or int(max_tokens * 0.75)
        self.strategy = strategy
        self.preserve_system = preserve_system
        self.preserve_recent = preserve_recent
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        # Rough estimate: ~4 chars per token
        return len(text) // 4
    
    def count_message_tokens(self, message: Dict[str, Any]) -> int:
        """Count tokens in a message."""
        content = message.get("content", "")
        if isinstance(content, str):
            return self.estimate_tokens(content)
        elif isinstance(content, list):
            # Handle multi-part content
            total = 0
            for part in content:
                if isinstance(part, dict):
                    total += self.estimate_tokens(str(part.get("text", "")))
                else:
                    total += self.estimate_tokens(str(part))
            return total
        return 0
    
    def count_total_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count total tokens in messages."""
        return sum(self.count_message_tokens(m) for m in messages)
    
    def needs_compaction(self, messages: List[Dict[str, Any]]) -> bool:
        """Check if messages need compaction."""
        return self.count_total_tokens(messages) > self.max_tokens
    
    def compact(
        self,
        messages: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], CompactionResult]:
        """
        Compact messages to fit within token limit.
        
        Args:
            messages: List of messages to compact
            
        Returns:
            Tuple of (compacted messages, result)
        """
        original_tokens = self.count_total_tokens(messages)
        
        if original_tokens <= self.max_tokens:
            return messages, CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages_removed=0,
                messages_kept=len(messages),
                strategy_used=self.strategy
            )
        
        if self.strategy == CompactionStrategy.TRUNCATE:
            compacted = self._truncate(messages)
        elif self.strategy == CompactionStrategy.SLIDING:
            compacted = self._sliding_window(messages)
        elif self.strategy == CompactionStrategy.SUMMARIZE:
            compacted = self._summarize(messages)
        elif self.strategy == CompactionStrategy.SMART:
            compacted = self._smart_compact(messages)
        elif self.strategy == CompactionStrategy.PRUNE:
            compacted = self._prune(messages)
        elif self.strategy == CompactionStrategy.LLM_SUMMARIZE:
            compacted = self._llm_summarize(messages)
        else:
            compacted = self._truncate(messages)
        
        compacted_tokens = self.count_total_tokens(compacted)
        
        result = CompactionResult(
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages_removed=len(messages) - len(compacted),
            messages_kept=len(compacted),
            strategy_used=self.strategy
        )
        
        return compacted, result
    
    def _truncate(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Truncate oldest messages."""
        result = []
        
        # Separate system and non-system messages
        system_msgs = []
        other_msgs = []
        
        for msg in messages:
            if self.preserve_system and msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)
        
        # Always keep system messages
        result.extend(system_msgs)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:] if other_msgs else []
        
        # Add recent messages
        result.extend(recent)
        
        # If still over limit, truncate more
        while self.count_total_tokens(result) > self.target_tokens and len(result) > 1:
            # Remove oldest non-system message
            for i, msg in enumerate(result):
                if msg.get("role") != "system":
                    result.pop(i)
                    break
        
        return result
    
    def _sliding_window(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep a sliding window of recent messages."""
        result = []
        
        # Keep system messages
        for msg in messages:
            if self.preserve_system and msg.get("role") == "system":
                result.append(msg)
        
        # Add messages from end until we hit target
        non_system = [m for m in messages if m.get("role") != "system"]
        
        for msg in reversed(non_system):
            if self.count_total_tokens(result + [msg]) <= self.target_tokens:
                result.insert(len([m for m in result if m.get("role") == "system"]), msg)
            else:
                break
        
        # Ensure messages are in order
        system_msgs = [m for m in result if m.get("role") == "system"]
        other_msgs = [m for m in result if m.get("role") != "system"]
        
        return system_msgs + other_msgs
    
    def _summarize(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Summarize old messages (simplified version)."""
        result = []
        
        # Keep system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:]
        
        # Summarize older messages
        older = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
        
        if older:
            # Create a simple summary
            summary_parts = []
            for msg in older:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    # Take first 100 chars
                    summary_parts.append(f"{role}: {content[:100]}...")
            
            if summary_parts:
                summary = "[Previous conversation summary]\n" + "\n".join(summary_parts[:5])
                result.append({
                    "role": "system",
                    "content": summary
                })
        
        result.extend(recent)
        
        return result
    
    def _smart_compact(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Smart compaction based on message importance."""
        # For now, use sliding window as base
        return self._sliding_window(messages)
    
    def _prune(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prune old tool outputs while keeping tool calls.
        
        This reduces token usage by removing verbose tool outputs
        from older messages while preserving the context of what
        tools were called.
        """
        result = []
        
        # Separate system and other messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages intact
        recent = other_msgs[-self.preserve_recent:]
        older = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
        
        # Prune older messages
        for msg in older:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # If this is a tool result, truncate it (use smart format)
            if role == "tool" or msg.get("tool_call_id"):
                if isinstance(content, str) and len(content) > 500:
                    pruned_msg = msg.copy()
                    tail_size = min(100, len(content) // 5)
                    head = content[:200]
                    tail = content[-tail_size:] if tail_size > 0 else ""
                    pruned_msg["content"] = f"{head}\n...[{len(content):,} chars, showing first/last portions]...\n{tail}"
                    result.append(pruned_msg)
                else:
                    result.append(msg)
            else:
                result.append(msg)
        
        result.extend(recent)
        return result
    
    def _llm_summarize(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Use LLM to summarize older messages.
        
        Note: This is a placeholder that returns a structured summary.
        Actual LLM integration should be done at the agent level.
        """
        result = []
        
        # Keep system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:]
        older = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
        
        if older:
            # Create structured summary for LLM to process
            summary_parts = []
            for msg in older:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    # Extract key information
                    summary_parts.append(f"[{role}]: {content[:150]}...")
            
            if summary_parts:
                summary = (
                    "[Compacted conversation history - summarize key points]\n"
                    + "\n".join(summary_parts[:10])
                )
                result.append({
                    "role": "system",
                    "content": summary,
                    "_compacted": True,
                    "_original_count": len(older),
                })
        
        result.extend(recent)
        return result
    
    def get_stats(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about messages."""
        total_tokens = self.count_total_tokens(messages)
        
        return {
            "message_count": len(messages),
            "total_tokens": total_tokens,
            "max_tokens": self.max_tokens,
            "target_tokens": self.target_tokens,
            "needs_compaction": total_tokens > self.max_tokens,
            "utilization": total_tokens / self.max_tokens if self.max_tokens > 0 else 0
        }

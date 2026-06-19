"""
Context Compactor for PraisonAI Agents.

Manages context window by compacting messages when needed.
"""

import re
from typing import List, Dict, Any, Optional, Callable, Awaitable, Tuple
import asyncio

from .config import CompactionConfig, COMPACTION_PREFIX, SUMMARY_TEMPLATE
from .strategy import CompactionStrategy
from .result import CompactionResult
from .protocols import ToolResultPrunerProtocol, MessageFormatterProtocol, SummaryBuilderProtocol


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
        preserve_recent: int = 5,
        config: Optional[CompactionConfig] = None,
        llm_summarize_fn: Optional[Callable[[str], Awaitable[str]]] = None,
        tool_pruner: Optional[ToolResultPrunerProtocol] = None,
        message_formatter: Optional[MessageFormatterProtocol] = None,
        summary_builder: Optional[SummaryBuilderProtocol] = None
    ):
        """
        Initialize the compactor.
        
        Args:
            max_tokens: Maximum tokens before compaction
            target_tokens: Target tokens after compaction
            strategy: Compaction strategy to use
            preserve_system: Keep system messages
            preserve_recent: Number of recent messages to preserve
            config: Optional CompactionConfig for advanced settings
            llm_summarize_fn: Async function to call LLM for summarization
            tool_pruner: Protocol implementation for tool result pruning
            message_formatter: Protocol implementation for message formatting
            summary_builder: Protocol implementation for summary building
        """
        # Use provided config or create default
        self.config = config or CompactionConfig(
            max_tokens=max_tokens,
            target_tokens=target_tokens or int(max_tokens * 0.75),
            preserve_system=preserve_system,
            preserve_recent=preserve_recent
        )
        
        # Set instance attributes from config to ensure consistency
        self.max_tokens = self.config.max_tokens
        self.target_tokens = self.config.target_tokens
        self.strategy = strategy
        self.preserve_system = self.config.preserve_system
        self.preserve_recent = self.config.preserve_recent
        self.llm_summarize_fn = llm_summarize_fn
        
        # Protocol implementations (defaults to None - no heavy implementations in core)
        self.tool_pruner = tool_pruner
        self.message_formatter = message_formatter  
        self.summary_builder = summary_builder
        
        # Anti-thrashing state tracking
        self._last_savings_pct: float = 100.0  # Start high to allow first compaction
        self._low_savings_streak: int = 0
        
        # Iterative summary state
        self._previous_summary: Optional[str] = None
        self._previous_summary_global_idx: int = 0
        
        # Reset state tracking for each compact() call
        self._used_previous_summary: bool = False
    
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
        """
        Check if messages need compaction with anti-thrashing protection.
        
        Returns False if:
        - Token count is below threshold
        - We've had too many consecutive low-savings attempts
        """
        if self.count_total_tokens(messages) <= self.max_tokens:
            return False
            
        # Anti-thrashing: skip if we've had too many low-savings attempts
        if self._low_savings_streak >= self.config.max_consecutive_low_savings:
            return False
            
        return True
    
    def compact(
        self,
        messages: List[Dict[str, Any]],
        focus_topic: str = ""
    ) -> tuple[List[Dict[str, Any]], CompactionResult]:
        """
        Compact messages to fit within token limit (synchronous version).
        
        For LLM_SUMMARIZE strategy, falls back to naive summarization if no LLM function provided.
        Use compact_async for proper LLM integration.
        
        Args:
            messages: List of messages to compact
            focus_topic: Optional topic to focus on during summarization
            
        Returns:
            Tuple of (compacted messages, result)
        """
        # Reset state for this compaction call
        self._used_previous_summary = False
        
        original_tokens = self.count_total_tokens(messages)
        
        if original_tokens <= self.max_tokens:
            result = CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages_removed=0,
                messages_kept=len(messages),
                strategy_used=self.strategy
            )
            result.calculate_savings_pct()
            return messages, result
        
        # Apply tool result deduplication pre-pass if enabled
        processed_messages = messages
        tool_results_pruned = 0
        if self.config.tool_prune_before_summarise and self.tool_pruner:
            processed_messages, tool_results_pruned = self.tool_pruner.prune(
                messages, 
                self.config.max_tool_result_size
            )
        
        # Skip early exit - proceed with full compaction strategy
        # Anti-thrashing check will be applied after strategy runs
        
        if self.strategy == CompactionStrategy.TRUNCATE:
            compacted = self._truncate(processed_messages)
        elif self.strategy == CompactionStrategy.SLIDING:
            compacted = self._sliding_window(processed_messages)
        elif self.strategy == CompactionStrategy.SUMMARIZE:
            compacted = self._summarize(processed_messages)
        elif self.strategy == CompactionStrategy.SMART:
            compacted = self._smart_compact(processed_messages)
        elif self.strategy == CompactionStrategy.PRUNE:
            compacted = self._prune(processed_messages)
        elif self.strategy == CompactionStrategy.LLM_SUMMARIZE:
            if self.llm_summarize_fn:
                # For sync calls with LLM function, we need to run async
                try:
                    # Check if we're already in an async context
                    try:
                        loop = asyncio.get_running_loop()
                        # If in async context, fallback to naive summarization
                        compacted = self._summarize(processed_messages)
                    except RuntimeError:
                        # No running loop, safe to create one
                        compacted = asyncio.run(self._llm_summarize_async(processed_messages, focus_topic))
                except Exception:
                    # Fallback to naive summarization if async fails
                    compacted = self._summarize(processed_messages)
            else:
                compacted = self._llm_summarize(processed_messages, focus_topic)
        else:
            compacted = self._truncate(processed_messages)
        
        compacted_tokens = self.count_total_tokens(compacted)
        
        result = CompactionResult(
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages_removed=len(messages) - len(compacted),
            messages_kept=len(compacted),
            strategy_used=self.strategy,
            tool_results_pruned=tool_results_pruned,
            previous_summary_reused=getattr(self, '_used_previous_summary', False)
        )
        result.calculate_savings_pct()
        
        # Update anti-thrashing tracking based on actual results
        self._last_savings_pct = result.savings_pct
        if result.savings_pct >= self.config.min_savings_pct:
            self._low_savings_streak = 0
        else:
            self._low_savings_streak += 1
        
        return compacted, result

    async def compact_async(
        self,
        messages: List[Dict[str, Any]],
        focus_topic: str = ""
    ) -> tuple[List[Dict[str, Any]], CompactionResult]:
        """
        Compact messages to fit within token limit (asynchronous version).
        
        Args:
            messages: List of messages to compact
            focus_topic: Optional topic to focus on during summarization
            
        Returns:
            Tuple of (compacted messages, result)
        """
        # Reset state for this compaction call
        self._used_previous_summary = False
        
        original_tokens = self.count_total_tokens(messages)
        
        if original_tokens <= self.max_tokens:
            result = CompactionResult(
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
                messages_removed=0,
                messages_kept=len(messages),
                strategy_used=self.strategy
            )
            result.calculate_savings_pct()
            return messages, result
        
        # Apply tool result deduplication pre-pass if enabled
        processed_messages = messages
        tool_results_pruned = 0
        if self.config.tool_prune_before_summarise and self.tool_pruner:
            processed_messages, tool_results_pruned = self.tool_pruner.prune(
                messages, 
                self.config.max_tool_result_size
            )
        
        if self.strategy == CompactionStrategy.TRUNCATE:
            compacted = self._truncate(processed_messages)
        elif self.strategy == CompactionStrategy.SLIDING:
            compacted = self._sliding_window(processed_messages)
        elif self.strategy == CompactionStrategy.SUMMARIZE:
            compacted = self._summarize(processed_messages)
        elif self.strategy == CompactionStrategy.SMART:
            compacted = self._smart_compact(processed_messages)
        elif self.strategy == CompactionStrategy.PRUNE:
            compacted = self._prune(processed_messages)
        elif self.strategy == CompactionStrategy.LLM_SUMMARIZE:
            compacted = await self._llm_summarize_async(processed_messages, focus_topic)
        else:
            compacted = self._truncate(processed_messages)
        
        compacted_tokens = self.count_total_tokens(compacted)
        
        result = CompactionResult(
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages_removed=len(messages) - len(compacted),
            messages_kept=len(compacted),
            strategy_used=self.strategy,
            tool_results_pruned=tool_results_pruned,
            previous_summary_reused=getattr(self, '_used_previous_summary', False)
        )
        result.calculate_savings_pct()
        
        # Update anti-thrashing tracking based on actual results
        self._last_savings_pct = result.savings_pct
        if result.savings_pct >= self.config.min_savings_pct:
            self._low_savings_streak = 0
        else:
            self._low_savings_streak += 1
        
        return compacted, result
    
    def _prune_tool_results(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        Delegate tool result pruning to injected protocol implementation.
        
        If no tool pruner is provided, returns messages unchanged.
        This maintains backward compatibility while enforcing protocol-driven design.
        
        Returns:
            Tuple of (processed messages, number of tool results pruned)
        """
        if self.tool_pruner:
            return self.tool_pruner.prune(messages, self.config.max_tool_result_size)
        return messages, 0
    
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
            # Remove oldest message (respecting preserve_system setting)
            removed = False
            for i, msg in enumerate(result):
                # Skip system messages only if preserve_system is True
                if not (self.preserve_system and msg.get("role") == "system"):
                    result.pop(i)
                    removed = True
                    break
            if not removed:
                # Only system messages remain but still over budget — stop to avoid infinite loop
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
    
    def _llm_summarize(self, messages: List[Dict[str, Any]], focus_topic: str = "") -> List[Dict[str, Any]]:
        """
        Use LLM to summarize older messages with iterative support.
        
        Supports iterative summarization - if we have a previous summary,
        we only summarize the new messages since that summary.
        Also includes anti-injection framing when configured.
        
        Args:
            messages: List of messages to compact
            focus_topic: Optional topic to focus on during summarization
        """
        self._used_previous_summary = False
        result = []
        
        # Keep system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:]
        
        # Determine what to summarize
        total_original_messages = len(messages)
        if (self.config.enable_iterative_summary and 
            self._previous_summary and 
            total_original_messages > self._previous_summary_global_idx):
            # Iterative: summarize only new messages since previous summary
            # Calculate how many old messages to summarize based on global position
            messages_since_summary = total_original_messages - self._previous_summary_global_idx
            new_older_messages = max(0, messages_since_summary - self.preserve_recent)
            if new_older_messages > 0:
                to_summarize = other_msgs[-messages_since_summary:-self.preserve_recent]
            else:
                to_summarize = []
            self._used_previous_summary = True
        else:
            # Fresh summary: summarize all older messages
            to_summarize = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
            self._used_previous_summary = False
        
        if to_summarize or self._previous_summary:
            # Build summary content
            summary_parts = []
            
            # Include previous summary if doing iterative summarization
            if self._used_previous_summary and self._previous_summary:
                summary_parts.append(f"[Previous Summary]: {self._previous_summary}")
                summary_parts.append("[New Activity]:")
            
            # Add new messages to summarize
            for msg in to_summarize:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    # Extract key information with focus consideration
                    if focus_topic and focus_topic.lower() in content.lower():
                        # Prioritize content related to focus topic
                        summary_parts.append(f"[{role}] *FOCUS*: {content[:200]}...")
                    else:
                        summary_parts.append(f"[{role}]: {content[:150]}...")
            
            if summary_parts:
                focus_hint = f"\nFocus on: {focus_topic}" if focus_topic else ""
                
                if self._used_previous_summary:
                    summary = (
                        f"[Iterative conversation summary - update with new activity{focus_hint}]\n"
                        + "\n".join(summary_parts[:15])
                    )
                else:
                    summary = (
                        f"[Compacted conversation history - summarize key points{focus_hint}]\n"
                        + "\n".join(summary_parts[:10])
                    )
                
                # Apply anti-injection prefix if configured
                if hasattr(self.config, 'compaction_prefix') and self.config.compaction_prefix:
                    summary = f"{self.config.compaction_prefix}\n\n{summary}"
                
                summary_msg = {
                    "role": "system",
                    "content": summary,
                    "_compacted": True,
                    "_original_count": len(to_summarize),
                    "_iterative": self._used_previous_summary,
                    "_focus_topic": focus_topic
                }
                result.append(summary_msg)
                
                # Update tracking for future iterative summarization
                self._previous_summary = summary
                self._previous_summary_global_idx = len(messages)
        
        result.extend(recent)
        return result

    async def _llm_summarize_async(self, messages: List[Dict[str, Any]], focus_topic: str = "") -> List[Dict[str, Any]]:
        """
        Use LLM to intelligently summarize older messages.
        
        This method invokes the agent's LLM to create a meaningful summary
        that preserves key facts, identifiers, and the user's intent.
        
        Args:
            messages: List of messages to compact
            focus_topic: Optional topic to focus on during summarization
        """
        self._used_previous_summary = False
        result = []
        
        # Keep system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:]
        
        # Determine what to summarize based on iterative settings
        total_original_messages = len(messages)
        if (self.config.enable_iterative_summary and 
            self._previous_summary and 
            total_original_messages > self._previous_summary_global_idx):
            # Iterative: summarize only new messages since previous summary
            messages_since_summary = total_original_messages - self._previous_summary_global_idx
            new_older_messages = max(0, messages_since_summary - self.preserve_recent)
            if new_older_messages > 0:
                older = other_msgs[-messages_since_summary:-self.preserve_recent]
            else:
                older = []
            self._used_previous_summary = True
        else:
            # Fresh summary: summarize all older messages
            older = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
            self._used_previous_summary = False
        
        if older and self.llm_summarize_fn:
            try:
                # Format messages for summarization using protocol
                if self.message_formatter:
                    history_text = self.message_formatter.format_for_summary(older)
                else:
                    # Fallback to basic formatting if no protocol implementation
                    history_text = str(older)
                
                # Create summarization prompt that preserves important information
                focus_hint = f" Focus especially on: {focus_topic}." if focus_topic else ""
                iterative_hint = ""
                if self._used_previous_summary and self._previous_summary:
                    iterative_hint = f"\n\n[Previous Summary]: {self._previous_summary}\n[New Activity to Add]:"
                
                prompt = (
                    "Summarise the following conversation history. Preserve verbatim: "
                    "all file paths, IDs, hashes, URLs, task references, error messages, "
                    "tool outputs, and the user's requests. Be concise but complete. "
                    f"Focus on facts and actions taken, not general conversation.{focus_hint}"
                    f"{iterative_hint}\n\n{history_text}"
                )
                
                # Call the LLM for summarization
                summary = await self.llm_summarize_fn(prompt)
                
                # Add the LLM-generated summary as a system message
                summary_content = summary
                if self._used_previous_summary:
                    summary_content = f"[Iterative conversation summary]\n{summary}"
                else:
                    summary_content = f"[Previous conversation summary]\n{summary}"
                
                result.append({
                    "role": "system",
                    "content": summary_content,
                    "_compacted": True,
                    "_original_count": len(older),
                    "_llm_generated": True,
                    "_iterative": self._used_previous_summary,
                    "_focus_topic": focus_topic
                })
                
                # Update tracking for future iterative summarization
                self._previous_summary = summary
                self._previous_summary_global_idx = len(messages)
            except Exception as e:
                # Fallback to naive summarization if LLM call fails
                import logging
                logging.warning(f"LLM summarization failed, falling back to naive: {e}")
                summary_parts = []
                for msg in older:
                    role = msg.get("role", "unknown")
                    content = str(msg.get("content", ""))
                    if content:
                        # Extract key information
                        summary_parts.append(f"[{role}]: {content[:150]}...")
                
                if summary_parts:
                    summary = (
                        "[Compacted conversation history - LLM summarization failed]\n"
                        + "\n".join(summary_parts[:10])
                    )
                    result.append({
                        "role": "system",
                        "content": summary,
                        "_compacted": True,
                        "_original_count": len(older),
                        "_fallback": True,
                    })
        elif older:
            # Fallback to naive summarization if no LLM function
            summary_parts = []
            for msg in older:
                role = msg.get("role", "unknown")
                content = str(msg.get("content", ""))
                if content:
                    summary_parts.append(f"[{role}]: {content[:150]}...")
            
            if summary_parts:
                summary = (
                    "[Compacted conversation history - no LLM function]\n"
                    + "\n".join(summary_parts[:10])
                )
                result.append({
                    "role": "system",
                    "content": summary,
                    "_compacted": True,
                    "_original_count": len(older),
                    "_fallback": True,
                })
        
        result.extend(recent)
        return result

    def _format_messages_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Delegate message formatting to protocol implementation.
        
        If no formatter is provided, returns basic string representation.
        """
        if self.message_formatter:
            return self.message_formatter.format_for_summary(messages)
        return str(messages)
    
    def _build_structured_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Delegate structured summary building to protocol implementation.
        
        If no summary builder is provided, returns basic summary.
        """
        if self.summary_builder:
            return self.summary_builder.build_structured_summary(messages)
        return f"Summary of {len(messages)} messages"
    
    def _merge_summaries(self, previous: str, current: str) -> str:
        """
        Delegate summary merging to protocol implementation.
        
        If no summary builder is provided, returns current summary only.
        """
        if self.summary_builder:
            return self.summary_builder.merge_summaries(previous, current)
        return current
    
    def get_stats(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about messages."""
        total_tokens = self.count_total_tokens(messages)
        
        return {
            "message_count": len(messages),
            "total_tokens": total_tokens,
            "max_tokens": self.max_tokens,
            "target_tokens": self.target_tokens,
            "needs_compaction": total_tokens > self.max_tokens,
            "utilization": total_tokens / self.max_tokens if self.max_tokens > 0 else 0,
            "compaction_config": {
                "anti_injection_enabled": bool(self.config.compaction_prefix),
                "structured_template": self.config.structured_template,
                "iterative_update": self.config.iterative_update,
                "has_previous_summary": self._previous_summary is not None
            }
        }

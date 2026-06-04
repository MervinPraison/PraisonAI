"""
Context Compactor for PraisonAI Agents.

Manages context window by compacting messages when needed.
"""

import re
from typing import List, Dict, Any, Optional, Callable, Awaitable
import asyncio

from .config import CompactionConfig, COMPACTION_PREFIX, SUMMARY_TEMPLATE
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
        preserve_recent: int = 5,
        config: Optional[CompactionConfig] = None,
        llm_summarize_fn: Optional[Callable[[str], Awaitable[str]]] = None
    ):
        """
        Initialize the compactor.
        
        Args:
            max_tokens: Maximum tokens before compaction
            target_tokens: Target tokens after compaction
            strategy: Compaction strategy to use
            preserve_system: Keep system messages
            preserve_recent: Number of recent messages to preserve
<<<<<<< HEAD
            config: Optional CompactionConfig to override defaults
            llm_summarize_fn: Async function to call LLM for summarization
        """
        # Initialize config first
        self.config = config or CompactionConfig()
        
        # Use config values if config provided, otherwise use constructor args
        if config is not None:
            self.max_tokens = config.max_tokens
            self.target_tokens = config.target_tokens
            self.preserve_system = config.preserve_system
            self.preserve_recent = config.preserve_recent
        else:
            self.max_tokens = max_tokens
            self.target_tokens = target_tokens or int(max_tokens * 0.75)
            self.preserve_system = preserve_system
            self.preserve_recent = preserve_recent
            
        self.strategy = strategy
        self.llm_summarize_fn = llm_summarize_fn
        
        # Track previous summaries for iterative update
        self._previous_summary: Optional[str] = None
    
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
        Compact messages to fit within token limit (synchronous version).
        
        For LLM_SUMMARIZE strategy, falls back to naive summarization if no LLM function provided.
        Use compact_async for proper LLM integration.
        
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
            if self.llm_summarize_fn:
                # For sync calls with LLM function, we need to run async
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If in async context, fallback to naive summarization
                        compacted = self._summarize(messages)
                    else:
                        compacted = loop.run_until_complete(self._llm_summarize_async(messages))
                except Exception:
                    # Fallback to naive summarization if async fails
                    compacted = self._summarize(messages)
            else:
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

    async def compact_async(
        self,
        messages: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], CompactionResult]:
        """
        Compact messages to fit within token limit (asynchronous version).
        
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
            compacted = await self._llm_summarize_async(messages)
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
        Use LLM to summarize older messages with anti-injection framing.
        
        Note: This implementation uses structured templates and anti-injection prefixes
        to prevent the model from treating summarized content as active instructions.
        """
        result = []
        
        # Keep system messages (excluding previous compacted summaries)
        system_msgs = [
            m for m in messages 
            if m.get("role") == "system" and not m.get("_compacted")
        ]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:]
        older = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
        
        if older:
            if self.config.structured_template:
                structured = self._build_structured_summary(older)
            else:
                # Fallback to simple summary
                summary_parts = []
                for msg in older:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    if isinstance(content, str) and content:
                        summary_parts.append(f"[{role}]: {content[:150]}...")
                structured = "\n".join(summary_parts[:10])
            
            if structured:
                # Apply anti-injection prefix
                prefixed = f"{self.config.compaction_prefix}\n\n{structured}"
                
                # Handle iterative update if enabled
                if self.config.iterative_update and self._previous_summary:
                    structured = self._merge_summaries(self._previous_summary, structured)
                    prefixed = f"{self.config.compaction_prefix}\n\n{structured}"
                
                # Store for next iteration
                if self.config.iterative_update:
                    self._previous_summary = structured
                
                result.append({
                    "role": "system",
                    "content": prefixed,
                    "_compacted": True,
                    "_original_count": len(older),
                    "_anti_injection": True,
                })
        
        result.extend(recent)
        return result

    async def _llm_summarize_async(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Use LLM to intelligently summarize older messages.
        
        This method invokes the agent's LLM to create a meaningful summary
        that preserves key facts, identifiers, and the user's intent.
        """
        result = []
        
        # Keep system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:]
        older = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
        
        if older and self.llm_summarize_fn:
            try:
                # Format messages for summarization
                history_text = self._format_messages_for_summary(older)
                
                # Create summarization prompt that preserves important information
                prompt = (
                    "Summarise the following conversation history. Preserve verbatim: "
                    "all file paths, IDs, hashes, URLs, task references, error messages, "
                    "tool outputs, and the user's requests. Be concise but complete. "
                    "Focus on facts and actions taken, not general conversation.\n\n"
                    f"{history_text}"
                )
                
                # Call the LLM for summarization
                summary = await self.llm_summarize_fn(prompt)
                
                # Add the LLM-generated summary as a system message
                result.append({
                    "role": "system",
                    "content": f"[Previous conversation summary]\n{summary}",
                    "_compacted": True,
                    "_original_count": len(older),
                    "_llm_generated": True,
                })
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
                })
        
        result.extend(recent)
        return result

    def _format_messages_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages for LLM summarization."""
        formatted = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            # Handle tool calls
            if msg.get("tool_calls"):
                tool_calls = msg.get("tool_calls", [])
                tool_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
                formatted.append(f"{i+1}. {role}: Called tools: {', '.join(tool_names)}")
            
            # Handle content
            if isinstance(content, str) and content.strip():
                # Truncate very long content but preserve structure
                if len(content) > 1000:
                    content = content[:800] + "...[truncated]..." + content[-200:]
                formatted.append(f"{i+1}. {role}: {content}")
            elif isinstance(content, list):
                # Handle multi-part content
                parts = []
                for part in content[:3]:  # Limit to first 3 parts
                    if isinstance(part, dict):
                        text = part.get("text", "")
                        if text:
                            parts.append(text[:200] + "..." if len(text) > 200 else text)
                if parts:
                    formatted.append(f"{i+1}. {role}: {' | '.join(parts)}")
            
            # Handle tool results with IDs
            if msg.get("tool_call_id"):
                tool_id = msg.get("tool_call_id", "")
                formatted.append(f"{i+1}. {role} (tool {tool_id}): {str(content)[:500]}...")
        
        return "\n".join(formatted)
    
    def _build_structured_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Build a structured summary using the configured template.
        
        Args:
            messages: Messages to summarize
            
        Returns:
            Structured summary string
        """
        # Extract information from messages
        active_task = "No specific task identified"
        completed = []
        in_progress = []
        pending = []
        files = set()
        remaining = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if not isinstance(content, str):
                continue
                
            content_lower = content.lower()
            
            # Extract file paths
            file_matches = re.findall(r'[\w/\.\-]+\.[a-zA-Z]{1,4}', content)
            files.update(file_matches[:5])  # Limit to 5 files
            
            # Categorize content based on keywords and role
            content_snippet = content[:200] + ("..." if len(content) > 200 else "")
            
            if role == "user":
                if any(word in content_lower for word in ["please", "can you", "help"]) or re.search(r'\bdo\b', content_lower):
                    active_task = content_snippet
                elif "?" in content:
                    pending.append(content_snippet)
                    
            elif role == "assistant":
                if any(word in content_lower for word in ["completed", "done", "finished"]):
                    completed.append(content_snippet)
                elif any(word in content_lower for word in ["working", "processing", "analyzing"]):
                    in_progress.append(content_snippet)
                elif any(word in content_lower for word in ["will", "plan to", "next"]):
                    remaining.append(content_snippet)
                    
            elif role == "tool":
                # Tool results are generally completed actions
                tool_name = msg.get("name", "unknown")
                completed.append(f"Tool {tool_name}: {content_snippet}")
        
        # Format using template
        return SUMMARY_TEMPLATE.format(
            active_task=active_task,
            completed="\n".join(f"- {item}" for item in completed[:3]) or "None identified",
            in_progress="\n".join(f"- {item}" for item in in_progress[:3]) or "None identified",
            pending="\n".join(f"- {item}" for item in pending[:3]) or "None identified",
            files=", ".join(list(files)[:5]) or "None mentioned",
            remaining="\n".join(f"- {item}" for item in remaining[:3]) or "None identified"
        )
    
    def _merge_summaries(self, previous: str, current: str) -> str:
        """
        Merge previous summary with current one for iterative updates.
        
        Args:
            previous: Previous summary content
            current: Current summary content
            
        Returns:
            Merged summary
        """
        # Simple merge strategy: prioritize current but preserve unique info from previous
        if not previous:
            return current
            
        # Preserve context but avoid excessive growth
        MAX_PREVIOUS_LENGTH = 500
        if len(previous) > MAX_PREVIOUS_LENGTH:
            truncated_previous = previous[:MAX_PREVIOUS_LENGTH]
            return f"{current}\n\n[Previous context]: {truncated_previous}..."
        else:
            return f"{current}\n\n[Previous context]: {previous}"
    
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

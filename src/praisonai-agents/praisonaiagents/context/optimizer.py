"""
Context Optimizer for PraisonAI Agents.

Provides strategies for reducing context size when approaching limits.
"""

from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
from .models import ContextLedger, OptimizerStrategy, OptimizationResult
from .tokens import estimate_messages_tokens


class BaseOptimizer(ABC):
    """Base class for optimization strategies."""
    
    @abstractmethod
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: Optional[ContextLedger] = None,
    ) -> tuple:
        """
        Optimize messages to fit within target tokens.
        
        Args:
            messages: Messages to optimize
            target_tokens: Target token count
            ledger: Current token ledger
            
        Returns:
            Tuple of (optimized_messages, OptimizationResult)
        """
        pass


class TruncateOptimizer(BaseOptimizer):
    """Truncate oldest messages strategy."""
    
    def __init__(self, preserve_system: bool = True, preserve_recent: int = 5):
        self.preserve_system = preserve_system
        self.preserve_recent = preserve_recent
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: Optional[ContextLedger] = None,
    ) -> tuple:
        original_tokens = estimate_messages_tokens(messages)
        
        if original_tokens <= target_tokens:
            return messages, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=original_tokens,
                tokens_saved=0,
                strategy_used=OptimizerStrategy.TRUNCATE,
            )
        
        # Separate system and other messages
        system_msgs = []
        other_msgs = []
        
        for msg in messages:
            if self.preserve_system and msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:] if other_msgs else []
        
        result = system_msgs + recent
        
        # Continue removing until under target
        while estimate_messages_tokens(result) > target_tokens and len(result) > 1:
            for i, msg in enumerate(result):
                if msg.get("role") != "system":
                    result.pop(i)
                    break
        
        optimized_tokens = estimate_messages_tokens(result)
        
        return result, OptimizationResult(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=original_tokens - optimized_tokens,
            strategy_used=OptimizerStrategy.TRUNCATE,
            messages_removed=len(messages) - len(result),
        )


class SlidingWindowOptimizer(BaseOptimizer):
    """Keep a sliding window of recent messages."""
    
    def __init__(self, preserve_system: bool = True):
        self.preserve_system = preserve_system
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: Optional[ContextLedger] = None,
    ) -> tuple:
        original_tokens = estimate_messages_tokens(messages)
        
        if original_tokens <= target_tokens:
            return messages, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=original_tokens,
                tokens_saved=0,
                strategy_used=OptimizerStrategy.SLIDING_WINDOW,
            )
        
        result = []
        
        # Keep system messages
        for msg in messages:
            if self.preserve_system and msg.get("role") == "system":
                result.append(msg)
        
        # Add messages from end until target reached
        non_system = [m for m in messages if m.get("role") != "system"]
        
        for msg in reversed(non_system):
            test_result = result + [msg]
            if estimate_messages_tokens(test_result) <= target_tokens:
                result.insert(len([m for m in result if m.get("role") == "system"]), msg)
            else:
                break
        
        # Ensure order
        system_msgs = [m for m in result if m.get("role") == "system"]
        other_msgs = [m for m in result if m.get("role") != "system"]
        result = system_msgs + other_msgs
        
        optimized_tokens = estimate_messages_tokens(result)
        
        return result, OptimizationResult(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=original_tokens - optimized_tokens,
            strategy_used=OptimizerStrategy.SLIDING_WINDOW,
            messages_removed=len(messages) - len(result),
        )


class PruneToolsOptimizer(BaseOptimizer):
    """Prune old tool outputs while keeping tool calls."""
    
    def __init__(
        self,
        preserve_recent: int = 5,
        max_output_chars: int = 4000,  # Increased from 500 to allow full page content
        protected_tools: Optional[List[str]] = None,
        tool_limits: Optional[Dict[str, int]] = None,  # Per-tool limits
    ):
        self.preserve_recent = preserve_recent
        self.max_output_chars = max_output_chars
        self.protected_tools = protected_tools or []
        self.tool_limits = tool_limits or {}  # {tool_name: max_chars}
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: Optional[ContextLedger] = None,
    ) -> tuple:
        original_tokens = estimate_messages_tokens(messages)
        
        result = []
        pruned_count = 0
        
        # Separate system and other messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result.extend(system_msgs)
        
        # Keep recent messages intact
        recent = other_msgs[-self.preserve_recent:]
        older = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
        
        # Prune older tool outputs
        for msg in older:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Check if this is a tool result
            if role == "tool" or msg.get("tool_call_id"):
                # Check if protected
                tool_name = msg.get("name", "")
                if tool_name in self.protected_tools:
                    result.append(msg)
                    continue
                
                # Get per-tool limit or use default
                limit = self.tool_limits.get(tool_name, self.max_output_chars)
                
                # Truncate if too long (use smart format)
                if isinstance(content, str) and len(content) > limit:
                    pruned_msg = msg.copy()
                    tail_size = min(limit // 5, 500)
                    head = content[:limit - tail_size]
                    tail = content[-tail_size:] if tail_size > 0 else ""
                    pruned_msg["content"] = f"{head}\n...[{len(content):,} chars, showing first/last portions]...\n{tail}"
                    pruned_msg["_pruned"] = True
                    pruned_msg["_original_length"] = len(content)
                    result.append(pruned_msg)
                    pruned_count += 1
                else:
                    result.append(msg)
            else:
                result.append(msg)
        
        result.extend(recent)
        
        optimized_tokens = estimate_messages_tokens(result)
        
        return result, OptimizationResult(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=original_tokens - optimized_tokens,
            strategy_used=OptimizerStrategy.PRUNE_TOOLS,
            tool_outputs_pruned=pruned_count,
        )


class NonDestructiveOptimizer(BaseOptimizer):
    """
    Tag messages for exclusion without deleting them.
    
    Messages are tagged with _condense_parent and excluded from
    effective history, but can be restored on rewind.
    """
    
    def __init__(self, preserve_recent: int = 3):
        self.preserve_recent = preserve_recent
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: Optional[ContextLedger] = None,
    ) -> tuple:
        import uuid
        
        original_tokens = estimate_messages_tokens(messages)
        
        if original_tokens <= target_tokens:
            return messages, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=original_tokens,
                tokens_saved=0,
                strategy_used=OptimizerStrategy.NON_DESTRUCTIVE,
            )
        
        condense_id = str(uuid.uuid4())
        
        # Separate system and other messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        # Keep recent, tag older
        keep_start = max(0, len(other_msgs) - self.preserve_recent)
        
        result = []
        tagged_count = 0
        
        # Add system messages
        result.extend(system_msgs)
        
        # Tag older messages
        for i, msg in enumerate(other_msgs):
            if i < keep_start:
                tagged_msg = msg.copy()
                if "_condense_parent" not in tagged_msg:
                    tagged_msg["_condense_parent"] = condense_id
                    tagged_count += 1
                result.append(tagged_msg)
            else:
                result.append(msg)
        
        # Calculate effective tokens (excluding tagged)
        effective_msgs = [m for m in result if "_condense_parent" not in m]
        optimized_tokens = estimate_messages_tokens(effective_msgs)
        
        return result, OptimizationResult(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=original_tokens - optimized_tokens,
            strategy_used=OptimizerStrategy.NON_DESTRUCTIVE,
            messages_tagged=tagged_count,
        )


class SummarizeOptimizer(BaseOptimizer):
    """
    Summarize older messages using LLM or fallback to truncation.
    
    When an LLM summarize function is provided, uses it to create
    intelligent summaries. Otherwise falls back to truncation.
    """
    
    def __init__(
        self,
        preserve_recent: int = 5,
        max_summary_items: int = 10,
        llm_summarize_fn: Optional[callable] = None,
        max_summary_tokens: int = 500,
    ):
        """
        Initialize summarize optimizer.
        
        Args:
            preserve_recent: Number of recent messages to keep intact
            max_summary_items: Max items to include in fallback summary
            llm_summarize_fn: Optional function(messages) -> str for LLM summarization
            max_summary_tokens: Target token count for LLM summary
        """
        self.preserve_recent = preserve_recent
        self.max_summary_items = max_summary_items
        self.llm_summarize_fn = llm_summarize_fn
        self.max_summary_tokens = max_summary_tokens
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: Optional[ContextLedger] = None,
    ) -> tuple:
        original_tokens = estimate_messages_tokens(messages)
        
        if original_tokens <= target_tokens:
            return messages, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=original_tokens,
                tokens_saved=0,
                strategy_used=OptimizerStrategy.SUMMARIZE,
            )
        
        # Separate system and other messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        
        result = list(system_msgs)
        
        # Keep recent messages
        recent = other_msgs[-self.preserve_recent:]
        older = other_msgs[:-self.preserve_recent] if len(other_msgs) > self.preserve_recent else []
        
        if older:
            # Try LLM summarization first
            summary = self._create_summary(older)
            
            if summary:
                result.append({
                    "role": "system",
                    "content": summary,
                    "_summary": True,
                    "_original_count": len(older),
                    "_llm_summarized": self.llm_summarize_fn is not None,
                })
        
        result.extend(recent)
        
        optimized_tokens = estimate_messages_tokens(result)
        
        return result, OptimizationResult(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=original_tokens - optimized_tokens,
            strategy_used=OptimizerStrategy.SUMMARIZE,
            messages_removed=len(older),
            summary_added=bool(older),
        )
    
    def _create_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Create summary using LLM or fallback to truncation."""
        if self.llm_summarize_fn:
            try:
                # Use LLM to create intelligent summary
                return self.llm_summarize_fn(messages, self.max_summary_tokens)
            except Exception:
                # Fallback to truncation on error
                pass
        
        # Fallback: Create truncated summary
        summary_parts = []
        for msg in messages[:self.max_summary_items]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                summary_parts.append(f"[{role}]: {content[:150]}...")
        
        if summary_parts:
            return "[Previous conversation summary]\n" + "\n".join(summary_parts)
        return ""


class SummarizeToolOutputsOptimizer(BaseOptimizer):
    """
    Summarize large tool outputs using LLM before truncation.
    
    This optimizer specifically targets tool role messages with large content,
    using an LLM to create intelligent summaries that preserve key information.
    Falls back to keeping original content if LLM is unavailable or fails.
    """
    
    def __init__(
        self,
        llm_summarize_fn: Optional[callable] = None,
        max_output_tokens: int = 1000,
        min_chars_to_summarize: int = 2000,
        preserve_recent: int = 2,
        tool_summarize_limits: Optional[Dict[str, int]] = None,
    ):
        """
        Initialize tool output summarizer.
        
        Args:
            llm_summarize_fn: Function(content, max_tokens) -> summary string
            max_output_tokens: Target token count for summarized output
            min_chars_to_summarize: Default minimum chars before summarization triggers
            preserve_recent: Number of recent tool outputs to preserve intact
            tool_summarize_limits: Per-tool min_chars_to_summarize limits {tool_name: min_chars}
        """
        self.llm_summarize_fn = llm_summarize_fn
        self.max_output_tokens = max_output_tokens
        self.min_chars_to_summarize = min_chars_to_summarize
        self.preserve_recent = preserve_recent
        self.tool_summarize_limits = tool_summarize_limits or {}
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: Optional[ContextLedger] = None,
    ) -> tuple:
        original_tokens = estimate_messages_tokens(messages)
        
        # If already under budget or no LLM function, return as-is
        if original_tokens <= target_tokens or not self.llm_summarize_fn:
            return messages, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=original_tokens,
                tokens_saved=0,
                strategy_used=OptimizerStrategy.SMART,
            )
        
        result = []
        summarized_count = 0
        
        # Find tool messages and their indices
        tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
        
        # Preserve recent tool outputs (only if there are more than preserve_recent tools)
        if tool_indices and self.preserve_recent > 0 and len(tool_indices) > self.preserve_recent:
            recent_tool_indices = set(tool_indices[-self.preserve_recent:])
        else:
            recent_tool_indices = set()  # Summarize all if few tools or preserve_recent=0
        
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Only process tool messages with large content
            if role == "tool" and i not in recent_tool_indices:
                # Get per-tool limit or use default
                tool_name = msg.get("name", "")
                min_chars = self.tool_summarize_limits.get(tool_name, self.min_chars_to_summarize)
                if isinstance(content, str) and len(content) >= min_chars:
                    # Try to summarize
                    try:
                        summary = self.llm_summarize_fn(content, self.max_output_tokens)
                        if summary and len(summary) < len(content):
                            summarized_msg = msg.copy()
                            summarized_msg["content"] = summary
                            summarized_msg["_summarized"] = True
                            summarized_msg["_original_length"] = len(content)
                            result.append(summarized_msg)
                            summarized_count += 1
                            continue
                    except Exception:
                        # Fallback to original on error
                        pass
            
            result.append(msg)
        
        optimized_tokens = estimate_messages_tokens(result)
        
        tokens_saved = original_tokens - optimized_tokens
        
        return result, OptimizationResult(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=tokens_saved,
            strategy_used=OptimizerStrategy.SMART,
            tool_outputs_summarized=summarized_count,
            tokens_saved_by_summarization=tokens_saved,  # All savings from summarization
        )


class LLMSummarizeOptimizer(SummarizeOptimizer):
    """
    LLM-powered summarization optimizer.
    
    Uses the agent's LLM to create intelligent summaries of older messages,
    preserving key information while reducing token count.
    """
    
    def __init__(
        self,
        preserve_recent: int = 5,
        llm_client: Optional[Any] = None,
        model: str = "gpt-4o-mini",
        max_summary_tokens: int = 500,
    ):
        """
        Initialize LLM summarize optimizer.
        
        Args:
            preserve_recent: Number of recent messages to keep intact
            llm_client: OpenAI-compatible client for summarization
            model: Model to use for summarization
            max_summary_tokens: Target token count for summary
        """
        self.llm_client = llm_client
        self.model = model
        
        # Create LLM summarize function if client provided
        llm_fn = self._llm_summarize if llm_client else None
        
        super().__init__(
            preserve_recent=preserve_recent,
            llm_summarize_fn=llm_fn,
            max_summary_tokens=max_summary_tokens,
        )
    
    def _llm_summarize(self, messages: List[Dict[str, Any]], max_tokens: int) -> str:
        """Use LLM to create intelligent summary."""
        if not self.llm_client:
            return ""
        
        # Build content to summarize
        content_parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                # Truncate very long content for summarization input
                truncated = content[:2000] if len(content) > 2000 else content
                content_parts.append(f"[{role}]: {truncated}")
        
        if not content_parts:
            return ""
        
        # Create summarization prompt
        summarize_prompt = f"""Summarize the following conversation history concisely, preserving key facts, decisions, and context. Keep the summary under {max_tokens} tokens.

Conversation:
{chr(10).join(content_parts)}

Summary:"""
        
        try:
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": summarize_prompt}],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            summary = response.choices[0].message.content
            return f"[AI Summary of {len(messages)} previous messages]\n{summary}"
        except Exception:
            return ""


class SmartOptimizer(BaseOptimizer):
    """
    Smart optimization combining multiple strategies.
    
    Applies strategies in order:
    1. Summarize tool outputs (if LLM available and smart_tool_summarize=True)
    2. Prune tool outputs (fallback truncation)
    3. Sliding window
    4. Summarize conversation if still over
    """
    
    def __init__(
        self,
        preserve_recent: int = 5,
        protected_tools: Optional[List[str]] = None,
        tool_limits: Optional[Dict[str, int]] = None,
        llm_summarize_fn: Optional[callable] = None,
        smart_tool_summarize: bool = True,
        tool_summarize_limits: Optional[Dict[str, int]] = None,
    ):
        self.preserve_recent = preserve_recent
        self.protected_tools = protected_tools or []
        self.tool_limits = tool_limits or {}
        self.smart_tool_summarize = smart_tool_summarize
        self.tool_summarize_limits = tool_summarize_limits or {}
        
        # Tool output summarization (LLM-powered, applied first when available)
        self._summarize_tools = SummarizeToolOutputsOptimizer(
            llm_summarize_fn=llm_summarize_fn if smart_tool_summarize else None,
            preserve_recent=preserve_recent,
            tool_summarize_limits=tool_summarize_limits,
        )
        self._prune = PruneToolsOptimizer(
            preserve_recent=preserve_recent,
            protected_tools=protected_tools,
            tool_limits=tool_limits,
        )
        self._window = SlidingWindowOptimizer()
        self._summarize = SummarizeOptimizer(
            preserve_recent=preserve_recent,
            llm_summarize_fn=llm_summarize_fn,
        )
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: Optional[ContextLedger] = None,
    ) -> tuple:
        original_tokens = estimate_messages_tokens(messages)
        
        if original_tokens <= target_tokens:
            return messages, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=original_tokens,
                tokens_saved=0,
                strategy_used=OptimizerStrategy.SMART,
            )
        
        # Step 1: Summarize tool outputs (LLM-powered, if available)
        tool_summarized_count = 0
        tokens_saved_by_summarization = 0
        if self._summarize_tools.llm_summarize_fn:
            result, tool_summary_result = self._summarize_tools.optimize(messages, target_tokens, ledger)
            tool_summarized_count = tool_summary_result.tool_outputs_summarized
            tokens_saved_by_summarization = tool_summary_result.tokens_saved_by_summarization
            
            if estimate_messages_tokens(result) <= target_tokens:
                return result, OptimizationResult(
                    original_tokens=original_tokens,
                    optimized_tokens=tool_summary_result.optimized_tokens,
                    tokens_saved=original_tokens - tool_summary_result.optimized_tokens,
                    strategy_used=OptimizerStrategy.SMART,
                    tool_outputs_summarized=tool_summarized_count,
                    tokens_saved_by_summarization=tokens_saved_by_summarization,
                )
        else:
            result = messages
        
        # Step 2: Prune tool outputs (fallback truncation)
        result, prune_result = self._prune.optimize(result, target_tokens, ledger)
        tokens_saved_by_truncation = prune_result.tokens_saved
        
        if estimate_messages_tokens(result) <= target_tokens:
            return result, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=prune_result.optimized_tokens,
                tokens_saved=original_tokens - prune_result.optimized_tokens,
                strategy_used=OptimizerStrategy.SMART,
                tool_outputs_summarized=tool_summarized_count,
                tool_outputs_pruned=prune_result.tool_outputs_pruned,
                tokens_saved_by_summarization=tokens_saved_by_summarization,
                tokens_saved_by_truncation=tokens_saved_by_truncation,
            )
        
        # Step 3: Sliding window
        result, window_result = self._window.optimize(result, target_tokens, ledger)
        
        if estimate_messages_tokens(result) <= target_tokens:
            return result, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=window_result.optimized_tokens,
                tokens_saved=original_tokens - window_result.optimized_tokens,
                strategy_used=OptimizerStrategy.SMART,
                tool_outputs_pruned=prune_result.tool_outputs_pruned,
                messages_removed=window_result.messages_removed,
            )
        
        # Step 4: Summarize conversation
        result, summary_result = self._summarize.optimize(result, target_tokens, ledger)
        
        optimized_tokens = estimate_messages_tokens(result)
        
        return result, OptimizationResult(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=original_tokens - optimized_tokens,
            strategy_used=OptimizerStrategy.SMART,
            tool_outputs_summarized=tool_summarized_count,
            tool_outputs_pruned=prune_result.tool_outputs_pruned,
            tokens_saved_by_summarization=tokens_saved_by_summarization,
            tokens_saved_by_truncation=tokens_saved_by_truncation,
            messages_removed=window_result.messages_removed + summary_result.messages_removed,
            summary_added=summary_result.summary_added,
        )


# Strategy registry
OPTIMIZER_REGISTRY: Dict[OptimizerStrategy, type] = {
    OptimizerStrategy.TRUNCATE: TruncateOptimizer,
    OptimizerStrategy.SLIDING_WINDOW: SlidingWindowOptimizer,
    OptimizerStrategy.PRUNE_TOOLS: PruneToolsOptimizer,
    OptimizerStrategy.NON_DESTRUCTIVE: NonDestructiveOptimizer,
    OptimizerStrategy.SUMMARIZE: SummarizeOptimizer,
    OptimizerStrategy.SMART: SmartOptimizer,
}

# LLM summarizer available separately (not in registry as it needs client)
LLM_SUMMARIZE_OPTIMIZER = LLMSummarizeOptimizer


def get_optimizer(
    strategy: OptimizerStrategy,
    **kwargs
) -> BaseOptimizer:
    """
    Get an optimizer instance for a strategy.
    
    Args:
        strategy: Optimization strategy
        **kwargs: Strategy-specific arguments
        
    Returns:
        Optimizer instance
    """
    optimizer_class = OPTIMIZER_REGISTRY.get(strategy, SmartOptimizer)
    return optimizer_class(**kwargs)


def get_effective_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Get effective history excluding tagged messages.
    
    Filters out messages with _condense_parent tags.
    
    Args:
        messages: Full message history
        
    Returns:
        Effective messages for API calls
    """
    return [m for m in messages if "_condense_parent" not in m]

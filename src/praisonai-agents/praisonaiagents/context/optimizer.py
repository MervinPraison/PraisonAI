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
        max_output_chars: int = 500,
        protected_tools: Optional[List[str]] = None,
    ):
        self.preserve_recent = preserve_recent
        self.max_output_chars = max_output_chars
        self.protected_tools = protected_tools or []
    
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
                
                # Truncate if too long
                if isinstance(content, str) and len(content) > self.max_output_chars:
                    pruned_msg = msg.copy()
                    pruned_msg["content"] = content[:self.max_output_chars] + "\n...[output truncated]..."
                    pruned_msg["_pruned"] = True
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
    Summarize older messages using LLM.
    
    Note: This is a placeholder that creates a structured summary.
    Actual LLM summarization should be done at the agent level.
    """
    
    def __init__(self, preserve_recent: int = 5, max_summary_items: int = 10):
        self.preserve_recent = preserve_recent
        self.max_summary_items = max_summary_items
    
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
            # Create summary
            summary_parts = []
            for msg in older[:self.max_summary_items]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    summary_parts.append(f"[{role}]: {content[:150]}...")
            
            if summary_parts:
                summary = (
                    "[Previous conversation summary]\n"
                    + "\n".join(summary_parts)
                )
                result.append({
                    "role": "system",
                    "content": summary,
                    "_summary": True,
                    "_original_count": len(older),
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


class SmartOptimizer(BaseOptimizer):
    """
    Smart optimization combining multiple strategies.
    
    Applies strategies in order:
    1. Prune tool outputs
    2. Sliding window
    3. Summarize if still over
    """
    
    def __init__(
        self,
        preserve_recent: int = 5,
        protected_tools: Optional[List[str]] = None,
    ):
        self.preserve_recent = preserve_recent
        self.protected_tools = protected_tools or []
        
        self._prune = PruneToolsOptimizer(
            preserve_recent=preserve_recent,
            protected_tools=protected_tools,
        )
        self._window = SlidingWindowOptimizer()
        self._summarize = SummarizeOptimizer(preserve_recent=preserve_recent)
    
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
        
        # Step 1: Prune tool outputs
        result, prune_result = self._prune.optimize(messages, target_tokens, ledger)
        
        if estimate_messages_tokens(result) <= target_tokens:
            return result, OptimizationResult(
                original_tokens=original_tokens,
                optimized_tokens=prune_result.optimized_tokens,
                tokens_saved=original_tokens - prune_result.optimized_tokens,
                strategy_used=OptimizerStrategy.SMART,
                tool_outputs_pruned=prune_result.tool_outputs_pruned,
            )
        
        # Step 2: Sliding window
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
        
        # Step 3: Summarize
        result, summary_result = self._summarize.optimize(result, target_tokens, ledger)
        
        optimized_tokens = estimate_messages_tokens(result)
        
        return result, OptimizationResult(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=original_tokens - optimized_tokens,
            strategy_used=OptimizerStrategy.SMART,
            tool_outputs_pruned=prune_result.tool_outputs_pruned,
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

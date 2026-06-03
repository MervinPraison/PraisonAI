"""
Context compaction policy adapters for PraisonAI Agents.

As per AGENTS.md: Heavy implementations belong in adapters, not core protocols.
This module contains the concrete implementation of ContextCompactionPolicyProtocol.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union
from copy import deepcopy

from .protocols import (
    ContextCompactionPolicyProtocol,
    CompactionRoute,
    CompactionStrategy, 
    ContextBudgetResult
)


@dataclass
class ContextCompactionPolicyAdapter:
    """
    Adapter implementing ContextCompactionPolicyProtocol.
    
    Provides intelligent policy decisions for proactive context management,
    replacing reactive string-matching with proactive token budget analysis.
    """
    # When to trigger compaction (0.0-1.0 fraction of context window)
    trigger_at: float = 0.90
    
    # Compaction strategy
    strategy: Union[str, CompactionStrategy] = CompactionStrategy.DROP_OLDEST_TOOLS
    
    # Always preserve the most recent N conversation turns
    preserve_last_n_turns: int = 5
    
    # Maximum compaction attempts before giving up
    max_compaction_attempts: int = 2
    
    # Target utilization after compaction (0.0-1.0)
    target_utilization: float = 0.70
    
    # Whether to be aggressive about tool output truncation
    aggressive_tool_truncation: bool = True
    
    # Model-specific overrides
    model_overrides: Optional[Dict[str, Dict[str, Any]]] = None
    
    def __post_init__(self):
        """Validate configuration."""
        if not 0.1 <= self.trigger_at <= 0.99:
            raise ValueError("trigger_at must be between 0.1 and 0.99")
        if not 0.1 <= self.target_utilization <= 0.95:
            raise ValueError("target_utilization must be between 0.1 and 0.95")
        if self.trigger_at <= self.target_utilization:
            raise ValueError("trigger_at must be greater than target_utilization")
            
        # Convert string strategy to enum
        if isinstance(self.strategy, str):
            self.strategy = CompactionStrategy(self.strategy.lower())
    
    def compute_context_budget(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None
    ) -> ContextBudgetResult:
        """
        Compute context budget and determine route before LLM call.
        
        Replaces reactive error handling with proactive analysis.
        
        Args:
            messages: Current conversation history
            model: Model name for context window lookup
            tools: Tool schemas (if any)
            system_prompt: System prompt content
            
        Returns:
            ContextBudgetResult with routing decision
        """
        # Get model context window
        from .budgeter import ContextBudgeter, get_model_limit
        model_limit = get_model_limit(model)
        budgeter = ContextBudgeter(model=model, model_limit=model_limit)
        
        # Estimate current token usage
        from .tokens import estimate_messages_tokens
        current_tokens = estimate_messages_tokens(messages, use_accurate=False)
        
        # Add system prompt tokens if provided
        if system_prompt:
            from .tokens import estimate_tokens_heuristic
            current_tokens += estimate_tokens_heuristic(system_prompt)
        
        # Add tool schema tokens if provided
        if tools:
            from .tokens import estimate_tool_schema_tokens
            current_tokens += estimate_tool_schema_tokens(tools, use_accurate=False)
        
        # Calculate utilization
        available_tokens = budgeter.usable
        utilization = current_tokens / available_tokens if available_tokens > 0 else 1.0
        
        # Apply model-specific overrides
        effective_trigger = self.trigger_at
        effective_strategy = self.strategy
        
        if self.model_overrides and model in self.model_overrides:
            overrides = self.model_overrides[model]
            effective_trigger = overrides.get("trigger_at", self.trigger_at)
            effective_strategy = CompactionStrategy(
                overrides.get("strategy", self.strategy)
            )
        
        # Determine route
        needs_action = utilization >= effective_trigger
        
        if not needs_action:
            route = CompactionRoute.FITS
            recommended_strategy = effective_strategy
        else:
            # Decide on compaction strategy
            if utilization >= 0.95:
                # Critical - need aggressive action
                route = CompactionRoute.COMPACT_THEN_TRUNCATE
            elif self._has_large_tool_outputs(messages) and self.aggressive_tool_truncation:
                # Try truncating tool outputs first
                route = CompactionRoute.TRUNCATE_TOOLS
            else:
                # Standard compaction
                route = CompactionRoute.COMPACT_NEEDED
                
            recommended_strategy = effective_strategy
        
        return ContextBudgetResult(
            route=route,
            current_tokens=current_tokens,
            available_tokens=available_tokens,
            utilization=utilization,
            needs_action=needs_action,
            recommended_strategy=recommended_strategy,
            details={
                "model": model,
                "model_limit": model_limit,
                "effective_trigger": effective_trigger,
                "preserve_turns": self.preserve_last_n_turns,
                "max_attempts": self.max_compaction_attempts,
                "target_utilization": self.target_utilization,
            }
        )
    
    def _has_large_tool_outputs(self, messages: List[Dict[str, Any]]) -> bool:
        """Check if messages contain large tool outputs that could be truncated."""
        for msg in messages:
            if msg.get("role") == "tool" or msg.get("tool_call_id"):
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 1000:
                    return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert policy to dictionary for serialization."""
        return {
            "trigger_at": self.trigger_at,
            "strategy": self.strategy.value if isinstance(self.strategy, CompactionStrategy) else self.strategy,
            "preserve_last_n_turns": self.preserve_last_n_turns,
            "max_compaction_attempts": self.max_compaction_attempts,
            "target_utilization": self.target_utilization,
            "aggressive_tool_truncation": self.aggressive_tool_truncation,
            "model_overrides": self.model_overrides,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextCompactionPolicyAdapter":
        """Create policy from dictionary."""
        return cls(**data)


# Pre-defined policy presets
CONSERVATIVE_POLICY = ContextCompactionPolicyAdapter(
    trigger_at=0.80,
    strategy=CompactionStrategy.DROP_OLDEST_TOOLS,
    preserve_last_n_turns=8,
    target_utilization=0.60,
)

BALANCED_POLICY = ContextCompactionPolicyAdapter(
    trigger_at=0.90,
    strategy=CompactionStrategy.DROP_OLDEST_TOOLS,
    preserve_last_n_turns=5,
    target_utilization=0.70,
)

AGGRESSIVE_POLICY = ContextCompactionPolicyAdapter(
    trigger_at=0.95,
    strategy=CompactionStrategy.SUMMARISE,
    preserve_last_n_turns=3,
    target_utilization=0.75,
    aggressive_tool_truncation=True,
)


def get_default_policy_impl() -> ContextCompactionPolicyAdapter:
    """Get the default context compaction policy implementation."""
    return deepcopy(BALANCED_POLICY)
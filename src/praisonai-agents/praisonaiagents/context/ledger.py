"""
Context Ledger for PraisonAI Agents.

Tracks token usage across context segments with per-agent and per-session support.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from .models import ContextLedger, ContextSegment, BudgetAllocation
from .tokens import estimate_messages_tokens, estimate_tool_schema_tokens


@dataclass
class SegmentStats:
    """Statistics for a context segment."""
    tokens: int = 0
    count: int = 0  # Number of items (messages, tools, etc.)
    budget: int = 0
    
    @property
    def utilization(self) -> float:
        """Utilization as fraction of budget."""
        if self.budget == 0:
            return 0.0
        return self.tokens / self.budget
    
    @property
    def over_budget(self) -> bool:
        """Check if over budget."""
        return self.tokens > self.budget if self.budget > 0 else False


class ContextLedgerManager:
    """
    Manages context token accounting.
    
    Tracks tokens per segment and provides utilization metrics.
    Supports multi-agent scenarios with per-agent ledgers.
    
    Example:
        manager = ContextLedgerManager()
        manager.set_budget(budgeter.allocate())
        
        # Track segments
        manager.track_system_prompt(system_prompt)
        manager.track_history(messages)
        manager.track_tools(tool_schemas)
        
        # Get stats
        print(manager.get_utilization())
        print(manager.get_warnings())
    """
    
    def __init__(self, agent_id: Optional[str] = None):
        """
        Initialize ledger manager.
        
        Args:
            agent_id: Optional agent identifier for multi-agent tracking
        """
        self.agent_id = agent_id
        self._ledger = ContextLedger()
        self._budget: Optional[BudgetAllocation] = None
        self._segment_details: Dict[str, SegmentStats] = {}
        
        # Initialize segment stats
        for segment in ContextSegment:
            self._segment_details[segment.value] = SegmentStats()
    
    def set_budget(self, budget: BudgetAllocation) -> None:
        """Set the budget allocation."""
        self._budget = budget
        
        # Update segment budgets
        for segment in ContextSegment:
            self._segment_details[segment.value].budget = budget.get_segment_budget(segment)
    
    def reset(self) -> None:
        """Reset all token counts."""
        self._ledger = ContextLedger()
        for segment in ContextSegment:
            stats = self._segment_details[segment.value]
            stats.tokens = 0
            stats.count = 0
    
    def track_segment(
        self,
        segment: ContextSegment,
        tokens: int,
        count: int = 1
    ) -> None:
        """
        Track tokens for a segment.
        
        Args:
            segment: Context segment
            tokens: Token count
            count: Number of items
        """
        self._ledger.set_segment(segment, tokens)
        stats = self._segment_details[segment.value]
        stats.tokens = tokens
        stats.count = count
    
    def add_to_segment(
        self,
        segment: ContextSegment,
        tokens: int,
        count: int = 1
    ) -> None:
        """
        Add tokens to a segment.
        
        Args:
            segment: Context segment
            tokens: Tokens to add
            count: Items to add
        """
        self._ledger.add_segment(segment, tokens)
        stats = self._segment_details[segment.value]
        stats.tokens += tokens
        stats.count += count
    
    def track_system_prompt(self, content: str) -> int:
        """Track system prompt tokens."""
        from .tokens import estimate_tokens_heuristic
        tokens = estimate_tokens_heuristic(content)
        self.track_segment(ContextSegment.SYSTEM_PROMPT, tokens)
        return tokens
    
    def track_rules(self, content: str) -> int:
        """Track rules tokens."""
        from .tokens import estimate_tokens_heuristic
        tokens = estimate_tokens_heuristic(content)
        self.track_segment(ContextSegment.RULES, tokens)
        return tokens
    
    def track_skills(self, content: str) -> int:
        """Track skills tokens."""
        from .tokens import estimate_tokens_heuristic
        tokens = estimate_tokens_heuristic(content)
        self.track_segment(ContextSegment.SKILLS, tokens)
        return tokens
    
    def track_memory(self, content: str) -> int:
        """Track memory tokens."""
        from .tokens import estimate_tokens_heuristic
        tokens = estimate_tokens_heuristic(content)
        self.track_segment(ContextSegment.MEMORY, tokens)
        return tokens
    
    def track_history(self, messages: List[Dict[str, Any]]) -> int:
        """
        Track conversation history tokens.
        
        Args:
            messages: List of message dicts
            
        Returns:
            Total tokens
        """
        tokens = estimate_messages_tokens(messages)
        self.track_segment(ContextSegment.HISTORY, tokens, len(messages))
        self._ledger.message_count = len(messages)
        
        # Count turns (user messages)
        turns = sum(1 for m in messages if m.get("role") == "user")
        self._ledger.turn_count = turns
        
        return tokens
    
    def track_tools(self, tools: List[Dict[str, Any]]) -> int:
        """
        Track tool schema tokens.
        
        Args:
            tools: List of tool definitions
            
        Returns:
            Total tokens
        """
        tokens = estimate_tool_schema_tokens(tools)
        self.track_segment(ContextSegment.TOOLS_SCHEMA, tokens, len(tools))
        return tokens
    
    def track_tool_output(self, content: str) -> int:
        """
        Add a tool output to tracking.
        
        Args:
            content: Tool output content
            
        Returns:
            Tokens for this output
        """
        from .tokens import estimate_tokens_heuristic
        tokens = estimate_tokens_heuristic(content)
        self.add_to_segment(ContextSegment.TOOL_OUTPUTS, tokens)
        self._ledger.tool_call_count += 1
        return tokens
    
    def get_ledger(self) -> ContextLedger:
        """Get current ledger."""
        return self._ledger.copy()
    
    def get_total(self) -> int:
        """Get total tokens across all segments."""
        return self._ledger.total
    
    def get_utilization(self) -> float:
        """Get overall utilization as fraction of usable budget."""
        if self._budget is None:
            return 0.0
        usable = self._budget.usable
        if usable == 0:
            return 0.0
        return self._ledger.total / usable
    
    def get_segment_stats(self, segment: ContextSegment) -> SegmentStats:
        """Get stats for a segment."""
        return self._segment_details[segment.value]
    
    def get_all_stats(self) -> Dict[str, SegmentStats]:
        """Get stats for all segments."""
        return self._segment_details.copy()
    
    def get_warnings(self, threshold: float = 0.9) -> List[str]:
        """
        Get warnings for segments near or over budget.
        
        Args:
            threshold: Warning threshold (0.0-1.0)
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        for segment in ContextSegment:
            stats = self._segment_details[segment.value]
            if stats.budget > 0:
                if stats.over_budget:
                    warnings.append(
                        f"{segment.value}: OVER BUDGET ({stats.tokens:,} / {stats.budget:,} tokens)"
                    )
                elif stats.utilization >= threshold:
                    pct = int(stats.utilization * 100)
                    warnings.append(
                        f"{segment.value}: {pct}% of budget ({stats.tokens:,} / {stats.budget:,} tokens)"
                    )
        
        # Overall utilization warning
        if self._budget:
            overall_util = self.get_utilization()
            if overall_util >= threshold:
                pct = int(overall_util * 100)
                warnings.insert(0, f"Overall context: {pct}% of usable budget")
        
        return warnings
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "ledger": self._ledger.to_dict(),
            "total": self._ledger.total,
            "utilization": self.get_utilization(),
            "segments": {
                name: {
                    "tokens": stats.tokens,
                    "count": stats.count,
                    "budget": stats.budget,
                    "utilization": stats.utilization,
                }
                for name, stats in self._segment_details.items()
            },
            "warnings": self.get_warnings(),
        }


class MultiAgentLedger:
    """
    Manages ledgers for multiple agents.
    
    Provides per-agent tracking and combined views.
    """
    
    def __init__(self):
        """Initialize multi-agent ledger."""
        self._agents: Dict[str, ContextLedgerManager] = {}
        self._shared_tokens: int = 0  # Tokens shared across agents
    
    def get_agent_ledger(self, agent_id: str) -> ContextLedgerManager:
        """Get or create ledger for an agent."""
        if agent_id not in self._agents:
            self._agents[agent_id] = ContextLedgerManager(agent_id)
        return self._agents[agent_id]
    
    def set_shared_tokens(self, tokens: int) -> None:
        """Set tokens shared across agents (e.g., team memory)."""
        self._shared_tokens = tokens
    
    def get_combined_total(self) -> int:
        """Get total tokens across all agents plus shared."""
        total = self._shared_tokens
        for ledger in self._agents.values():
            total += ledger.get_total()
        return total
    
    def get_agent_ids(self) -> List[str]:
        """Get list of tracked agent IDs."""
        return list(self._agents.keys())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agents": {
                agent_id: ledger.to_dict()
                for agent_id, ledger in self._agents.items()
            },
            "shared_tokens": self._shared_tokens,
            "combined_total": self.get_combined_total(),
        }

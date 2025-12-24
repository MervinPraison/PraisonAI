"""
Thinking Budget for PraisonAI Agents.

Defines budget constraints for extended thinking.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class BudgetLevel(str, Enum):
    """Predefined budget levels."""
    MINIMAL = "minimal"      # 2000 tokens
    LOW = "low"              # 4000 tokens
    MEDIUM = "medium"        # 8000 tokens
    HIGH = "high"            # 16000 tokens
    MAXIMUM = "maximum"      # 32000 tokens


# Token allocations for each level
BUDGET_TOKENS = {
    BudgetLevel.MINIMAL: 2000,
    BudgetLevel.LOW: 4000,
    BudgetLevel.MEDIUM: 8000,
    BudgetLevel.HIGH: 16000,
    BudgetLevel.MAXIMUM: 32000,
}


@dataclass
class ThinkingBudget:
    """
    Budget constraints for extended thinking.
    
    Controls how much thinking/reasoning the LLM can do
    before producing a response.
    """
    max_tokens: int = 8000
    max_time_seconds: Optional[float] = None
    adaptive: bool = True
    level: Optional[BudgetLevel] = None
    
    # Adaptive settings
    min_tokens: int = 1000
    complexity_multiplier: float = 1.0
    
    def __post_init__(self):
        # If level is specified, use its token allocation
        if self.level:
            self.max_tokens = BUDGET_TOKENS.get(self.level, self.max_tokens)
    
    @classmethod
    def from_level(cls, level: BudgetLevel, **kwargs) -> "ThinkingBudget":
        """Create a budget from a predefined level."""
        return cls(
            max_tokens=BUDGET_TOKENS[level],
            level=level,
            **kwargs
        )
    
    @classmethod
    def minimal(cls) -> "ThinkingBudget":
        """Create a minimal budget."""
        return cls.from_level(BudgetLevel.MINIMAL)
    
    @classmethod
    def low(cls) -> "ThinkingBudget":
        """Create a low budget."""
        return cls.from_level(BudgetLevel.LOW)
    
    @classmethod
    def medium(cls) -> "ThinkingBudget":
        """Create a medium budget."""
        return cls.from_level(BudgetLevel.MEDIUM)
    
    @classmethod
    def high(cls) -> "ThinkingBudget":
        """Create a high budget."""
        return cls.from_level(BudgetLevel.HIGH)
    
    @classmethod
    def maximum(cls) -> "ThinkingBudget":
        """Create a maximum budget."""
        return cls.from_level(BudgetLevel.MAXIMUM)
    
    def get_tokens_for_complexity(self, complexity: float) -> int:
        """
        Get token budget based on task complexity.
        
        Args:
            complexity: Complexity score (0.0 to 1.0)
            
        Returns:
            Adjusted token budget
        """
        if not self.adaptive:
            return self.max_tokens
        
        # Scale between min and max based on complexity
        range_tokens = self.max_tokens - self.min_tokens
        adjusted = self.min_tokens + int(range_tokens * complexity * self.complexity_multiplier)
        
        return min(adjusted, self.max_tokens)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_tokens": self.max_tokens,
            "max_time_seconds": self.max_time_seconds,
            "adaptive": self.adaptive,
            "level": self.level.value if self.level else None,
            "min_tokens": self.min_tokens,
            "complexity_multiplier": self.complexity_multiplier
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThinkingBudget":
        """Create from dictionary."""
        level = None
        if data.get("level"):
            level = BudgetLevel(data["level"])
        
        return cls(
            max_tokens=data.get("max_tokens", 8000),
            max_time_seconds=data.get("max_time_seconds"),
            adaptive=data.get("adaptive", True),
            level=level,
            min_tokens=data.get("min_tokens", 1000),
            complexity_multiplier=data.get("complexity_multiplier", 1.0)
        )

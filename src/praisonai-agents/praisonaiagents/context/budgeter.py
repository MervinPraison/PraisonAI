"""
Context Budgeter for PraisonAI Agents.

Allocates token budgets across context segments based on model limits.
"""

from typing import Dict, Any, Optional
from .models import BudgetAllocation


# Model token limits (context window sizes)
MODEL_LIMITS: Dict[str, int] = {
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    # Anthropic
    "claude-3-5-sonnet": 200000,
    "claude-3-5-haiku": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    # Google
    "gemini-2.0-flash": 1048576,
    "gemini-1.5-pro": 2097152,
    "gemini-1.5-flash": 1048576,
    # Defaults
    "default": 128000,
}

# Default output reserves by model family
OUTPUT_RESERVES: Dict[str, int] = {
    "gpt-4o": 16384,
    "gpt-4o-mini": 16384,
    "gpt-4-turbo": 4096,
    "gpt-4": 4096,
    "gpt-3.5-turbo": 4096,
    "claude-3": 8192,
    "gemini": 8192,
    "default": 8000,
}


def get_model_limit(model: str) -> int:
    """
    Get context window limit for a model.
    
    Args:
        model: Model name or identifier
        
    Returns:
        Context window size in tokens
    """
    # Exact match
    if model in MODEL_LIMITS:
        return MODEL_LIMITS[model]
    
    # Partial match (e.g., "gpt-4o-2024-05-13" matches "gpt-4o")
    model_lower = model.lower()
    for key, limit in MODEL_LIMITS.items():
        if key in model_lower or model_lower.startswith(key):
            return limit
    
    return MODEL_LIMITS["default"]


def get_output_reserve(model: str) -> int:
    """
    Get recommended output token reserve for a model.
    
    Args:
        model: Model name
        
    Returns:
        Output reserve in tokens
    """
    model_lower = model.lower()
    
    for key, reserve in OUTPUT_RESERVES.items():
        if key in model_lower:
            return reserve
    
    return OUTPUT_RESERVES["default"]


class ContextBudgeter:
    """
    Allocates token budgets across context segments.
    
    Ensures context fits within model limits while reserving
    space for output generation.
    
    Example:
        budgeter = ContextBudgeter(model="gpt-4o")
        allocation = budgeter.allocate()
        print(f"History budget: {allocation.history_budget}")
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        model_limit: Optional[int] = None,
        output_reserve: Optional[int] = None,
        # Segment budget overrides (absolute tokens)
        system_prompt_budget: int = 2000,
        rules_budget: int = 500,
        skills_budget: int = 500,
        memory_budget: int = 1000,
        tools_schema_budget: int = 2000,
        tool_outputs_budget: int = 20000,
        buffer_budget: int = 1000,
        # Ratio-based allocation (if set, overrides fixed budgets)
        history_ratio: Optional[float] = None,
    ):
        """
        Initialize budgeter.
        
        Args:
            model: Model name for limit lookup
            model_limit: Override model limit
            output_reserve: Override output reserve
            system_prompt_budget: Budget for system prompt
            rules_budget: Budget for rules
            skills_budget: Budget for skills
            memory_budget: Budget for memory
            tools_schema_budget: Budget for tool schemas
            tool_outputs_budget: Budget for tool outputs
            buffer_budget: Safety buffer
            history_ratio: If set, allocate this ratio of usable for history
        """
        self.model = model
        self.model_limit = model_limit or get_model_limit(model)
        self.output_reserve = output_reserve or get_output_reserve(model)
        
        self.system_prompt_budget = system_prompt_budget
        self.rules_budget = rules_budget
        self.skills_budget = skills_budget
        self.memory_budget = memory_budget
        self.tools_schema_budget = tools_schema_budget
        self.tool_outputs_budget = tool_outputs_budget
        self.buffer_budget = buffer_budget
        self.history_ratio = history_ratio
    
    @property
    def usable(self) -> int:
        """Usable tokens after output reserve."""
        return self.model_limit - self.output_reserve
    
    def allocate(self) -> BudgetAllocation:
        """
        Create a budget allocation.
        
        Returns:
            BudgetAllocation with segment budgets
        """
        allocation = BudgetAllocation(
            model_limit=self.model_limit,
            output_reserve=self.output_reserve,
            system_prompt=self.system_prompt_budget,
            rules=self.rules_budget,
            skills=self.skills_budget,
            memory=self.memory_budget,
            tools_schema=self.tools_schema_budget,
            tool_outputs=self.tool_outputs_budget,
            buffer=self.buffer_budget,
            history=-1,  # Dynamic
        )
        
        # If history_ratio is set, compute history budget from ratio
        if self.history_ratio is not None:
            allocation.history = int(self.usable * self.history_ratio)
        
        return allocation
    
    def check_overflow(
        self,
        current_tokens: int,
        threshold: float = 0.8
    ) -> bool:
        """
        Check if current tokens exceed threshold.
        
        Args:
            current_tokens: Current total tokens
            threshold: Threshold as fraction of usable (0.0-1.0)
            
        Returns:
            True if overflow threshold exceeded
        """
        return current_tokens > (self.usable * threshold)
    
    def get_remaining(self, current_tokens: int) -> int:
        """
        Get remaining tokens before hitting usable limit.
        
        Args:
            current_tokens: Current total tokens
            
        Returns:
            Remaining tokens (can be negative if over limit)
        """
        return self.usable - current_tokens
    
    def get_utilization(self, current_tokens: int) -> float:
        """
        Get current utilization as fraction.
        
        Args:
            current_tokens: Current total tokens
            
        Returns:
            Utilization (0.0-1.0+)
        """
        if self.usable == 0:
            return 0.0
        return current_tokens / self.usable
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert budgeter state to dictionary."""
        return {
            "model": self.model,
            "model_limit": self.model_limit,
            "output_reserve": self.output_reserve,
            "usable": self.usable,
            "allocation": self.allocate().to_dict(),
        }

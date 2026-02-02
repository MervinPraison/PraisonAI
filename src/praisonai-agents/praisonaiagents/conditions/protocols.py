"""
Condition Protocol Definitions.

Provides Protocol interfaces that define the minimal contract for condition implementations.
This enables:
- Unified condition evaluation across AgentFlow and AgentTeam
- Custom condition implementations
- Type checking with static analyzers
- Mocking conditions in tests

These protocols are lightweight and have zero performance impact.
"""
from typing import Protocol, runtime_checkable, Dict, Any, List, Optional


@runtime_checkable
class ConditionProtocol(Protocol):
    """
    Minimal Protocol for condition implementations.
    
    This defines the essential interface that any condition must provide.
    It enables unified condition evaluation across AgentFlow (string-based)
    and AgentTeam (dict-based) systems.
    
    Example:
        ```python
        # Create a custom condition
        class ScoreCondition:
            def __init__(self, threshold: int):
                self.threshold = threshold
            
            def evaluate(self, context: Dict[str, Any]) -> bool:
                return context.get("score", 0) > self.threshold
        
        # Use in workflows
        cond: ConditionProtocol = ScoreCondition(80)
        result = cond.evaluate({"score": 90})  # True
        ```
    """
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Evaluate the condition against the given context.
        
        Args:
            context: Dictionary containing variables for evaluation.
                     May include workflow variables, previous outputs, etc.
            
        Returns:
            Boolean result of condition evaluation.
            Returns False on evaluation errors (fail-safe).
        """
        ...


@runtime_checkable
class RoutingConditionProtocol(ConditionProtocol, Protocol):
    """
    Extended Protocol for conditions that support routing to targets.
    
    This extends ConditionProtocol with the ability to return target
    tasks/steps based on the condition evaluation. Used primarily
    by AgentTeam for task routing.
    
    Example:
        ```python
        class ApprovalCondition:
            def __init__(self, routes: Dict[str, List[str]]):
                self.routes = routes
            
            def evaluate(self, context: Dict[str, Any]) -> bool:
                decision = context.get("decision", "")
                return decision in self.routes
            
            def get_target(self, context: Dict[str, Any]) -> List[str]:
                decision = context.get("decision", "")
                return self.routes.get(decision, [])
        ```
    """
    
    def get_target(self, context: Dict[str, Any]) -> List[str]:
        """
        Get the target tasks/steps based on condition evaluation.
        
        Args:
            context: Dictionary containing variables for evaluation.
            
        Returns:
            List of target task/step names to route to.
            Returns empty list if no match found.
        """
        ...

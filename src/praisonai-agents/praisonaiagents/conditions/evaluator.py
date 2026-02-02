"""
Condition Evaluator - Shared condition evaluation logic.

This module provides the shared condition evaluation logic used by both
AgentFlow (string-based conditions) and AgentTeam (dict-based routing).

The implementation is extracted from workflows.py _evaluate_condition()
to enable DRY condition handling across the codebase.
"""
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ExpressionCondition:
    """
    String-based condition evaluator for expressions like "{{score}} > 80".
    
    Supports:
        - Numeric comparison: "{{var}} > 80", "{{var}} >= 50", "{{var}} < 10"
        - String equality: "{{var}} == approved", "{{var}} != rejected"
        - Contains check: "error in {{message}}", "{{status}} contains success"
        - Boolean: "{{flag}}" (truthy check)
        - Nested property: "{{item.score}} >= 60"
    
    Example:
        ```python
        cond = ExpressionCondition("{{score}} > 80")
        result = cond.evaluate({"score": 90})  # True
        ```
    """
    
    def __init__(self, expression: str):
        """
        Initialize with a condition expression.
        
        Args:
            expression: Condition string with {{var}} placeholders.
        """
        self.expression = expression
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Evaluate the condition against the given context.
        
        Args:
            context: Dictionary containing variables for evaluation.
                     Special key 'previous_output' is also substituted.
            
        Returns:
            Boolean result of condition evaluation.
            Returns False on evaluation errors (fail-safe).
        """
        return evaluate_condition(
            self.expression,
            context,
            previous_output=context.get('previous_output')
        )
    
    def __repr__(self) -> str:
        return f"ExpressionCondition({self.expression!r})"


class DictCondition:
    """
    Dict-based condition evaluator for routing decisions.
    
    Used by AgentTeam for task routing based on decision keys.
    
    Example:
        ```python
        cond = DictCondition(
            {"approved": ["publish"], "rejected": ["revise"]},
            key="decision"
        )
        result = cond.evaluate({"decision": "approved"})  # True
        targets = cond.get_target({"decision": "approved"})  # ["publish"]
        ```
    """
    
    def __init__(self, routes: Dict[str, List[str]], key: str = "decision"):
        """
        Initialize with routing configuration.
        
        Args:
            routes: Dict mapping decision values to target task lists.
            key: Context key to read decision value from.
        """
        self.routes = routes
        self.key = key
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Check if the context contains a valid routing decision.
        
        Args:
            context: Dictionary containing the decision key.
            
        Returns:
            True if decision value matches a route key.
        """
        decision = context.get(self.key, "")
        if isinstance(decision, str):
            decision = decision.lower()
        return decision in self.routes
    
    def get_target(self, context: Dict[str, Any]) -> List[str]:
        """
        Get target tasks based on the decision value.
        
        Args:
            context: Dictionary containing the decision key.
            
        Returns:
            List of target task names, or empty list if no match.
        """
        decision = context.get(self.key, "")
        if isinstance(decision, str):
            decision = decision.lower()
        targets = self.routes.get(decision, [])
        if isinstance(targets, str):
            return [targets]
        return targets if targets else []
    
    def __repr__(self) -> str:
        return f"DictCondition(routes={self.routes!r}, key={self.key!r})"


def evaluate_condition(
    condition: str,
    variables: Dict[str, Any],
    previous_output: Optional[str] = None
) -> bool:
    """
    Evaluate a condition expression with variable substitution.
    
    This is the shared condition evaluation function used by both
    AgentFlow and AgentTeam. It supports various condition formats.
    
    Supported formats:
        - Numeric comparison: "{{var}} > 80", "{{var}} >= 50", "{{var}} < 10"
        - String equality: "{{var}} == approved", "{{var}} != rejected"
        - Contains check: "error in {{message}}", "{{status}} contains success"
        - Boolean: "{{flag}}" (truthy check)
        - Nested property: "{{item.score}} >= 60"
    
    Args:
        condition: Condition expression with {{var}} placeholders.
        variables: Dictionary containing variables for substitution.
        previous_output: Optional output from previous step (substitutes {{previous_output}}).
        
    Returns:
        Boolean result of condition evaluation.
        Returns False on evaluation errors (fail-safe).
    
    Example:
        ```python
        result = evaluate_condition("{{score}} > 80", {"score": 90})  # True
        result = evaluate_condition("{{status}} == approved", {"status": "approved"})  # True
        result = evaluate_condition("error in {{message}}", {"message": "An error occurred"})  # True
        ```
    """
    # Substitute variables in condition
    substituted = condition
    
    # Handle nested property access like {{item.score}}
    def get_nested_value(var_path: str, vars_dict: Dict[str, Any]) -> Any:
        parts = var_path.split('.')
        value = vars_dict
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value
    
    # First substitute {{previous_output}} if provided (before general variable substitution)
    if previous_output is not None:
        substituted = substituted.replace("{{previous_output}}", str(previous_output))
    
    # Find all {{var}} patterns and substitute
    pattern = r'\{\{([^}]+)\}\}'
    matches = re.findall(pattern, substituted)  # Use substituted, not condition
    
    for var_name in matches:
        # Skip previous_output as it's already handled
        if var_name == 'previous_output':
            continue
            
        if '.' in var_name:
            # Nested property access
            value = get_nested_value(var_name, variables)
        else:
            value = variables.get(var_name)
        
        if value is None:
            value = ""
        
        # Replace the placeholder with the value
        placeholder = f"{{{{{var_name}}}}}"
        if isinstance(value, (int, float)):
            substituted = substituted.replace(placeholder, str(value))
        elif isinstance(value, bool):
            substituted = substituted.replace(placeholder, str(value).lower())
        else:
            substituted = substituted.replace(placeholder, str(value))
    
    # Now evaluate the substituted condition
    try:
        # Handle different condition formats
        
        # Check if we have unsubstituted empty values in comparisons
        # If a variable was missing, it becomes empty string which can cause issues
        if ' > ' in substituted or ' < ' in substituted or ' >= ' in substituted or ' <= ' in substituted:
            # Check for empty left side in comparison (missing variable)
            if substituted.strip().startswith('>') or substituted.strip().startswith('<'):
                return False
            if substituted.strip().startswith('='):
                return False
        
        # Numeric comparisons: "90 > 80", "50 >= 50", "10 < 20", etc.
        numeric_pattern = r'^(-?\d+(?:\.\d+)?)\s*(>|>=|<|<=|==|!=)\s*(-?\d+(?:\.\d+)?)$'
        numeric_match = re.match(numeric_pattern, substituted.strip())
        if numeric_match:
            left = float(numeric_match.group(1))
            op = numeric_match.group(2)
            right = float(numeric_match.group(3))
            
            if op == '>':
                return left > right
            if op == '>=':
                return left >= right
            if op == '<':
                return left < right
            if op == '<=':
                return left <= right
            if op == '==':
                return left == right
            if op == '!=':
                return left != right
        
        # String equality: "approved == approved", "status != rejected"
        string_eq_pattern = r'^(.+?)\s*(==|!=)\s*(.+)$'
        string_match = re.match(string_eq_pattern, substituted.strip())
        if string_match:
            left = string_match.group(1).strip()
            op = string_match.group(2)
            right = string_match.group(3).strip()
            
            if op == '==':
                return left == right
            if op == '!=':
                return left != right
        
        # Contains check: "error in some message", "status contains success"
        if ' in ' in substituted:
            parts = substituted.split(' in ', 1)
            if len(parts) == 2:
                needle = parts[0].strip()
                haystack = parts[1].strip()
                return needle.lower() in haystack.lower()
        
        if ' contains ' in substituted:
            parts = substituted.split(' contains ', 1)
            if len(parts) == 2:
                haystack = parts[0].strip()
                needle = parts[1].strip()
                return needle.lower() in haystack.lower()
        
        # Boolean check: truthy evaluation
        # Handle "true", "false", "True", "False"
        if substituted.strip().lower() == 'true':
            return True
        if substituted.strip().lower() == 'false':
            return False
        
        # Non-empty string is truthy
        return bool(substituted.strip())
        
    except Exception as e:
        logger.warning(f"Condition evaluation failed for '{condition}': {e}")
        return False

"""
Guardrail chain implementation for composable validation.

This module provides concrete implementation of guardrail chaining,
separated from the protocol definitions for clean architecture.
"""
from typing import List, Dict, Any, Tuple
from .protocols import GuardrailProtocol


class GuardrailChain:
    """
    Composable chain of guardrails that can validate in sequence.
    
    Supports short-circuit evaluation (stops at first failure) and
    fail-closed behavior by default.
    
    Example:
        ```python
        chain = GuardrailChain([
            ProfanityFilter(),
            SchemaValidator(my_schema), 
            PermissionPolicy(allowed_tools)
        ])
        
        is_valid, result = chain.validate_input("Hello world")
        ```
    """
    
    def __init__(self, guardrails: List[GuardrailProtocol], fail_open: bool = False):
        """
        Initialize guardrail chain.
        
        Args:
            guardrails: List of guardrail implementations
            fail_open: If True, failures in guardrail execution allow through (unsafe)
                      If False, failures in guardrail execution block content (safe)
        """
        self.guardrails = guardrails
        self.fail_open = fail_open
        
    def __call__(self, task_output) -> Tuple[bool, Any]:
        """Validate an Agent/Task output through the chain's output guardrails.

        Makes ``GuardrailChain`` directly usable as ``Agent(guardrails=chain)``:
        the Agent's guardrail runner calls the guardrail with a single
        ``TaskOutput`` (or plain string) and expects a ``(success, result)``
        tuple. Takes exactly one positional parameter so it passes the Agent's
        guardrail signature validation. On success the original ``task_output``
        is passed through so the downstream pipeline keeps its object; on failure
        the error message is returned (fail-closed by default).
        """
        raw_text = task_output if isinstance(task_output, str) else getattr(task_output, "raw", str(task_output))
        is_valid, result = self.validate_output(raw_text)
        if is_valid:
            return True, task_output
        return False, result

    def validate_input(self, content: str, **kwargs) -> Tuple[bool, str]:
        """Validate input through all guardrails."""
        return self._validate_through_chain("validate_input", content, **kwargs)
        
    def validate_output(self, content: str, **kwargs) -> Tuple[bool, str]:
        """Validate output through all guardrails."""
        return self._validate_through_chain("validate_output", content, **kwargs)
        
    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any], **kwargs) -> Tuple[bool, Dict[str, Any]]:
        """Validate tool call through all guardrails."""
        for guardrail in self.guardrails:
            if hasattr(guardrail, 'validate_tool_call'):
                try:
                    is_valid, processed_args = guardrail.validate_tool_call(tool_name, arguments, **kwargs)
                    if not is_valid:
                        return False, arguments  # Failed validation
                    arguments = processed_args  # Update arguments with processing
                except Exception as e:
                    if not self.fail_open:
                        return False, arguments  # Fail closed on error
                        
        return True, arguments

    def validate_tool_result(self, tool_name: str, result: Any, **kwargs) -> Tuple[bool, Any]:
        """Validate a tool result through all guardrails (fail-closed)."""
        for guardrail in self.guardrails:
            if hasattr(guardrail, 'validate_tool_result'):
                try:
                    is_valid, processed_result = guardrail.validate_tool_result(tool_name, result, **kwargs)
                    if not is_valid:
                        return False, result  # Failed validation
                    result = processed_result  # Update result with processing (e.g. redaction)
                except Exception as e:
                    if not self.fail_open:
                        return False, result  # Fail closed on error

        return True, result

    def _validate_through_chain(self, method_name: str, content: str, **kwargs) -> Tuple[bool, str]:
        """Internal helper to validate content through the guardrail chain."""
        for guardrail in self.guardrails:
            if hasattr(guardrail, method_name):
                try:
                    method = getattr(guardrail, method_name)
                    is_valid, processed_content = method(content, **kwargs)
                    if not is_valid:
                        return False, processed_content  # Failed validation
                    content = processed_content  # Update content with processing
                except Exception as e:
                    if not self.fail_open:
                        return False, f"Guardrail error: {str(e)}"  # Fail closed on error
                        
        return True, content
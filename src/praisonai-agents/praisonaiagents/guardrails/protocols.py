"""
Guardrail Protocol Definitions.

Provides Protocol interfaces for composable safety and validation systems.
This enables custom guardrail implementations, deterministic validation,
and fail-safe error handling.
"""
from typing import Protocol, runtime_checkable, Optional, Any, Dict, Tuple


@runtime_checkable  
class GuardrailProtocol(Protocol):
    """
    Protocol for guardrail implementations that validate agent inputs/outputs.
    
    Guardrails can validate:
    - Input prompts (before processing)
    - Tool call arguments (before execution)  
    - Tool results (before they re-enter the LLM context)
    - Agent outputs (before returning to user)
    
    Example:
        ```python
        class ProfanityFilter:
            def validate_input(self, content: str, **kwargs) -> Tuple[bool, str]:
                if "badword" in content.lower():
                    return False, "Content contains inappropriate language"
                return True, content
                
            def validate_output(self, content: str, **kwargs) -> Tuple[bool, str]:
                return self.validate_input(content, **kwargs)
                
            def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any], **kwargs) -> Tuple[bool, Dict[str, Any]]:
                return True, arguments  # No tool validation for this filter
        ```
    """
    
    def validate_input(self, content: str, **kwargs) -> Tuple[bool, str]:
        """
        Validate input content before agent processes it.
        
        Args:
            content: The input text to validate
            **kwargs: Additional context (agent_name, user_id, etc.)
            
        Returns:
            Tuple of (is_valid: bool, processed_content: str)
            - If is_valid=False, processed_content should contain error message
            - If is_valid=True, processed_content can be modified content or original
        """
        ...
        
    def validate_output(self, content: str, **kwargs) -> Tuple[bool, str]:
        """
        Validate agent output before returning to user.
        
        Args:
            content: The output text to validate
            **kwargs: Additional context (agent_name, tool_used, etc.)
            
        Returns:
            Tuple of (is_valid: bool, processed_content: str)
        """
        ...
        
    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any], **kwargs) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate tool call before execution.
        
        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments to validate
            **kwargs: Additional context (agent_name, etc.)
            
        Returns:
            Tuple of (is_valid: bool, processed_arguments: Dict[str, Any])
        """
        ...

    def validate_tool_result(self, tool_name: str, result: Any, **kwargs) -> Tuple[bool, Any]:
        """
        Validate/redact a tool's result before it re-enters the LLM context.

        Runs after the tool executes and before its output is handed back to
        the model, trace, or downstream channel. Lets a guardrail inspect or
        rewrite raw tool output (e.g. redact a leaked secret, strip a
        prompt-injection payload) that ``validate_output`` never sees because
        it only ever receives the model's paraphrase.

        Args:
            tool_name: Name of the tool that produced the result
            result: The tool's raw result to validate
            **kwargs: Additional context (agent_name, etc.)

        Returns:
            Tuple of (is_valid: bool, processed_result: Any)
            - If is_valid=False, the result is rejected (fail-closed)
            - If is_valid=True, processed_result may be the original or a
              redacted/rewritten value
        """
        ...


@runtime_checkable
class StructuralGuardrailProtocol(Protocol):
    """
    Protocol for deterministic, schema-based validation.
    
    Unlike LLM-based guardrails, structural guardrails provide
    fast, deterministic validation using patterns, schemas, and rules.
    
    Example:
        ```python
        class SchemaValidator:
            def __init__(self, schema: Dict[str, Any]):
                self.schema = schema
                
            def validate_schema(self, data: Any) -> Tuple[bool, str]:
                # Use jsonschema or pydantic to validate
                try:
                    validate(data, self.schema)
                    return True, ""
                except ValidationError as e:
                    return False, str(e)
        ```
    """
    
    def validate_schema(self, data: Any, schema: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """
        Validate data against a JSON schema or similar structural rules.
        
        Args:
            data: The data to validate
            schema: Optional schema override
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        ...
        
    def validate_pattern(self, text: str, pattern: str) -> Tuple[bool, str]:
        """
        Validate text against a regex pattern or string pattern.
        
        Args:
            text: Text to validate
            pattern: Regex pattern or pattern identifier
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        ...


@runtime_checkable
class PolicyGuardrailProtocol(Protocol):
    """
    Protocol for policy-based guardrails that enforce business rules,
    permissions, and usage policies.
    
    Example:
        ```python
        class PermissionPolicy:
            def __init__(self, allowed_tools: Dict[str, List[str]]):
                self.allowed_tools = allowed_tools  # agent_name -> [tool_names]
                
            def check_permission(self, action: str, resource: str, context: Dict[str, Any]) -> Tuple[bool, str]:
                agent_name = context.get("agent_name", "")
                if action == "tool_call" and resource not in self.allowed_tools.get(agent_name, []):
                    return False, f"Agent {agent_name} not permitted to use tool {resource}"
                return True, ""
        ```
    """
    
    def check_permission(self, action: str, resource: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if an action is permitted based on policy rules.
        
        Args:
            action: The action being attempted (e.g., "tool_call", "output", "input")
            resource: The resource being accessed (e.g., tool name, output type)
            context: Additional context (agent_name, user_id, etc.)
            
        Returns:
            Tuple of (is_permitted: bool, denial_reason: str)
        """
        ...
        
    def check_rate_limit(self, resource: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if the rate limit has been exceeded for a resource.
        
        Args:
            resource: The resource being rate-limited
            context: Context for rate limiting (user_id, agent_name, etc.)
            
        Returns:
            Tuple of (within_limit: bool, error_message: str)
        """
        ...


# Method names that make an object a guardrail. An object exposing at least one
# of these is a protocol-conforming guardrail even though it is not ``callable``.
GUARDRAIL_PROTOCOL_METHODS = ("validate_input", "validate_output", "validate_tool_call", "validate_tool_result")


def is_guardrail_object(obj: Any) -> bool:
    """Return True when ``obj`` is a protocol-conforming guardrail *instance*.

    ``isinstance(obj, GuardrailProtocol)`` is not usable here: a ``runtime_checkable``
    Protocol only checks method presence and would also match unrelated objects
    partially, while classes (not instances) must be rejected. This helper is the
    single place that decides "is this thing a guardrail object?".

    Plain validator callables are handled by their own passthrough branch and are
    not required to match here (they will, however, if they also expose one of the
    protocol methods - e.g. ``GuardrailChain``).
    """
    if obj is None or isinstance(obj, type):
        return False
    return any(callable(getattr(obj, name, None)) for name in GUARDRAIL_PROTOCOL_METHODS)


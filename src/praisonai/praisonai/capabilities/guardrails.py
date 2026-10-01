"""
Guardrails Capabilities Module

Provides content guardrails and safety checks functionality.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List, Literal


@dataclass
class GuardrailResult:
    """Result from guardrail check."""
    passed: bool
    violations: Optional[List[Dict[str, Any]]] = None
    modified_content: Optional[str] = None
    original_content: Optional[str] = None
    guardrail_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _build_check_prompt(content: str, rules: Optional[List[str]]) -> str:
    """Build the guardrail check prompt for the given content and rules."""
    if rules:
        rules_text = "\n".join(f"- {rule}" for rule in rules)
    else:
        rules_text = """- No personally identifiable information (PII)
- No profanity or offensive language
- No harmful or dangerous content
- No misinformation"""

    return f"""You are a content guardrail. Check the following content against these rules:

{rules_text}

Content to check:
{content}

Respond with a JSON object:
{{"passed": true/false, "violations": ["list of violations if any"], "modified_content": "cleaned content if needed"}}

Only respond with the JSON, no other text."""


def _handle_guardrail_error(
    exc: Exception,
    content: str,
    guardrail_name: str,
    on_error: str,
    metadata: Optional[Dict[str, Any]],
) -> GuardrailResult:
    """Fail-closed error handler for guardrail checks.

    A rate-limit, timeout, invalid JSON, empty response or unexpected schema
    must NOT silently green-light content. By default (``on_error="block"``)
    the guardrail blocks; callers can opt into the old permissive behaviour
    with ``on_error="allow"`` or surface the error with ``on_error="raise"``.
    """
    if on_error == "raise":
        raise exc
    return GuardrailResult(
        passed=(on_error == "allow"),
        violations=[{"reason": "guardrail_unavailable", "error": str(exc)}],
        modified_content=None,
        original_content=content,
        guardrail_name=guardrail_name,
        metadata={"error": str(exc), "on_error": on_error, **(metadata or {})},
    )


def _parse_guardrail_response(
    response: Any,
    content: str,
    guardrail_name: str,
    on_error: str,
    metadata: Optional[Dict[str, Any]],
) -> GuardrailResult:
    """Validate and parse the LLM response into a GuardrailResult (fail-closed)."""
    import json

    if not response.choices or response.choices[0].message is None:
        return _handle_guardrail_error(
            ValueError("LLM returned empty or filtered response"),
            content, guardrail_name, on_error, metadata,
        )
    result_data = json.loads(response.choices[0].message.content)
    # Schema-check: the model MUST assert a decision explicitly; a missing or
    # non-bool ``passed`` is not a pass.
    if not isinstance(result_data, dict) or not isinstance(result_data.get("passed"), bool):
        return _handle_guardrail_error(
            ValueError(f"guardrail LLM returned unexpected schema: {result_data!r}"),
            content, guardrail_name, on_error, metadata,
        )
    return GuardrailResult(
        passed=result_data["passed"],
        violations=result_data.get("violations"),
        modified_content=result_data.get("modified_content"),
        original_content=content,
        guardrail_name=guardrail_name,
        metadata=metadata or {},
    )


def apply_guardrail(
    content: str,
    guardrail_name: str = "default",
    rules: Optional[List[str]] = None,
    model: str = "gpt-4o-mini",
    timeout: float = 60.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    on_error: Literal["block", "allow", "raise"] = "block",
    **kwargs
) -> GuardrailResult:
    """
    Apply a guardrail to content.
    
    Args:
        content: Content to check
        guardrail_name: Name of the guardrail
        rules: List of rules to apply
        model: Model to use for guardrail checking
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        on_error: What to do when the check itself fails (rate-limit, timeout,
            invalid JSON, unexpected schema). ``"block"`` (default) fails closed
            and marks the content as not passed; ``"allow"`` restores the old
            permissive behaviour; ``"raise"`` re-raises the underlying error.
        
    Returns:
        GuardrailResult with check results
        
    Example:
        >>> result = apply_guardrail("Some content", rules=["no_pii", "no_profanity"])
        >>> print(result.passed)
    """
    import litellm

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": _build_check_prompt(content, rules)}],
            timeout=timeout,
            api_key=api_key,
            api_base=api_base,
            response_format={"type": "json_object"},
            **kwargs
        )
        return _parse_guardrail_response(
            response, content, guardrail_name, on_error, metadata
        )
    except Exception as e:
        return _handle_guardrail_error(e, content, guardrail_name, on_error, metadata)


async def aapply_guardrail(
    content: str,
    guardrail_name: str = "default",
    rules: Optional[List[str]] = None,
    model: str = "gpt-4o-mini",
    timeout: float = 60.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    on_error: Literal["block", "allow", "raise"] = "block",
    **kwargs
) -> GuardrailResult:
    """
    Async: Apply a guardrail to content.
    
    See apply_guardrail() for full documentation, including ``on_error``.
    """
    import litellm

    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": _build_check_prompt(content, rules)}],
            timeout=timeout,
            api_key=api_key,
            api_base=api_base,
            response_format={"type": "json_object"},
            **kwargs
        )
        return _parse_guardrail_response(
            response, content, guardrail_name, on_error, metadata
        )
    except Exception as e:
        return _handle_guardrail_error(e, content, guardrail_name, on_error, metadata)

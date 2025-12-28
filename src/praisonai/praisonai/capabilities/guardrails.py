"""
Guardrails Capabilities Module

Provides content guardrails and safety checks functionality.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class GuardrailResult:
    """Result from guardrail check."""
    passed: bool
    violations: Optional[List[Dict[str, Any]]] = None
    modified_content: Optional[str] = None
    original_content: Optional[str] = None
    guardrail_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def apply_guardrail(
    content: str,
    guardrail_name: str = "default",
    rules: Optional[List[str]] = None,
    model: str = "gpt-4o-mini",
    timeout: float = 60.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
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
        
    Returns:
        GuardrailResult with check results
        
    Example:
        >>> result = apply_guardrail("Some content", rules=["no_pii", "no_profanity"])
        >>> print(result.passed)
    """
    import litellm
    
    # Build guardrail prompt
    rules_text = ""
    if rules:
        rules_text = "\n".join(f"- {rule}" for rule in rules)
    else:
        rules_text = """- No personally identifiable information (PII)
- No profanity or offensive language
- No harmful or dangerous content
- No misinformation"""
    
    check_prompt = f"""You are a content guardrail. Check the following content against these rules:

{rules_text}

Content to check:
{content}

Respond with a JSON object:
{{"passed": true/false, "violations": ["list of violations if any"], "modified_content": "cleaned content if needed"}}

Only respond with the JSON, no other text."""

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": check_prompt}],
            timeout=timeout,
            api_key=api_key,
            api_base=api_base,
            response_format={"type": "json_object"},
            **kwargs
        )
        
        import json
        result_text = response.choices[0].message.content
        result_data = json.loads(result_text)
        
        return GuardrailResult(
            passed=result_data.get("passed", True),
            violations=result_data.get("violations"),
            modified_content=result_data.get("modified_content"),
            original_content=content,
            guardrail_name=guardrail_name,
            metadata=metadata or {},
        )
    except Exception as e:
        # On error, fail safe (pass through)
        return GuardrailResult(
            passed=True,
            violations=None,
            modified_content=None,
            original_content=content,
            guardrail_name=guardrail_name,
            metadata={"error": str(e), **(metadata or {})},
        )


async def aapply_guardrail(
    content: str,
    guardrail_name: str = "default",
    rules: Optional[List[str]] = None,
    model: str = "gpt-4o-mini",
    timeout: float = 60.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> GuardrailResult:
    """
    Async: Apply a guardrail to content.
    
    See apply_guardrail() for full documentation.
    """
    import litellm
    
    rules_text = ""
    if rules:
        rules_text = "\n".join(f"- {rule}" for rule in rules)
    else:
        rules_text = """- No personally identifiable information (PII)
- No profanity or offensive language
- No harmful or dangerous content
- No misinformation"""
    
    check_prompt = f"""You are a content guardrail. Check the following content against these rules:

{rules_text}

Content to check:
{content}

Respond with a JSON object:
{{"passed": true/false, "violations": ["list of violations if any"], "modified_content": "cleaned content if needed"}}

Only respond with the JSON, no other text."""

    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": check_prompt}],
            timeout=timeout,
            api_key=api_key,
            api_base=api_base,
            response_format={"type": "json_object"},
            **kwargs
        )
        
        import json
        result_text = response.choices[0].message.content
        result_data = json.loads(result_text)
        
        return GuardrailResult(
            passed=result_data.get("passed", True),
            violations=result_data.get("violations"),
            modified_content=result_data.get("modified_content"),
            original_content=content,
            guardrail_name=guardrail_name,
            metadata=metadata or {},
        )
    except Exception as e:
        return GuardrailResult(
            passed=True,
            violations=None,
            modified_content=None,
            original_content=content,
            guardrail_name=guardrail_name,
            metadata={"error": str(e), **(metadata or {})},
        )

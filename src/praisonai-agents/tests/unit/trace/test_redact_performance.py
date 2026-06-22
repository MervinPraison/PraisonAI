"""Test to verify redaction optimizations work correctly."""

from praisonaiagents.trace.redact import (
    _REDACT_KV_PATTERN,
    _REDACT_PATTERN,
    _should_redact,
    redact_string,
)

def test_should_redact_uses_compiled_regex():
    """Verify _should_redact uses the compiled regex pattern."""
    # Test exact match
    assert _should_redact("api_key") == True
    assert _should_redact("password") == True
    
    # Test normalized match
    assert _should_redact("API-KEY") == True
    assert _should_redact("API KEY") == True
    
    # Test substring match via regex
    assert _should_redact("my_api_key_field") == True
    assert _should_redact("user_password") == True
    
    # Test non-sensitive
    assert _should_redact("username") == False
    assert _should_redact("email") == False
    print("✓ _should_redact works correctly with compiled regex")

def test_redact_string_uses_compiled_pattern():
    """Verify redact_string uses pre-compiled pattern."""
    # Test various formats
    test_cases = [
        ('api_key=sk-12345', 'api_key=[REDACTED]'),
        ('password: secret123', 'password: [REDACTED]'),
        ('{"token": "bearer-xyz"}', '{"token": "[REDACTED]"}'),
        ('API_KEY="mysecret"', 'API_KEY="[REDACTED]"'),
    ]
    
    for input_str, expected in test_cases:
        result = redact_string(input_str)
        assert result == expected, f"Failed: {input_str} -> {result} (expected {expected})"
    
    print("✓ redact_string works correctly with pre-compiled pattern")

def test_patterns_are_compiled():
    """Verify patterns are compiled at module level."""
    import re
    
    # Check that patterns are compiled regex objects
    assert isinstance(_REDACT_PATTERN, re.Pattern)
    assert isinstance(_REDACT_KV_PATTERN, re.Pattern)
    
    # Verify _REDACT_PATTERN does not have IGNORECASE flag
    # (since we normalize to lowercase before using it)
    assert (_REDACT_PATTERN.flags & re.IGNORECASE) == 0
    
    # Verify _REDACT_KV_PATTERN has IGNORECASE flag 
    # (since it works on raw text)
    assert (_REDACT_KV_PATTERN.flags & re.IGNORECASE) != 0
    
    print("✓ Patterns are properly compiled at module level")

if __name__ == "__main__":
    test_should_redact_uses_compiled_regex()
    test_redact_string_uses_compiled_pattern()
    test_patterns_are_compiled()
    print("\n✅ All tests passed!")
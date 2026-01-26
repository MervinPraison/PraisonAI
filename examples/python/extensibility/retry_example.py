"""Example: Retry Policies and Fallback Chains

This example demonstrates how to configure retry behavior with
exponential backoff, jitter, and fallback chains.
"""
from praisonaiagents.tools import (
    RetryPolicy,
    FallbackChain,
    ToolExecutionConfig,
)


def example_retry_policy():
    """Demonstrate RetryPolicy configuration and usage."""
    print("=" * 50)
    print("RetryPolicy Examples")
    print("=" * 50)
    
    # 1. Default policy
    print("\n1. Default RetryPolicy:")
    policy = RetryPolicy()
    print(f"   max_attempts: {policy.max_attempts}")
    print(f"   backoff_factor: {policy.backoff_factor}")
    print(f"   initial_delay_ms: {policy.initial_delay_ms}")
    print(f"   max_delay_ms: {policy.max_delay_ms}")
    print(f"   retry_on: {policy.retry_on}")
    
    # 2. Exponential backoff calculation
    print("\n2. Exponential Backoff (no jitter):")
    policy = RetryPolicy(
        initial_delay_ms=1000,
        backoff_factor=2.0,
        max_delay_ms=30000,
        jitter=False
    )
    for attempt in range(5):
        delay = policy.get_delay_ms(attempt)
        print(f"   Attempt {attempt}: delay = {delay}ms")
    
    # 3. With jitter for production
    print("\n3. With Jitter (production-ready):")
    policy = RetryPolicy(
        initial_delay_ms=1000,
        backoff_factor=2.0,
        jitter=True,
        jitter_factor=0.25  # ±25%
    )
    print("   Delays for attempt 0 (10 samples):")
    delays = [policy.get_delay_ms(0) for _ in range(10)]
    print(f"   {delays}")
    print(f"   Range: {min(delays)} - {max(delays)} (expected: 750-1250)")
    
    # 4. should_retry logic
    print("\n4. should_retry Logic:")
    policy = RetryPolicy(max_attempts=3, retry_on={"timeout", "rate_limit"})
    
    test_cases = [
        ("timeout", 0),
        ("timeout", 2),
        ("timeout", 3),  # At max_attempts
        ("unknown_error", 0),  # Not in retry_on
    ]
    for error_type, attempt in test_cases:
        result = policy.should_retry(error_type, attempt)
        print(f"   should_retry('{error_type}', {attempt}) = {result}")
    
    # 5. Custom error types
    print("\n5. Custom Error Types:")
    policy = RetryPolicy(retry_on={"api_error", "network_error", "throttled"})
    print(f"   Retries on: {policy.retry_on}")
    print(f"   should_retry('api_error', 0) = {policy.should_retry('api_error', 0)}")
    print(f"   should_retry('timeout', 0) = {policy.should_retry('timeout', 0)}")


def example_fallback_chain():
    """Demonstrate FallbackChain configuration."""
    print("\n" + "=" * 50)
    print("FallbackChain Examples")
    print("=" * 50)
    
    # 1. Basic chain
    print("\n1. Basic FallbackChain:")
    chain = FallbackChain(
        tools=["web_search", "cached_search", "default_response"]
    )
    print(f"   Tools: {chain.tools}")
    print(f"   Length: {len(chain)}")
    print(f"   stop_on_success: {chain.stop_on_success}")
    
    # 2. Iteration
    print("\n2. Iterating over chain:")
    for i, tool in enumerate(chain):
        print(f"   {i+1}. {tool}")
    
    # 3. Try all (don't stop on success)
    print("\n3. Try All Mode:")
    chain = FallbackChain(
        tools=["validator_1", "validator_2", "validator_3"],
        stop_on_success=False
    )
    print(f"   stop_on_success: {chain.stop_on_success}")
    print("   (All tools will be tried regardless of success)")


def example_tool_execution_config():
    """Demonstrate ToolExecutionConfig combining retry and fallback."""
    print("\n" + "=" * 50)
    print("ToolExecutionConfig Examples")
    print("=" * 50)
    
    # 1. Default config
    print("\n1. Default Config:")
    config = ToolExecutionConfig()
    print(f"   retry_policy: {config.retry_policy}")
    print(f"   fallback_chain: {config.fallback_chain}")
    print(f"   timeout_ms: {config.timeout_ms}")
    
    # 2. Using default() factory
    print("\n2. Default Factory:")
    config = ToolExecutionConfig.default()
    print(f"   retry_policy.max_attempts: {config.retry_policy.max_attempts}")
    
    # 3. Full configuration
    print("\n3. Full Configuration:")
    config = ToolExecutionConfig(
        retry_policy=RetryPolicy(
            max_attempts=5,
            backoff_factor=1.5,
            initial_delay_ms=500,
            jitter=True
        ),
        fallback_chain=FallbackChain(
            tools=["primary_api", "backup_api", "cache"]
        ),
        timeout_ms=10000
    )
    print(f"   retry_policy.max_attempts: {config.retry_policy.max_attempts}")
    print(f"   retry_policy.jitter: {config.retry_policy.jitter}")
    print(f"   fallback_chain tools: {config.fallback_chain.tools}")
    print(f"   timeout_ms: {config.timeout_ms}")


def example_validation():
    """Demonstrate validation of RetryPolicy parameters."""
    print("\n" + "=" * 50)
    print("Validation Examples")
    print("=" * 50)
    
    invalid_configs = [
        ("max_attempts=0", {"max_attempts": 0}),
        ("backoff_factor=0.5", {"backoff_factor": 0.5}),
        ("initial_delay_ms=-1", {"initial_delay_ms": -1}),
        ("max_delay < initial", {"initial_delay_ms": 1000, "max_delay_ms": 500}),
        ("jitter_factor=1.5", {"jitter_factor": 1.5}),
    ]
    
    for name, kwargs in invalid_configs:
        try:
            RetryPolicy(**kwargs)
            print(f"\n   {name}: No error (unexpected!)")
        except ValueError as e:
            print(f"\n   {name}:")
            print(f"   → ValueError: {e}")


if __name__ == "__main__":
    example_retry_policy()
    example_fallback_chain()
    example_tool_execution_config()
    example_validation()
    
    print("\n" + "=" * 50)
    print("All examples completed!")
    print("=" * 50)

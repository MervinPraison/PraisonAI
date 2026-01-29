"""
Model Failover Example - Automatic Provider Switching

This example demonstrates how to configure model failover
for reliability and cost optimization.
"""

import os
from praisonaiagents import (
    AuthProfile,
    FailoverConfig,
    FailoverManager,
)

# Create auth profiles for different providers
openai_profile = AuthProfile(
    name="openai-primary",
    provider="openai",
    api_key=os.environ.get("OPENAI_API_KEY", "sk-..."),
    priority=1,  # Highest priority
    rate_limit=100,
)

anthropic_profile = AuthProfile(
    name="anthropic-backup",
    provider="anthropic",
    api_key=os.environ.get("ANTHROPIC_API_KEY", "sk-ant-..."),
    priority=2,  # Second priority
    rate_limit=50,
)

groq_profile = AuthProfile(
    name="groq-fallback",
    provider="groq",
    api_key=os.environ.get("GROQ_API_KEY", "gsk-..."),
    priority=3,  # Third priority (fast but limited)
    rate_limit=30,
)

# Configure failover behavior
failover_config = FailoverConfig(
    max_retries=3,
    retry_delay=1.0,
    exponential_backoff=True,
    max_retry_delay=60.0,
    failover_on_rate_limit=True,
    failover_on_timeout=True,
    failover_on_error=True,
)

# Create failover manager
manager = FailoverManager(failover_config)
manager.add_profile(openai_profile)
manager.add_profile(anthropic_profile)
manager.add_profile(groq_profile)

def demonstrate_failover():
    """Demonstrate failover functionality."""
    
    print("Failover Manager Status:")
    print()
    
    # Get current status
    status = manager.status()
    for name, info in status.items():
        print(f"  {name}:")
        print(f"    Status: {info.get('status', 'unknown')}")
        print(f"    Priority: {info.get('priority', 'N/A')}")
        print(f"    Failures: {info.get('failure_count', 0)}")
    print()
    
    # Get next available profile
    next_profile = manager.get_next_profile()
    if next_profile:
        print(f"Next profile to use: {next_profile.name}")
        print(f"  Provider: {next_profile.provider}")
        print(f"  Priority: {next_profile.priority}")
    print()
    
    # Simulate marking a failure
    print("Simulating failure on primary provider...")
    manager.mark_failure("openai-primary", "Rate limit exceeded")
    
    # Get next profile after failure
    next_profile = manager.get_next_profile()
    if next_profile:
        print(f"After failure, next profile: {next_profile.name}")
    print()
    
    # Get retry delay
    delay = manager.get_retry_delay("openai-primary")
    print(f"Retry delay for openai-primary: {delay}s")
    print()
    
    # Reset all providers
    print("Resetting all providers...")
    manager.reset_all()
    
    next_profile = manager.get_next_profile()
    if next_profile:
        print(f"After reset, next profile: {next_profile.name}")

def cost_optimization_example():
    """Example of cost-optimized failover."""
    
    print("\nCost Optimization Example:")
    print("-" * 40)
    
    # Create cost-optimized manager
    cost_manager = FailoverManager()
    
    # Cheaper model first
    cost_manager.add_profile(AuthProfile(
        name="gpt-4o-mini",
        provider="openai",
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        priority=1,
        metadata={"model": "gpt-4o-mini", "cost_per_1k": 0.00015}
    ))
    
    # Premium model as fallback
    cost_manager.add_profile(AuthProfile(
        name="gpt-4o",
        provider="openai",
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        priority=2,
        metadata={"model": "gpt-4o", "cost_per_1k": 0.005}
    ))
    
    # Most expensive as last resort
    cost_manager.add_profile(AuthProfile(
        name="claude-opus",
        provider="anthropic",
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        priority=3,
        metadata={"model": "claude-3-opus", "cost_per_1k": 0.015}
    ))
    
    print("Cost-optimized failover chain:")
    for profile in [
        cost_manager.get_profile("gpt-4o-mini"),
        cost_manager.get_profile("gpt-4o"),
        cost_manager.get_profile("claude-opus"),
    ]:
        if profile:
            cost = profile.metadata.get("cost_per_1k", "N/A")
            print(f"  {profile.priority}. {profile.name} (${cost}/1K tokens)")

if __name__ == "__main__":
    print("Model Failover Configuration")
    print("=" * 40)
    print()
    
    print("Failover Config:")
    print(f"  Max retries: {failover_config.max_retries}")
    print(f"  Initial delay: {failover_config.retry_delay}s")
    print(f"  Exponential backoff: {failover_config.exponential_backoff}")
    print(f"  Max delay: {failover_config.max_retry_delay}s")
    print()
    
    print("Auth Profiles:")
    for profile in [openai_profile, anthropic_profile, groq_profile]:
        print(f"  {profile.name}:")
        print(f"    Provider: {profile.provider}")
        print(f"    Priority: {profile.priority}")
        print(f"    Rate limit: {profile.rate_limit} req/min")
    print()
    
    demonstrate_failover()
    cost_optimization_example()

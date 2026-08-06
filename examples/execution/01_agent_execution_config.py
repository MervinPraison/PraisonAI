"""
ExecutionConfig Example

Demonstrates using ExecutionConfig for fine-grained control over execution limits.
"""
import os
from praisonaiagents import Agent, ExecutionConfig

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

# Custom execution configuration
agent = Agent(
    instructions="You are a helpful assistant.",
    execution=ExecutionConfig(
        max_iter=30,
        max_rpm=100,
        max_execution_time=60,
        max_retry_limit=3,
    ),
)

# Rate-limited agent for API quota management
agent_rate_limited = Agent(
    instructions="You are a helpful assistant.",
    execution=ExecutionConfig(
        max_iter=20,
        max_rpm=10,  # Only 10 requests per minute
    ),
)

if __name__ == "__main__":
    print("Testing ExecutionConfig...")
    
    print(f"Custom agent max_iter: {agent.max_iter}")
    print(f"Custom agent max_rpm: {agent.max_rpm}")
    print(f"Custom agent max_execution_time: {agent.max_execution_time}")
    print(f"Custom agent max_retry_limit: {agent.max_retry_limit}")

    # max_rpm auto-creates a live RateLimiter (not just a stored number)
    assert agent_rate_limited.max_rpm == 10
    assert agent_rate_limited._rate_limiter is not None
    assert agent_rate_limited._rate_limiter.requests_per_minute == 10
    print(f"Rate-limited agent limiter: {agent_rate_limited._rate_limiter}")
    
    # Test custom agent
    print("\n--- Custom Execution ---")
    result = agent.chat("What is machine learning?")
    print(f"Result: {result}")
    
    print("\nExecutionConfig tests passed!")

"""
Rate Limiter Example - PraisonAI Agents

Demonstrates token bucket rate limiting for LLM API calls.
"""

from praisonaiagents import Agent
from praisonaiagents.llm import RateLimiter

# Create rate limiter: 60 requests per minute
limiter = RateLimiter(requests_per_minute=60, burst=5)

# Create agent with rate limiter
agent = Agent(
    name="RateLimitedBot",
    instructions="You are a helpful assistant.",
    rate_limiter=limiter
)

if __name__ == "__main__":
    print(f"Rate limiter: {limiter}")
    print(f"Available tokens: {limiter.available_tokens}")
    
    # Demonstrate rate limiting
    for i in range(3):
        limiter.acquire()
        print(f"Request {i+1} acquired, tokens left: {limiter.available_tokens:.1f}")
    
    print("\n✓ Rate limiter example complete")

"""
Redis State Store - Agent-First Example

Use Redis for state management with an Agent.

Docker Setup:
    docker run -d --name praison-redis -p 6379:6379 redis:7

Run:
    python state_redis.py

Expected Output:
    Agent responds with state persisted to Redis
"""

from praisonaiagents import Agent, db

print("=== Redis State Store (Agent-First) ===")

# Agent-first approach: use db parameter with Redis state store
my_db = db(
    database_url="sqlite:///conversations.db",  # Conversations
    state_url="redis://localhost:6379"          # State/tracing
)

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
    db=my_db,
    session_id="redis-state-example"
)

# Chat - state is automatically managed via Redis
response = agent.chat("Hello! Remember my favorite color is blue.")
print(f"Response: {response}")

# Second message to test state
response2 = agent.chat("What is my favorite color?")
print(f"Response: {response2}")

my_db.close()
print("\n=== Demo Complete ===")

# --- Advanced: Direct Store Usage ---
# from praisonai.persistence.factory import create_state_store
# store = create_state_store("redis", url="redis://localhost:6379")

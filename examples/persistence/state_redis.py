"""
Redis State Store Example for PraisonAI.

Demonstrates set/get/delete + TTL operations.

Requirements:
    pip install "praisonai[tools]"

Docker Setup:
    docker run -d --name praison-redis -p 6379:6379 redis:7

Run:
    python state_redis.py

Expected Output:
    === Redis State Store Demo ===
    Set key: session:user123:preferences
    Get value: {'theme': 'dark', 'language': 'en'}
    TTL remaining: 3600 seconds
    Hash operations: {'name': 'Alice', 'role': 'admin'}
"""

from praisonai.persistence.factory import create_state_store

# Create Redis state store
store = create_state_store("redis", url="redis://localhost:6379")

print("=== Redis State Store Demo ===")

# Basic set/get
key = "session:user123:preferences"
value = {"theme": "dark", "language": "en", "notifications": True}

store.set(key, value)
print(f"Set key: {key}")

retrieved = store.get(key)
print(f"Get value: {retrieved}")

# Set with TTL (expires in 1 hour)
ttl_key = "session:user123:token"
store.set(ttl_key, "abc123xyz", ttl=3600)
remaining = store.ttl(ttl_key)
print(f"TTL remaining: {remaining} seconds")

# Hash operations (for structured data)
hash_key = "user:123:profile"
store.hset(hash_key, "name", "Alice")
store.hset(hash_key, "role", "admin")
store.hset(hash_key, "last_login", "2024-12-24")

profile = store.hgetall(hash_key)
print(f"Hash operations: {profile}")

# Check existence
exists = store.exists(key)
print(f"Key exists: {exists}")

# Delete keys
store.delete(key)
store.delete(ttl_key)
store.delete(hash_key)
print("Cleaned up test keys")

store.close()

print("\n=== Demo Complete ===")

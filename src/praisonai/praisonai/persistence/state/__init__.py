"""
StateStore implementations for fast key-value state and caching.

Supported backends:
- Redis (redis)
- DynamoDB (dynamodb)
- Firestore (firestore)
- MongoDB (mongodb)
- Upstash (upstash)
- In-memory / JSON file (memory)
"""

__all__ = [
    "StateStore",
]

def __getattr__(name: str):
    if name == "StateStore":
        from .base import StateStore
        return StateStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

from mem0 import Memory
import os
import json

# Basic configuration
config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "praison",
            "path": ".praison",
        }
    }
}

# Initialize memory
memory = Memory.from_config(config)

# Search Alice's hobbies
search_results = memory.search(
    query="KAG",
    user_id="user1",
    limit=5
)

print(search_results)
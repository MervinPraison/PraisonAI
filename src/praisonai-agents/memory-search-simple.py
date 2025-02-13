from mem0 import Memory
import os
import json

# Basic configuration
config = {
    "version": "v1.1",
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "praison",
            "path": os.path.abspath("./.praison/storage")
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small"
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gpt-4o-mini"
        }
    }
}

# Initialize memory
memory = Memory.from_config(config)

# Search Alice's hobbies
search_results = memory.search(
    query="What are Alice's hobbies?",
    user_id="alice",
    limit=5
)

# Print results in a readable format
print("\nAlice's Memories:")
for memory in search_results['results']:
    print(f"\nMemory: {memory['memory']}")
    print(f"Score: {memory['score']}")
    if 'metadata' in memory:
        print("Metadata:")
        print(json.dumps(memory['metadata'], indent=2))
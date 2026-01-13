from mem0 import Memory
import logging
import json
import os
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MemorySearcher:
    def __init__(self):
        """Initialize Mem0 Memory searcher with configuration"""
        # Define the configuration
        config = {
            "version": "v1.1",
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "praison",
                    "path": os.path.abspath("./.praison/storage"),
                    "host": None,
                    "port": None
                }
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "embedding_dims": 1536
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "temperature": 0,
                    "max_tokens": 1000
                }
            }
        }
        
        # Initialize memory
        self.memory = Memory.from_config(config)
        logger.info("Memory searcher initialized")

    def pretty_print(self, data: Any) -> None:
        """Helper function to print data in a readable format"""
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2))
        else:
            print(data)

    def get_all_memories(self, user_id: Optional[str] = None) -> Dict:
        """Retrieve all memories for a user"""
        try:
            logger.info(f"Retrieving all memories for user {user_id}")
            memories = self.memory.get_all(user_id=user_id)
            count = len(memories.get('results', []))
            logger.info(f"Retrieved {count} memories")
            return memories
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {str(e)}")
            raise

    def search_memories(self, query: str, user_id: Optional[str] = None, limit: int = 5) -> Dict:
        """Search memories with a query"""
        try:
            logger.info(f"Searching memories with query: {query}")
            results = self.memory.search(
                query=query,
                user_id=user_id,
                limit=limit
            )
            count = len(results.get('results', []))
            logger.info(f"Found {count} matching memories")
            return results
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            raise

    def list_unique_users(self) -> list:
        """List all unique users in the memory store"""
        try:
            all_memories = self.memory.get_all()
            users = set()
            for memory in all_memories.get('results', []):
                if 'user_id' in memory:
                    users.add(memory['user_id'])
            return sorted(list(users))
        except Exception as e:
            logger.error(f"Failed to list users: {str(e)}")
            raise

def main():
    try:
        # Initialize memory searcher
        searcher = MemorySearcher()
        
        # Get list of users
        print("\n1. Available users in the memory store:")
        users = searcher.list_unique_users()
        searcher.pretty_print(users)
        
        if not users:
            print("No users found in the memory store. Please add some memories first.")
            return
            
        # Example user (using first user found)
        example_user = users[0]
        
        print(f"\n2. All memories for user '{example_user}':")
        all_memories = searcher.get_all_memories(user_id=example_user)
        searcher.pretty_print(all_memories)
        
        print(f"\n3. Searching memories for user '{example_user}':")
        search_results = searcher.search_memories(
            query="What are their hobbies?",
            user_id=example_user,
            limit=5
        )
        searcher.pretty_print(search_results)
        
        # Print summary
        print("\nMemory Store Summary:")
        total_memories = len(all_memories.get('results', []))
        print(f"Total memories for {example_user}: {total_memories}")
        if total_memories > 0:
            print("Available memories:")
            for mem in all_memories['results']:
                print(f"- {mem.get('memory', 'No content')}")
                if 'metadata' in mem:
                    print(f"  Metadata: {mem['metadata']}")

    except Exception as e:
        logger.error(f"Main process failed: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
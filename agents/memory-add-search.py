from mem0 import Memory
import logging
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self):
        """Initialize Mem0 Memory manager with configuration"""
        # Define the complete configuration with only supported fields
        config = {
            "version": "v1.1",
            "custom_prompt": None,
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
        
        # Ensure storage directory exists
        storage_path = os.path.abspath("./.praison/storage")
        if os.path.exists(storage_path):
            logger.info(f"Clearing existing storage at {storage_path}")
            import shutil
            shutil.rmtree(storage_path)
        os.makedirs(storage_path, exist_ok=True)
        logger.info(f"Created storage path: {storage_path}")
        
        # Initialize memory
        self.memory = Memory.from_config(config)
        logger.info("Memory manager initialized")

    def pretty_print(self, data: Any) -> None:
        """Helper function to print memory data in a readable format"""
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2))
        else:
            print(data)
            
    def extract_memory_id(self, result: Any) -> Optional[str]:
        """Extract memory ID from the result, handling different formats"""
        try:
            if isinstance(result, dict):
                # v1.1 format
                memories = result.get('results', [])
                return memories[0]['id'] if memories else None
            elif isinstance(result, list):
                # v1.0 format
                return result[0]['id'] if result else None
            return None
        except (KeyError, IndexError) as e:
            logger.warning(f"Could not extract memory ID from result: {e}")
            return None

    def prepare_metadata(self, metadata: Optional[Dict]) -> Dict:
        """Prepare metadata by converting values to acceptable types"""
        if not metadata:
            return {}
            
        clean_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                clean_metadata[key] = value
            elif isinstance(value, list):
                clean_metadata[key] = ','.join(map(str, value))
            elif isinstance(value, dict):
                clean_metadata[key] = json.dumps(value)
            else:
                clean_metadata[key] = str(value)
        return clean_metadata

    def verify_memory_addition(self, user_id: str, max_retries: int = 3) -> bool:
        """Verify that memory was added successfully"""
        for attempt in range(max_retries):
            try:
                time.sleep(0.5)  # Brief pause to allow indexing
                memories = self.memory.get_all(user_id=user_id)
                if len(memories.get('results', [])) > 0:
                    return True
                logger.warning(f"Memory not found on attempt {attempt + 1}")
            except Exception as e:
                logger.warning(f"Verification attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
        return False

    def add_memory(self, text: str, user_id: Optional[str] = None, metadata: Optional[Dict] = None) -> Dict:
        """Add a new memory with error handling and verification"""
        try:
            logger.info(f"Adding memory for user {user_id}")
            clean_metadata = self.prepare_metadata(metadata)
            logger.debug(f"Prepared metadata: {clean_metadata}")
            
            messages = [{"role": "user", "content": text}]
            result = self.memory.add(
                messages=messages,
                user_id=user_id,
                metadata=clean_metadata
            )
            
            if self.verify_memory_addition(user_id):
                logger.info("Memory added and verified successfully")
            else:
                logger.warning("Memory addition could not be verified")
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to add memory: {str(e)}")
            raise

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

def main():
    try:
        # Initialize memory manager
        manager = MemoryManager()
        
        # Add a test memory
        print("\n1. Adding a new memory:")
        metadata = {
            "category": "hobbies",
            "timestamp": datetime.now().isoformat(),
            "tags": "tennis,learning",
            "priority": 1,
            "source": "user_input"
        }
        
        result = manager.add_memory(
            text="I am working on improving my tennis skills. Suggest some online courses.",
            user_id="alice",
            metadata=metadata
        )
        manager.pretty_print(result)
        
        # Wait briefly for indexing
        time.sleep(1)
        
        print("\n2. Retrieving all memories:")
        all_memories = manager.get_all_memories(user_id="alice")
        manager.pretty_print(all_memories)
        
        print("\n3. Searching memories:")
        search_results = manager.search_memories(
            query="What are Alice's hobbies?",
            user_id="alice",
            limit=5
        )
        manager.pretty_print(search_results)
        
        # Print summary
        print("\nMemory Store Summary:")
        total_memories = len(all_memories.get('results', []))
        print(f"Total memories stored: {total_memories}")
        if total_memories > 0:
            print("Available memories:")
            for mem in all_memories['results']:
                print(f"- {mem.get('memory', 'No content')}")

    except Exception as e:
        logger.error(f"Main process failed: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
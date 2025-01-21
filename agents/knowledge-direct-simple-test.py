import logging
from praisonaiagents.knowledge import Knowledge
import os
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

config = {
    "version": "v1.1",
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "praison",
            "path": os.path.abspath("./.praison"),
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

knowledge = Knowledge(config)

# Search for memories based on a query
query = "KAG"
logger.info(f"Searching for memories with query: {query}")
search_results = knowledge.search(query, user_id="user1")
logger.info(f"Search results: {search_results}")
print(f"\nSearch results for '{query}':")
print(search_results)

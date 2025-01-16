import os
import logging
import uuid
import time

logger = logging.getLogger(__name__)

class Knowledge:
    def __init__(self, config=None):
        try:
            from mem0 import Memory
            from markitdown import MarkItDown
            import chromadb
        except ImportError:
            raise ImportError(
                "Required packages not installed. Please install using: "
                'pip install "praisonaiagents[knowledge]"'
            )

        os.environ['ANONYMIZED_TELEMETRY'] = 'False' # Chromadb
        
        # Generate unique collection name for each instance
        collection_name = f"test_{int(time.time())}_{str(uuid.uuid4())[:8]}"

        # Create persistent client config
        persist_dir = ".praison"
        base_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": collection_name,
                    "path": persist_dir,
                    "client": chromadb.PersistentClient(path=persist_dir)  # Use PersistentClient
                }
            },
            "version": "v1.1"
        }

        # If config is provided, merge it with base config
        if config:
            if "vector_store" in config and "config" in config["vector_store"]:
                # Don't override collection name and client
                config_copy = config["vector_store"]["config"].copy()
                for key in ["collection_name", "client"]:
                    if key in config_copy:
                        del config_copy[key]
                base_config["vector_store"]["config"].update(config_copy)

        self.config = base_config

        try:
            self.memory = Memory.from_config(self.config)
            self.markdown = MarkItDown()
        except (NotImplementedError, ValueError) as e:
            if "list_collections" in str(e) or "Extra fields not allowed" in str(e):
                # Keep only allowed fields
                vector_store_config = {
                    "collection_name": self.config["vector_store"]["config"]["collection_name"],
                    "path": self.config["vector_store"]["config"]["path"]
                }
                self.config["vector_store"]["config"] = vector_store_config
                self.memory = Memory.from_config(self.config)
                self.markdown = MarkItDown()
            else:
                raise

    def store(self, content, user_id=None, agent_id=None, run_id=None, metadata=None):
        """Store a memory."""
        try:
            # Process content to match expected format
            if isinstance(content, str):
                content = content.strip()
                if not content:
                    return []
                
            result = self.memory.add(content, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata)
            logger.info(f"Store operation result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error storing content: {str(e)}")
            return []

    def get_all(self, user_id=None, agent_id=None, run_id=None):
        """Retrieve all memories."""
        return self.memory.get_all(user_id=user_id, agent_id=agent_id, run_id=run_id)

    def get(self, memory_id):
        """Retrieve a specific memory by ID."""
        return self.memory.get(memory_id)

    def search(self, query, user_id=None, agent_id=None, run_id=None):
        """Search for memories related to a query."""
        return self.memory.search(query, user_id=user_id, agent_id=agent_id, run_id=run_id)

    def update(self, memory_id, data):
        """Update a memory."""
        return self.memory.update(memory_id, data)

    def history(self, memory_id):
        """Get the history of changes for a memory."""
        return self.memory.history(memory_id)

    def delete(self, memory_id):
        """Delete a memory."""
        self.memory.delete(memory_id)

    def delete_all(self, user_id=None, agent_id=None, run_id=None):
        """Delete all memories."""
        self.memory.delete_all(user_id=user_id, agent_id=agent_id, run_id=run_id)

    def reset(self):
        """Reset all memories."""
        self.memory.reset()

    def normalize_content(self, content):
        """Normalize content for consistent storage."""
        # Example normalization: strip whitespace, convert to lowercase
        return content.strip().lower()

    def add(self, file_path, user_id=None, agent_id=None, run_id=None, metadata=None):
        """Read file content and store it in memory."""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
            
        file_ext = os.path.splitext(file_path)[1].lower()
        logger.info(f"Processing file: {file_path} with extension: {file_ext}")
        
        try:
            # Determine how to read the file based on its extension
            if file_ext in ['.md', '.txt']:
                logger.info("Reading text file directly...")
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read().strip()
                logger.info(f"Raw text content: {content}")
                if not content:
                    raise ValueError("Empty text file")
                
                # Treat text file content as a single memory block
                content = self.normalize_content(content)
                memories = [content]
                logger.info(f"Normalized text content: {content}")
            
            else:
                # For other files, use MarkItDown or another appropriate method
                logger.info("Using MarkItDown for conversion...")
                result = self.markdown.convert(file_path)
                content = result.text_content
                content = self.normalize_content(content)
                memories = [content] if content else []
                logger.info(f"Normalized content: {content}")
                
            if not memories:
                logger.error("No content extracted from file")
                raise ValueError("No content could be extracted from file")
                
            if not metadata:
                metadata = {}
            metadata['file_type'] = file_ext.lstrip('.')
            metadata['filename'] = os.path.basename(file_path)
            logger.info(f"Processing with metadata: {metadata}")
            
            all_results = []
            for memory in memories:
                logger.info(f"Processing memory segment: {memory}")
                # Try direct storage first
                memory_result = self.store(memory, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata)
                logger.info(f"Store result for segment: {memory_result}")
                
                if memory_result:
                    logger.info(f"Successfully stored new memory: {memory_result}")
                    all_results.extend(memory_result)
                    continue  # Skip to next memory if storage successful

                # If storage failed, try to find existing memory
                logger.info("Direct storage failed, checking for existing memory...")
                existing_memories = self.memory.get_all(user_id=user_id, agent_id=agent_id, run_id=run_id)
                if existing_memories:
                    found = False
                    for existing in existing_memories:
                        if existing.get('memory') == memory:
                            logger.info(f"Found existing memory match: {existing}")
                            all_results.append({
                                'id': existing['id'], 
                                'memory': memory, 
                                'event': 'EXISTING',
                                'metadata': metadata
                            })
                            found = True
                            break
                    if not found:
                        logger.info("No existing memory found, forcing new storage")
                        # Force new storage
                        new_result = self.memory.add(memory, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata)
                        if new_result:
                            all_results.extend(new_result)
            
            if not all_results:
                logger.warning("No memories were stored or found")
            else:
                logger.info(f"Final storage results: {all_results}")
                
            return all_results
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}", exc_info=True)
            raise Exception(f"Error processing file {file_path}: {str(e)}")
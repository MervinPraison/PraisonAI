import os
import logging
import uuid
import time
from .chunking import Chunking
from functools import cached_property
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

logger = logging.getLogger(__name__)

class CustomMemory:
    @classmethod
    def from_config(cls, config):
        from mem0 import Memory
        return type('CustomMemory', (Memory,), {
            '_add_to_vector_store': cls._add_to_vector_store
        }).from_config(config)

    @staticmethod
    def _add_to_vector_store(self, messages, metadata, filters, infer):
        # Custom implementation that doesn't use LLM
        parsed_messages = "\n".join([msg["content"] for msg in messages])
        
        # Create a simple fact without using LLM
        new_retrieved_facts = [parsed_messages]
        
        # Process embeddings and continue with vector store operations
        new_message_embeddings = {}
        for new_mem in new_retrieved_facts:
            messages_embeddings = self.embedding_model.embed(new_mem)
            new_message_embeddings[new_mem] = messages_embeddings
            
        # Create the memory
        memory_id = self._create_memory(
            data=parsed_messages,
            existing_embeddings=new_message_embeddings,
            metadata=metadata
        )
        
        return [{
            "id": memory_id,
            "memory": parsed_messages,
            "event": "ADD"
        }]

class Knowledge:
    def __init__(self, config=None, verbose=None):
        self._config = config
        self._verbose = verbose or 0
        os.environ['ANONYMIZED_TELEMETRY'] = 'False'  # Chromadb
        
        # Configure logging levels based on verbose setting
        if not self._verbose:
            # Suppress logs from all relevant dependencies
            for logger_name in [
                'mem0', 
                'chromadb', 
                'local_persistent_hnsw',
                '_client',
                'main'
            ]:
                logging.getLogger(logger_name).setLevel(logging.WARNING)
            
            # Disable OpenAI API request logging
            logging.getLogger('openai').setLevel(logging.WARNING)
            
            # Set root logger to warning to catch any uncategorized logs
            logging.getLogger().setLevel(logging.WARNING)

    @cached_property
    def _deps(self):
        try:
            from markitdown import MarkItDown
            import chromadb
            return {
                'chromadb': chromadb,
                'markdown': MarkItDown()
            }
        except ImportError:
            raise ImportError(
                "Required packages not installed. Please install using: "
                'pip install "praisonaiagents[knowledge]"'
            )

    @cached_property
    def config(self):
        # Generate unique collection name for each instance (only if not provided in config)
        default_collection = f"test_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        persist_dir = ".praison"

        # Create persistent client config
        base_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": default_collection,
                    "path": persist_dir,
                    "client": self._deps['chromadb'].PersistentClient(path=persist_dir),
                    "host": None,
                    "port": None
                }
            },
            "version": "v1.1",
            "custom_prompt": "Return {{\"facts\": [text]}} where text is the exact input provided and json response",
            "reranker": {
                "enabled": False,
                "default_rerank": False
            }
        }

        # If config is provided, merge it with base config
        if self._config:
            # Merge version if provided
            if "version" in self._config:
                base_config["version"] = self._config["version"]
            
            # Merge vector_store config
            if "vector_store" in self._config:
                if "provider" in self._config["vector_store"]:
                    base_config["vector_store"]["provider"] = self._config["vector_store"]["provider"]
            
                if "config" in self._config["vector_store"]:
                    config_copy = self._config["vector_store"]["config"].copy()
                    # Only exclude client as it's managed internally
                    if "client" in config_copy:
                        del config_copy["client"]
                    base_config["vector_store"]["config"].update(config_copy)
            
            # Merge embedder config if provided
            if "embedder" in self._config:
                base_config["embedder"] = self._config["embedder"]
            
            # Merge llm config if provided
            if "llm" in self._config:
                base_config["llm"] = self._config["llm"]
            
            # Merge reranker config if provided
            if "reranker" in self._config:
                base_config["reranker"].update(self._config["reranker"])
        return base_config

    @cached_property
    def memory(self):
        try:
            return CustomMemory.from_config(self.config)
        except (NotImplementedError, ValueError) as e:
            if "list_collections" in str(e) or "Extra fields not allowed" in str(e):
                # Keep only allowed fields
                vector_store_config = {
                    "collection_name": self.config["vector_store"]["config"]["collection_name"],
                    "path": self.config["vector_store"]["config"]["path"]
                }
                self.config["vector_store"]["config"] = vector_store_config
                from mem0 import Memory
                return Memory.from_config(self.config)
            raise

    @cached_property
    def markdown(self):
        return self._deps['markdown']

    @cached_property
    def chunker(self):
        return Chunking(
            chunker_type='recursive',
            chunk_size=512,
            chunk_overlap=50
        )

    def _log(self, message, level=2):
        """Internal logging helper"""
        if self._verbose and self._verbose >= level:
            logger.info(message)

    def store(self, content, user_id=None, agent_id=None, run_id=None, metadata=None):
        """Store a memory."""
        try:
            if isinstance(content, str):
                if any(content.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.txt']):
                    self._log(f"Content appears to be a file path, processing file: {content}")
                    return self.add(content, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata)
                
                content = content.strip()
                if not content:
                    return []
                
            result = self.memory.add(content, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata)
            self._log(f"Store operation result: {result}")
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

    def search(self, query, user_id=None, agent_id=None, run_id=None, rerank=None, **kwargs):
        """Search for memories related to a query.
        
        Args:
            query: The search query string
            user_id: Optional user ID for user-specific search
            agent_id: Optional agent ID for agent-specific search  
            run_id: Optional run ID for run-specific search
            rerank: Whether to use Mem0's advanced reranking. If None, uses config default
            **kwargs: Additional search parameters to pass to Mem0 (keyword_search, filter_memories, etc.)
        
        Returns:
            List of search results, reranked if rerank=True
        """
        # Use config default if rerank not explicitly specified
        if rerank is None:
            rerank = self.config.get("reranker", {}).get("default_rerank", False)
        
        return self.memory.search(query, user_id=user_id, agent_id=agent_id, run_id=run_id, rerank=rerank, **kwargs)

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
        """Read file content and store it in memory.
        
        Args:
            file_path: Can be:
                - A string path to local file
                - A URL string
                - A list containing file paths and/or URLs
        """
        if isinstance(file_path, (list, tuple)):
            results = []
            for path in file_path:
                result = self._process_single_input(path, user_id, agent_id, run_id, metadata)
                results.extend(result.get('results', []))
            return {'results': results, 'relations': []}
        
        return self._process_single_input(file_path, user_id, agent_id, run_id, metadata)

    def _process_single_input(self, input_path, user_id=None, agent_id=None, run_id=None, metadata=None):
        """Process a single input which can be a file path or URL."""
        try:
            # Define supported file extensions
            DOCUMENT_EXTENSIONS = {
                'document': ('.pdf', '.ppt', '.pptx', '.doc', '.docx', '.xls', '.xlsx'),
                'media': ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.mp3', '.wav', '.ogg', '.m4a'),
                'text': ('.txt', '.csv', '.json', '.xml', '.md', '.html', '.htm'),
                'archive': '.zip'
            }

            # Check if input is URL
            if isinstance(input_path, str) and (input_path.startswith('http://') or input_path.startswith('https://')):
                self._log(f"Processing URL: {input_path}")
                raise NotImplementedError("URL processing not yet implemented")

            # Check if input ends with any supported extension
            is_supported_file = any(input_path.lower().endswith(ext) 
                                  for exts in DOCUMENT_EXTENSIONS.values()
                                  for ext in (exts if isinstance(exts, tuple) else (exts,)))
            
            if is_supported_file:
                self._log(f"Processing as file path: {input_path}")
                if not os.path.exists(input_path):
                    logger.error(f"File not found: {input_path}")
                    raise FileNotFoundError(f"File not found: {input_path}")
                
                file_ext = '.' + input_path.lower().split('.')[-1]  # Get extension reliably
                
                # Process file based on type
                if file_ext in DOCUMENT_EXTENSIONS['text']:
                    with open(input_path, 'r', encoding='utf-8') as file:
                        content = file.read().strip()
                    if not content:
                        raise ValueError("Empty text file")
                    memories = [self.normalize_content(content)]
                else:
                    # Use MarkItDown for documents and media
                    result = self.markdown.convert(input_path)
                    content = result.text_content
                    if not content:
                        raise ValueError("No content could be extracted from file")
                    chunks = self.chunker.chunk(content)
                    memories = [chunk.text.strip() if hasattr(chunk, 'text') else str(chunk).strip() 
                              for chunk in chunks if chunk]

                # Set metadata for file
                if not metadata:
                    metadata = {}
                metadata['file_type'] = file_ext.lstrip('.')
                metadata['filename'] = os.path.basename(input_path)
            else:
                # Treat as raw text content only if no file extension
                memories = [self.normalize_content(input_path)]

            # Create progress display
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                transient=True
            )

            # Store memories with progress bar
            all_results = []
            with progress:
                store_task = progress.add_task(f"Adding to Knowledge from {os.path.basename(input_path)}", total=len(memories))
                for memory in memories:
                    if memory:
                        memory_result = self.store(memory, user_id=user_id, agent_id=agent_id, 
                                                 run_id=run_id, metadata=metadata)
                        if memory_result:
                            all_results.extend(memory_result.get('results', []))
                        progress.advance(store_task)

            return {'results': all_results, 'relations': []}

        except Exception as e:
            logger.error(f"Error processing input {input_path}: {str(e)}", exc_info=True)
            raise
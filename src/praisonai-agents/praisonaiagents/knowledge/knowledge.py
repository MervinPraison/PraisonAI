import os
import logging
import uuid
import time
from datetime import datetime
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
    def _add_to_vector_store(self, messages, metadata=None, filters=None, infer=None):
        # Custom implementation that doesn't use LLM
        # Handle different message formats for backward compatibility
        if isinstance(messages, list):
            parsed_messages = "\n".join([msg.get("content", str(msg)) if isinstance(msg, dict) else str(msg) for msg in messages])
        else:
            parsed_messages = str(messages)
        
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
            metadata=metadata or {}
        )
        
        return [{
            "id": memory_id,
            "memory": parsed_messages,
            "event": "ADD"
        }]

class MongoDBMemory:
    """MongoDB-based memory store for knowledge management."""
    
    def __init__(self, config):
        self.config = config
        self.vector_store_config = config.get("vector_store", {}).get("config", {})
        self.connection_string = self.vector_store_config.get("connection_string", "mongodb://localhost:27017/")
        self.database_name = self.vector_store_config.get("database", "praisonai")
        self.collection_name = self.vector_store_config.get("collection", "knowledge_base")
        self.use_vector_search = self.vector_store_config.get("use_vector_search", True)
        
        # Initialize embedding model before MongoDB to ensure embedding_model_name is available
        self._init_embedding_model()
        
        # Initialize MongoDB client
        self._init_mongodb()
    
    def _init_mongodb(self):
        """Initialize MongoDB client and collection."""
        try:
            from pymongo import MongoClient
            
            self.client = MongoClient(
                self.connection_string,
                maxPoolSize=50,
                retryWrites=True,
                retryReads=True
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            # Setup database and collection
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            
            # Create indexes
            self._create_indexes()
            
        except Exception as e:
            raise Exception(f"Failed to initialize MongoDB: {e}")
    
    def _init_embedding_model(self):
        """Initialize embedding model from config."""
        try:
            # Set up embedding model based on config
            embedder_config = self.config.get("embedder", {})
            if embedder_config.get("provider") == "openai":
                import openai
                self.embedding_model = openai.OpenAI()
                self.embedding_model_name = embedder_config.get("config", {}).get("model", "text-embedding-3-small")
            else:
                # Default to OpenAI
                import openai
                self.embedding_model = openai.OpenAI()
                self.embedding_model_name = "text-embedding-3-small"
        except Exception as e:
            raise Exception(f"Failed to initialize embedding model: {e}")
    
    def _get_embedding_dimensions(self, model_name: str) -> int:
        """Get embedding dimensions based on model name."""
        # Common embedding model dimensions
        model_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
            "text-embedding-002": 1536,
            # Add more models as needed
        }
        
        # Check if model name contains known model identifiers
        for model_key, dimensions in model_dimensions.items():
            if model_key in model_name.lower():
                return dimensions
        
        # Default to 1536 for unknown models (OpenAI standard)
        return 1536
    
    def _create_indexes(self):
        """Create necessary indexes for MongoDB."""
        try:
            # Text search index
            self.collection.create_index([("content", "text")])
            
            # Metadata indexes
            self.collection.create_index([("metadata.filename", 1)])
            self.collection.create_index([("created_at", -1)])
            
            # Vector search index for Atlas (if enabled)
            if self.use_vector_search:
                self._create_vector_index()
                
        except Exception as e:
            logging.warning(f"Could not create MongoDB indexes: {e}")
    
    def _create_vector_index(self):
        """Create vector search index for Atlas Vector Search."""
        try:
            vector_index_def = {
                "mappings": {
                    "dynamic": True,
                    "fields": {
                        "embedding": {
                            "type": "knnVector",
                            "dimensions": self._get_embedding_dimensions(self.embedding_model_name),
                            "similarity": "cosine"
                        }
                    }
                }
            }
            
            # Use SearchIndexModel for PyMongo 4.6+ compatibility
            try:
                from pymongo.operations import SearchIndexModel
                search_index_model = SearchIndexModel(definition=vector_index_def, name="vector_index")
                self.collection.create_search_index(search_index_model)
            except ImportError:
                # Fallback for older PyMongo versions
                self.collection.create_search_index(vector_index_def, "vector_index")
            
        except Exception as e:
            logging.warning(f"Could not create vector search index: {e}")
    
    def _get_embedding(self, text):
        """Get embedding for text."""
        try:
            response = self.embedding_model.embeddings.create(
                input=text,
                model=self.embedding_model_name
            )
            return response.data[0].embedding
        except Exception as e:
            logging.error(f"Error getting embedding: {e}")
            return None
    
    def add(self, messages, user_id=None, agent_id=None, run_id=None, metadata=None):
        """Add memory to MongoDB."""
        try:
            # Handle different message formats
            if isinstance(messages, list):
                content = "\n".join([msg.get("content", str(msg)) if isinstance(msg, dict) else str(msg) for msg in messages])
            else:
                content = str(messages)
            
            # Generate embedding
            embedding = self._get_embedding(content) if self.use_vector_search else None
            
            # Create document
            doc = {
                "content": content,
                "metadata": metadata or {},
                "user_id": user_id,
                "agent_id": agent_id,
                "run_id": run_id,
                "created_at": datetime.utcnow(),
                "memory_type": "knowledge"
            }
            
            if embedding:
                doc["embedding"] = embedding
            
            # Insert document
            result = self.collection.insert_one(doc)
            
            return [{
                "id": str(result.inserted_id),
                "memory": content,
                "event": "ADD"
            }]
            
        except Exception as e:
            logging.error(f"Error adding memory to MongoDB: {e}")
            return []
    
    def search(self, query, user_id=None, agent_id=None, run_id=None, rerank=False, **kwargs):
        """Search memories in MongoDB."""
        try:
            results = []
            
            # Vector search if enabled
            if self.use_vector_search:
                embedding = self._get_embedding(query)
                if embedding:
                    pipeline = [
                        {
                            "$vectorSearch": {
                                "index": "vector_index",
                                "path": "embedding",
                                "queryVector": embedding,
                                "numCandidates": kwargs.get("limit", 10) * 10,
                                "limit": kwargs.get("limit", 10)
                            }
                        },
                        {
                            "$addFields": {
                                "score": {"$meta": "vectorSearchScore"}
                            }
                        }
                    ]
                    
                    # Add filters if provided
                    if user_id or agent_id or run_id:
                        match_filter = {}
                        if user_id:
                            match_filter["user_id"] = user_id
                        if agent_id:
                            match_filter["agent_id"] = agent_id
                        if run_id:
                            match_filter["run_id"] = run_id
                        
                        pipeline.append({"$match": match_filter})
                    
                    for doc in self.collection.aggregate(pipeline):
                        results.append({
                            "id": str(doc["_id"]),
                            "memory": doc["content"],
                            "metadata": doc.get("metadata", {}),
                            "score": doc.get("score", 1.0)
                        })
            
            # Fallback to text search
            if not results:
                search_filter = {"$text": {"$search": query}}
                
                # Add additional filters
                if user_id:
                    search_filter["user_id"] = user_id
                if agent_id:
                    search_filter["agent_id"] = agent_id
                if run_id:
                    search_filter["run_id"] = run_id
                
                for doc in self.collection.find(search_filter).limit(kwargs.get("limit", 10)):
                    results.append({
                        "id": str(doc["_id"]),
                        "memory": doc["content"],
                        "metadata": doc.get("metadata", {}),
                        "score": 1.0
                    })
            
            return results
            
        except Exception as e:
            logging.error(f"Error searching MongoDB: {e}")
            return []
    
    def get_all(self, user_id=None, agent_id=None, run_id=None):
        """Get all memories from MongoDB."""
        try:
            search_filter = {}
            if user_id:
                search_filter["user_id"] = user_id
            if agent_id:
                search_filter["agent_id"] = agent_id
            if run_id:
                search_filter["run_id"] = run_id
            
            results = []
            for doc in self.collection.find(search_filter):
                results.append({
                    "id": str(doc["_id"]),
                    "memory": doc["content"],
                    "metadata": doc.get("metadata", {}),
                    "created_at": doc.get("created_at")
                })
            
            return results
            
        except Exception as e:
            logging.error(f"Error getting all memories from MongoDB: {e}")
            return []
    
    def get(self, memory_id):
        """Get a specific memory by ID."""
        try:
            from bson import ObjectId
            doc = self.collection.find_one({"_id": ObjectId(memory_id)})
            if doc:
                return {
                    "id": str(doc["_id"]),
                    "memory": doc["content"],
                    "metadata": doc.get("metadata", {}),
                    "created_at": doc.get("created_at")
                }
            return None
            
        except Exception as e:
            logging.error(f"Error getting memory from MongoDB: {e}")
            return None
    
    def update(self, memory_id, data):
        """Update a memory."""
        try:
            from bson import ObjectId
            result = self.collection.update_one(
                {"_id": ObjectId(memory_id)},
                {"$set": {"content": data, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
            
        except Exception as e:
            logging.error(f"Error updating memory in MongoDB: {e}")
            return False
    
    def delete(self, memory_id):
        """Delete a memory."""
        try:
            from bson import ObjectId
            result = self.collection.delete_one({"_id": ObjectId(memory_id)})
            return result.deleted_count > 0
            
        except Exception as e:
            logging.error(f"Error deleting memory from MongoDB: {e}")
            return False
    
    def delete_all(self, user_id=None, agent_id=None, run_id=None):
        """Delete all memories."""
        try:
            search_filter = {}
            if user_id:
                search_filter["user_id"] = user_id
            if agent_id:
                search_filter["agent_id"] = agent_id
            if run_id:
                search_filter["run_id"] = run_id
            
            result = self.collection.delete_many(search_filter)
            return result.deleted_count
            
        except Exception as e:
            logging.error(f"Error deleting all memories from MongoDB: {e}")
            return 0
    
    def reset(self):
        """Reset all memories."""
        try:
            result = self.collection.delete_many({})
            return result.deleted_count
            
        except Exception as e:
            logging.error(f"Error resetting MongoDB memories: {e}")
            return 0

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
                    
                    # Special handling for MongoDB vector store
                    if self._config["vector_store"]["provider"] == "mongodb":
                        base_config["vector_store"] = {
                            "provider": "mongodb",
                            "config": {
                                "connection_string": self._config["vector_store"]["config"].get("connection_string", "mongodb://localhost:27017/"),
                                "database": self._config["vector_store"]["config"].get("database", "praisonai"),
                                "collection": self._config["vector_store"]["config"].get("collection", "knowledge_base"),
                                "use_vector_search": self._config["vector_store"]["config"].get("use_vector_search", True)
                            }
                        }
            
                if "config" in self._config["vector_store"] and self._config["vector_store"]["provider"] != "mongodb":
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
            
            # Merge graph_store config if provided (for graph memory support)
            if "graph_store" in self._config:
                base_config["graph_store"] = self._config["graph_store"]
        return base_config

    @cached_property
    def memory(self):
        # Check if MongoDB provider is specified
        if (self.config.get("vector_store", {}).get("provider") == "mongodb"):
            try:
                return MongoDBMemory(self.config)
            except Exception as e:
                logger.error(f"Failed to initialize MongoDB memory: {e}")
                # Fall back to default memory
                pass
        
        # Default Mem0 memory
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
                
            # Try new API format first, fall back to old format for backward compatibility
            try:
                # Convert content to messages format for mem0 API compatibility
                if isinstance(content, str):
                    messages = [{"role": "user", "content": content}]
                else:
                    messages = content if isinstance(content, list) else [{"role": "user", "content": str(content)}]
                
                result = self.memory.add(messages=messages, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata)
            except TypeError as e:
                # Fallback to old API format if messages parameter is not supported
                if "unexpected keyword argument" in str(e) or "positional argument" in str(e):
                    self._log(f"Falling back to legacy API format due to: {e}")
                    result = self.memory.add(content, user_id=user_id, agent_id=agent_id, run_id=run_id, metadata=metadata)
                else:
                    raise
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
                            # Handle both dict and list formats for backward compatibility
                            if isinstance(memory_result, dict):
                                all_results.extend(memory_result.get('results', []))
                            elif isinstance(memory_result, list):
                                all_results.extend(memory_result)
                            else:
                                # Log warning for unexpected types but don't break
                                import logging
                                logging.warning(f"Unexpected memory_result type: {type(memory_result)}, skipping")
                        progress.advance(store_task)

            return {'results': all_results, 'relations': []}

        except Exception as e:
            logger.error(f"Error processing input {input_path}: {str(e)}", exc_info=True)
            raise
import os
import logging
from praisonaiagents._logging import get_logger
from datetime import datetime
from .chunking import Chunking
from functools import cached_property


logger = get_logger(__name__)

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

# MongoDBMemory has been moved to adapters/mongodb_adapter.py
# This maintains backward compatibility while following protocol-driven architecture

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
                get_logger(logger_name).setLevel(logging.WARNING)
            
            # Disable OpenAI API request logging
            get_logger('openai').setLevel(logging.WARNING)
            
        # Initialize provider using protocol-driven approach
        self._provider = None

    @cached_property 
    def _deps(self):
        """Lazy load dependencies only when needed (backward compatibility)."""
        # This is kept for backward compatibility with existing code
        # The new protocol-driven approach uses adapters via registry
        try:
            from markitdown import MarkItDown
            return {
                'markdown': MarkItDown()
            }
        except ImportError:
            raise ImportError(
                "Required packages not installed. Please install using: "
                'pip install "praisonaiagents[knowledge]"'
            )

    @cached_property
    def config(self):
        # Use deterministic collection name for persistence across restarts
        # Only generate unique name if explicitly requested via config
        default_collection = "praisonai_knowledge"
        from ..paths import get_project_data_dir
        persist_dir = str(get_project_data_dir())

        # Create persistent client config (protocol-driven)
        base_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": default_collection,
                    "path": persist_dir,
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

    def _prepare_mem0_config(self, config):
        """Prepare config for mem0 by removing PraisonAI-specific fields.
        
        mem0's RerankerConfig only accepts 'provider' and 'config' fields.
        PraisonAI adds 'enabled' and 'default_rerank' for internal use.
        """
        mem0_config = config.copy()
        
        # Strip PraisonAI-specific reranker fields that mem0 doesn't accept
        if "reranker" in mem0_config:
            reranker = mem0_config["reranker"]
            if isinstance(reranker, dict):
                # Keep only mem0-compatible fields: provider, config
                mem0_reranker = {}
                if "provider" in reranker:
                    mem0_reranker["provider"] = reranker["provider"]
                if "config" in reranker:
                    mem0_reranker["config"] = reranker["config"]
                
                # If no valid mem0 fields, remove reranker entirely
                if mem0_reranker:
                    mem0_config["reranker"] = mem0_reranker
                else:
                    del mem0_config["reranker"]
        
        return mem0_config

    @cached_property
    def memory(self):
        """Initialize knowledge adapter using protocol-driven approach."""
        # Import registry functions
        from .adapters import get_knowledge_adapter, get_first_available_knowledge_adapter
        
        # Determine provider preference
        provider = self.config.get("vector_store", {}).get("provider", "mem0")
        self._log(f"Requested knowledge provider: {provider}")
        
        # Map legacy provider names to adapter names
        provider_mapping = {
            "chroma": "chroma",
            "mongodb": "mongodb", 
            "mem0": "mem0",
            "sqlite": "sqlite"
        }
        
        adapter_name = provider_mapping.get(provider, "mem0")
        
        # Try to get preferred adapter, fallback to available ones
        try:
            adapter = get_knowledge_adapter(adapter_name, config=self.config, verbose=self._verbose)
        except Exception as e:
            self._log(f"Failed to initialize '{adapter_name}': {e}")
            adapter = None
        
        if adapter is None:
            # Fallback to first available adapter
            self._log(f"Provider '{adapter_name}' not available, trying fallbacks")
            fallback_result = get_first_available_knowledge_adapter(
                preferences=["sqlite", "mem0"],
                config=self.config,
                verbose=self._verbose
            )
            if fallback_result:
                adapter_name, adapter = fallback_result
                self._log(f"Using fallback knowledge adapter: {adapter_name}")
            else:
                # Final fallback: try legacy mem0 approach for backward compatibility
                return self._init_legacy_memory()
        
        self._log(f"Initialized knowledge adapter: {adapter_name}")
        return adapter
        
    def _init_legacy_memory(self):
        """Legacy fallback memory initialization for backward compatibility."""
        # Prepare config for mem0 (strip PraisonAI-specific fields)
        mem0_config = self._prepare_mem0_config(self.config)
        
        # Default Mem0 memory
        try:
            return CustomMemory.from_config(mem0_config)
        except (NotImplementedError, ValueError) as e:
            if "list_collections" in str(e) or "Extra fields not allowed" in str(e):
                # Keep only allowed fields
                vector_store_config = {
                    "collection_name": mem0_config["vector_store"]["config"]["collection_name"],
                    "path": mem0_config["vector_store"]["config"]["path"]
                }
                mem0_config["vector_store"]["config"] = vector_store_config
                from mem0 import Memory
                return Memory.from_config(mem0_config)
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

    def _emit_knowledge_event(self, event_type: str, query: str = "", results=None, 
                              agent_id: str = None, source: str = "", chunk_count: int = 0,
                              metadata: dict = None):
        """Emit knowledge trace event if tracing is enabled (zero overhead when disabled)."""
        try:
            from ..trace.context_events import get_context_emitter
            emitter = get_context_emitter()
            if not emitter.enabled:
                return
            agent_name = agent_id or "unknown"
            if event_type == "search":
                result_list = results if isinstance(results, list) else []
                sources = []
                top_score = None
                for r in result_list[:10]:
                    if isinstance(r, dict):
                        meta = r.get("metadata", {})
                        if meta and isinstance(meta, dict):
                            src = meta.get("source") or meta.get("filename", "")
                            if src:
                                sources.append(src)
                        if top_score is None:
                            top_score = r.get("score")
                emitter.knowledge_search(agent_name, query, len(result_list), sources, top_score)
            elif event_type == "add":
                emitter.knowledge_add(agent_name, source, chunk_count, metadata)
        except Exception:
            pass  # Silent fail - tracing should never break knowledge operations

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
        
        try:
            results = self.memory.search(query, user_id=user_id, agent_id=agent_id, run_id=run_id, rerank=rerank, **kwargs)
        except TypeError as e:
            # Additional safeguard for mem0 MongoDB vector store issues
            error_msg = str(e).lower()
            if "unexpected keyword argument" in error_msg and "vectors" in error_msg:
                logger.warning(
                    "Knowledge search failed due to mem0 MongoDB vector store compatibility issue. "
                    "This is a known upstream bug: https://github.com/mem0ai/mem0/issues/3185. "
                    "Returning empty results."
                )
                results = []
            else:
                raise
        
        # Emit trace event for knowledge search
        self._emit_knowledge_event("search", query, results, agent_id)
        
        return results

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
        """Process a single input which can be a file path, directory, or URL."""
        try:
            # Define supported file extensions
            DOCUMENT_EXTENSIONS = {
                'document': ('.pdf', '.ppt', '.pptx', '.doc', '.docx', '.xls', '.xlsx'),
                'media': ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.mp3', '.wav', '.ogg', '.m4a'),
                'text': ('.txt', '.csv', '.json', '.xml', '.md', '.html', '.htm'),
                'archive': '.zip'
            }
            
            # Get all supported extensions as a flat tuple
            all_extensions = []
            for exts in DOCUMENT_EXTENSIONS.values():
                if isinstance(exts, tuple):
                    all_extensions.extend(exts)
                else:
                    all_extensions.append(exts)
            all_extensions = tuple(all_extensions)

            # Check if input is URL
            if isinstance(input_path, str) and (input_path.startswith('http://') or input_path.startswith('https://')):
                self._log(f"Processing URL: {input_path}")
                raise NotImplementedError("URL processing not yet implemented")
            
            # CRITICAL FIX: Check if input is a directory - recursively process all files
            if os.path.isdir(input_path):
                self._log(f"Processing directory: {input_path}")
                all_results = []
                
                # Walk through directory and process all supported files
                for root, dirs, files in os.walk(input_path):
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        # Only process files with supported extensions
                        if filename.lower().endswith(all_extensions):
                            try:
                                result = self._process_single_input(
                                    file_path, user_id, agent_id, run_id, metadata
                                )
                                all_results.extend(result.get('results', []))
                            except Exception as e:
                                logger.warning(f"Failed to process file {file_path}: {e}")
                
                if not all_results:
                    logger.warning(f"No supported files found in directory: {input_path}")
                
                return {'results': all_results, 'relations': []}

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
            from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
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
                                from .models import AddResult
                                if isinstance(memory_result, AddResult):
                                    all_results.append(memory_result.id)
                                elif hasattr(memory_result, 'results'):
                                    all_results.extend(memory_result.results)
                                else:
                                    # Log warning for unexpected types but don't break
                                    import logging
                                    logging.warning(f"Unexpected memory_result type: {type(memory_result)}, skipping")
                            progress.advance(store_task)

            # Emit trace event for knowledge add
            self._emit_knowledge_event("add", source=input_path, chunk_count=len(memories), 
                                       metadata=metadata, agent_id=agent_id)
            
            return {'results': all_results, 'relations': []}

        except Exception as e:
            logger.error(f"Error processing input {input_path}: {str(e)}", exc_info=True)
            raise
    
    def index(
        self,
        path: str,
        incremental: bool = True,
        force: bool = False,
        include_glob: list = None,
        exclude_glob: list = None,
        user_id: str = None,
        agent_id: str = None,
        run_id: str = None,
    ):
        """
        Index a directory or file for knowledge retrieval.
        
        Supports incremental indexing - only changed files are re-indexed.
        
        Args:
            path: Directory or file path to index
            incremental: If True, only index changed files (default: True)
            force: If True, re-index all files regardless of changes
            include_glob: List of glob patterns to include (e.g., ["*.py", "*.md"])
            exclude_glob: List of glob patterns to exclude (e.g., ["*.log", "test_*"])
            user_id: Optional user ID for scoping
            agent_id: Optional agent ID for scoping
            run_id: Optional run ID for scoping
            
        Returns:
            IndexResult with indexing statistics
        """
        from .indexing import IndexResult, CorpusStats, IgnoreMatcher, FileTracker
        import time as time_module
        import fnmatch as fnmatch_module
        
        start_time = time_module.time()
        
        result = IndexResult()
        
        # Initialize file tracker for incremental indexing
        from ..paths import DEFAULT_DIR_NAME
        state_dir = os.path.join(os.path.dirname(path) if os.path.isfile(path) else path, DEFAULT_DIR_NAME)
        os.makedirs(state_dir, exist_ok=True)
        state_file = os.path.join(state_dir, ".index_state.json")
        
        tracker = FileTracker(state_file=state_file)
        if incremental and not force:
            tracker.load()
        
        # Initialize ignore matcher
        ignore_matcher = IgnoreMatcher.from_directory(path if os.path.isdir(path) else os.path.dirname(path))
        
        # Collect files to index
        files_to_index = []
        
        if os.path.isfile(path):
            files_to_index = [path]
        else:
            for root, dirs, files in os.walk(path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for filename in files:
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, path)
                    
                    # Check ignore patterns
                    if ignore_matcher.should_ignore(rel_path):
                        continue
                    
                    # Check include patterns
                    if include_glob:
                        matched = False
                        for pattern in include_glob:
                            if fnmatch_module.fnmatch(filename, pattern):
                                matched = True
                                break
                        if not matched:
                            continue
                    
                    # Check exclude patterns
                    if exclude_glob:
                        excluded = False
                        for pattern in exclude_glob:
                            if fnmatch_module.fnmatch(filename, pattern) or fnmatch_module.fnmatch(rel_path, pattern):
                                excluded = True
                                break
                        if excluded:
                            continue
                    
                    files_to_index.append(filepath)
        
        # Index files
        total_chunks = 0
        for filepath in files_to_index:
            try:
                # Check if file has changed (for incremental indexing)
                if incremental and not force and not tracker.has_changed(filepath):
                    result.files_skipped += 1
                    continue
                
                # Index the file
                add_result = self.add(
                    filepath,
                    user_id=user_id,
                    agent_id=agent_id,
                    run_id=run_id,
                )
                
                # Count chunks
                if add_result and isinstance(add_result, dict):
                    chunks = len(add_result.get('results', []))
                    total_chunks += chunks
                
                # Mark as indexed
                file_info = tracker.get_file_info(filepath)
                tracker.mark_indexed(filepath, file_info)
                
                result.files_indexed += 1
                
            except Exception as e:
                result.errors.append(f"{filepath}: {str(e)}")
        
        # Save tracker state
        if incremental:
            tracker.save()
        
        # Calculate stats
        result.chunks_created = total_chunks
        result.duration_seconds = time_module.time() - start_time
        result.corpus_stats = CorpusStats(
            file_count=result.files_indexed + result.files_skipped,
            chunk_count=total_chunks,
            path=path,
            indexed_at=datetime.now().isoformat(),
        )
        
        # Store corpus stats for later retrieval
        self._corpus_stats = result.corpus_stats
        
        return result
    
    def get_corpus_stats(self):
        """
        Get statistics about the indexed corpus.
        
        Returns:
            CorpusStats with file count, chunk count, and strategy recommendation
        """
        from .indexing import CorpusStats
        
        if hasattr(self, '_corpus_stats') and self._corpus_stats:
            return self._corpus_stats
        
        # Return empty stats if not indexed
        return CorpusStats()
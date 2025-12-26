"""
Knowledge Handler for CLI.

Provides RAG/vector store management with full knowledge stack support.

Usage:
    praisonai knowledge add document.pdf
    praisonai knowledge add ./docs/
    praisonai knowledge query "How to authenticate?"
    praisonai knowledge list
    praisonai knowledge clear
    praisonai knowledge stats
"""

import os
from typing import Any, Dict, List, Optional
from .base import CommandHandler


class KnowledgeHandler(CommandHandler):
    """
    Handler for knowledge command.
    
    Manages knowledge base for RAG (Retrieval Augmented Generation).
    
    Supports:
    - Multiple vector stores (chroma, pinecone, qdrant, weaviate, memory)
    - Retrieval strategies (basic, fusion, recursive, auto_merge)
    - Rerankers (simple, llm, cross_encoder, cohere)
    - Index types (vector, keyword, hybrid)
    - Query modes (default, sub_question, summarize)
    
    Example:
        praisonai knowledge add document.pdf
        praisonai knowledge add ./docs/
        praisonai knowledge query "How to authenticate?" --retrieval fusion
        praisonai knowledge list
        praisonai knowledge clear
        praisonai knowledge stats
    """
    
    def __init__(
        self, 
        verbose: bool = False, 
        workspace: str = None,
        vector_store: str = "chroma",
        retrieval_strategy: str = "basic",
        reranker: Optional[str] = None,
        index_type: str = "vector",
        query_mode: str = "default",
        session_id: Optional[str] = None,
        db: Optional[str] = None
    ):
        super().__init__(verbose)
        self.workspace = workspace or os.getcwd()
        self.vector_store = vector_store
        self.retrieval_strategy = retrieval_strategy
        self.reranker = reranker
        self.index_type = index_type
        self.query_mode = query_mode
        self.session_id = session_id
        self.db = db
        self._knowledge = None
        self._embedding_fn = None
    
    @property
    def feature_name(self) -> str:
        return "knowledge"
    
    def get_actions(self) -> List[str]:
        return ["add", "query", "search", "list", "clear", "stats", "info", "export", "import", "help"]
    
    def get_help_text(self) -> str:
        return """
Knowledge Commands:
  praisonai knowledge add <file|dir|url>   - Add document(s) to knowledge base
  praisonai knowledge query "<question>"   - Query knowledge base with RAG
  praisonai knowledge list                 - List indexed documents
  praisonai knowledge clear                - Clear knowledge base
  praisonai knowledge stats                - Show knowledge base statistics
  praisonai knowledge export <file.json>   - Export knowledge base to JSON file
  praisonai knowledge import <file.json>   - Import knowledge base from JSON file
  praisonai knowledge help                 - Show this help message

Options:
  --workspace <path>              - Workspace directory (default: current)
  --vector-store <name>           - Vector store backend
                                    Values: memory, chroma, pinecone, qdrant, weaviate
                                    Default: chroma
  --retrieval-strategy <strategy> - Retrieval strategy
                                    Values: basic, fusion, recursive, auto_merge
                                    Default: basic
  --reranker <name>               - Reranker for result ordering
                                    Values: none, simple, llm, cross_encoder, cohere
                                    Default: none
  --index-type <type>             - Index type for search
                                    Values: vector, keyword, hybrid
                                    Default: vector
  --query-mode <mode>             - Query processing mode
                                    Values: default, sub_question, summarize
                                    Default: default
  --session <id>                  - Session ID for persistence
  --db <path>                     - Database path for persistence

Examples:
  praisonai knowledge add document.pdf
  praisonai knowledge add ./docs/
  praisonai knowledge query "How to authenticate?" --retrieval-strategy fusion
  praisonai knowledge query "Compare approaches" --reranker simple --query-mode sub_question
"""
    
    def _get_knowledge(self):
        """Lazy load Knowledge instance with configured options."""
        if self._knowledge is None:
            try:
                from praisonaiagents import Knowledge
                
                # Build config based on options
                config = {
                    "vector_store": {
                        "provider": self.vector_store,
                        "config": {
                            "path": os.path.join(self.workspace, ".praison", "knowledge")
                        }
                    }
                }
                
                self._knowledge = Knowledge(config=config)
            except ImportError:
                self.print_status(
                    "Knowledge requires praisonaiagents. Install with: pip install praisonaiagents[knowledge]",
                    "error"
                )
                return None
        return self._knowledge
    
    def _get_embedding_fn(self):
        """Get embedding function."""
        if self._embedding_fn is None:
            try:
                import openai
                client = openai.OpenAI()
                
                def embed(text: str) -> List[float]:
                    response = client.embeddings.create(
                        input=text,
                        model="text-embedding-3-small"
                    )
                    return response.data[0].embedding
                
                self._embedding_fn = embed
            except Exception as e:
                self.print_status(f"Failed to initialize embeddings: {e}", "warning")
        return self._embedding_fn
    
    def action_add(self, args: List[str], **kwargs) -> bool:
        """
        Add document(s) to knowledge base.
        
        Supports:
        - File paths (pdf, docx, txt, md, html, etc.)
        - Directories (recursive)
        - Glob patterns (*.pdf, docs/**/*.md)
        - URLs (http://, https://)
        
        Args:
            args: List containing file/directory/URL paths
            
        Returns:
            True if successful
        """
        if not args:
            self.print_status("Usage: praisonai knowledge add <file|directory|url|glob>", "error")
            return False
        
        knowledge = self._get_knowledge()
        if not knowledge:
            return False
        
        source = args[0]
        
        # Check if URL
        if source.startswith(("http://", "https://")):
            try:
                knowledge.add(source)
                self.print_status(f"✅ Added URL: {source}", "success")
                return True
            except Exception as e:
                self.print_status(f"Failed to add URL: {e}", "error")
                return False
        
        # Expand path
        if not os.path.isabs(source):
            source = os.path.join(self.workspace, source)
        
        # Check for glob pattern
        if "*" in source or "?" in source:
            import glob
            files = glob.glob(source, recursive=True)
            if not files:
                self.print_status(f"No files match pattern: {source}", "warning")
                return False
            
            count = 0
            for file_path in files:
                if os.path.isfile(file_path):
                    try:
                        knowledge.add(file_path)
                        count += 1
                    except Exception as e:
                        self.print_status(f"Failed to add {file_path}: {e}", "warning")
            
            self.print_status(f"✅ Added {count} files matching {args[0]}", "success")
            return True
        
        if not os.path.exists(source):
            self.print_status(f"Path not found: {source}", "error")
            return False
        
        try:
            if os.path.isdir(source):
                # Add all files in directory
                count = 0
                for root, _, files in os.walk(source):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            knowledge.add(file_path)
                            count += 1
                        except Exception as e:
                            if self.verbose:
                                self.print_status(f"Skipped {file}: {e}", "warning")
                self.print_status(f"✅ Added {count} files from {source}", "success")
            else:
                knowledge.add(source)
                self.print_status(f"✅ Added: {source}", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to add: {e}", "error")
            return False
    
    def action_search(self, args: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Alias for action_query."""
        return self.action_query(args, **kwargs)
    
    def action_query(self, args: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        Query knowledge base with RAG.
        
        Uses configured retrieval strategy, reranker, and query mode.
        
        Args:
            args: List containing query
            
        Returns:
            List of results with answer and sources
        """
        if not args:
            self.print_status("Usage: praisonai knowledge query <question>", "error")
            return []
        
        knowledge = self._get_knowledge()
        if not knowledge:
            return []
        
        query = ' '.join(args)
        limit = kwargs.get('limit', 5)
        
        try:
            # Use knowledge.search for basic retrieval
            results = knowledge.search(query, limit=limit)
            
            if results:
                self.print_status(f"\n🔍 Results for '{query}':\n", "info")
                for i, result in enumerate(results, 1):
                    if isinstance(result, dict):
                        content = result.get('memory', result.get('text', str(result)))[:200]
                        score = result.get('score', 'N/A')
                        self.print_status(f"  {i}. [score: {score}] {content}...", "info")
                    else:
                        content = str(result)[:200]
                        self.print_status(f"  {i}. {content}...", "info")
            else:
                self.print_status("No results found", "warning")
            
            return results
        except Exception as e:
            self.print_status(f"Query failed: {e}", "error")
            return []
    
    def action_list(self, args: List[str], **kwargs) -> List[str]:
        """
        List indexed documents.
        
        Returns:
            List of document names
        """
        knowledge = self._get_knowledge()
        if not knowledge:
            return []
        
        try:
            if hasattr(knowledge, 'list_documents'):
                docs = knowledge.list_documents()
            elif hasattr(knowledge, 'documents'):
                docs = list(knowledge.documents.keys()) if knowledge.documents else []
            else:
                docs = []
            
            if docs:
                self.print_status("\n📚 Indexed Documents:", "info")
                for doc in docs:
                    self.print_status(f"  - {doc}", "info")
            else:
                self.print_status("No documents indexed", "warning")
            
            return docs
        except Exception as e:
            self.print_status(f"Failed to list documents: {e}", "error")
            return []
    
    def action_clear(self, args: List[str], **kwargs) -> bool:
        """
        Clear knowledge base.
        
        Returns:
            True if successful
        """
        knowledge = self._get_knowledge()
        if not knowledge:
            return False
        
        try:
            if hasattr(knowledge, 'clear'):
                knowledge.clear()
            elif hasattr(knowledge, 'reset'):
                knowledge.reset()
            
            self.print_status("✅ Knowledge base cleared", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to clear: {e}", "error")
            return False
    
    def action_stats(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Show knowledge base statistics.
        
        Returns:
            Dictionary of statistics
        """
        knowledge = self._get_knowledge()
        if not knowledge:
            return {}
        
        stats = {
            "workspace": self.workspace,
            "vector_store": self.vector_store,
            "retrieval_strategy": self.retrieval_strategy,
            "reranker": self.reranker or "none",
            "index_type": self.index_type,
            "query_mode": self.query_mode
        }
        
        try:
            # Try to get document count from memory
            if hasattr(knowledge, 'memory'):
                mem = knowledge.memory
                if hasattr(mem, 'get_all'):
                    all_docs = mem.get_all()
                    stats['document_count'] = len(all_docs) if all_docs else 0
        except Exception:
            pass
        
        self.print_status("\n📊 Knowledge Base Statistics:", "info")
        for key, value in stats.items():
            self.print_status(f"  {key}: {value}", "info")
        
        return stats
    
    def action_info(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """Alias for action_stats."""
        return self.action_stats(args, **kwargs)
    
    def action_export(self, args: List[str], **kwargs) -> bool:
        """
        Export knowledge base to JSON file.
        
        Exports all documents with their metadata, embeddings, and content
        for backup or migration purposes.
        
        Args:
            args: List containing output file path
            
        Returns:
            True if successful
        """
        import json
        from datetime import datetime
        
        if not args:
            # Default filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(self.workspace, f"knowledge_export_{timestamp}.json")
        else:
            output_file = args[0]
            if not os.path.isabs(output_file):
                output_file = os.path.join(self.workspace, output_file)
        
        knowledge = self._get_knowledge()
        if not knowledge:
            return False
        
        try:
            export_data = {
                "version": "1.0",
                "exported_at": datetime.now().isoformat(),
                "workspace": self.workspace,
                "vector_store": self.vector_store,
                "documents": []
            }
            
            # Try to get all documents from knowledge/memory
            if hasattr(knowledge, 'memory') and hasattr(knowledge.memory, 'get_all'):
                all_docs = knowledge.memory.get_all()
                if all_docs:
                    for doc in all_docs:
                        if isinstance(doc, dict):
                            export_data["documents"].append(doc)
                        else:
                            export_data["documents"].append({
                                "content": str(doc),
                                "metadata": {}
                            })
            elif hasattr(knowledge, 'get_all'):
                all_docs = knowledge.get_all()
                if all_docs:
                    for doc in all_docs:
                        if isinstance(doc, dict):
                            export_data["documents"].append(doc)
                        else:
                            export_data["documents"].append({
                                "content": str(doc),
                                "metadata": {}
                            })
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            doc_count = len(export_data["documents"])
            self.print_status(f"✅ Exported {doc_count} documents to {output_file}", "success")
            return True
            
        except Exception as e:
            self.print_status(f"Export failed: {e}", "error")
            return False
    
    def action_import(self, args: List[str], **kwargs) -> bool:
        """
        Import knowledge base from JSON file.
        
        Imports documents from a previously exported JSON file.
        
        Args:
            args: List containing input file path
            
        Returns:
            True if successful
        """
        import json
        
        if not args:
            self.print_status("Usage: praisonai knowledge import <file.json>", "error")
            return False
        
        input_file = args[0]
        if not os.path.isabs(input_file):
            input_file = os.path.join(self.workspace, input_file)
        
        if not os.path.exists(input_file):
            self.print_status(f"File not found: {input_file}", "error")
            return False
        
        knowledge = self._get_knowledge()
        if not knowledge:
            return False
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # version field reserved for future schema migrations
            _ = import_data.get("version", "unknown")
            documents = import_data.get("documents", [])
            
            if not documents:
                self.print_status("No documents found in import file", "warning")
                return True
            
            imported_count = 0
            for doc in documents:
                try:
                    content = doc.get("content") or doc.get("memory") or doc.get("text", "")
                    metadata = doc.get("metadata", {})
                    
                    if content:
                        if hasattr(knowledge, 'store'):
                            knowledge.store(content, metadata=metadata)
                        elif hasattr(knowledge, 'add'):
                            knowledge.add(content, metadata=metadata)
                        imported_count += 1
                except Exception as e:
                    if self.verbose:
                        self.print_status(f"Skipped document: {e}", "warning")
            
            self.print_status(f"✅ Imported {imported_count} documents from {input_file}", "success")
            return True
            
        except json.JSONDecodeError as e:
            self.print_status(f"Invalid JSON file: {e}", "error")
            return False
        except Exception as e:
            self.print_status(f"Import failed: {e}", "error")
            return False
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> Any:
        """Execute knowledge command action."""
        return super().execute(action, action_args, **kwargs)

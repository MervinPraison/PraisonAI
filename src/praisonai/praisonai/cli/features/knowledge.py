"""
Knowledge Handler for CLI.

Provides RAG/vector store management.
Usage: praisonai knowledge add document.pdf
       praisonai knowledge search "query"
"""

import os
from typing import Any, Dict, List
from .base import CommandHandler


class KnowledgeHandler(CommandHandler):
    """
    Handler for knowledge command.
    
    Manages knowledge base for RAG (Retrieval Augmented Generation).
    
    Example:
        praisonai knowledge add document.pdf
        praisonai knowledge add ./docs/
        praisonai knowledge search "How to authenticate?"
        praisonai knowledge list
        praisonai knowledge clear
    """
    
    def __init__(self, verbose: bool = False, workspace: str = None):
        super().__init__(verbose)
        self.workspace = workspace or os.getcwd()
        self._knowledge = None
    
    @property
    def feature_name(self) -> str:
        return "knowledge"
    
    def get_actions(self) -> List[str]:
        return ["add", "search", "list", "clear", "info", "help"]
    
    def get_help_text(self) -> str:
        return """
Knowledge Commands:
  praisonai knowledge add <file|dir>     - Add document(s) to knowledge base
  praisonai knowledge search <query>     - Search knowledge base
  praisonai knowledge list               - List indexed documents
  praisonai knowledge clear              - Clear knowledge base
  praisonai knowledge info               - Show knowledge base info

Options:
  --workspace <path>                     - Workspace directory (default: current)
"""
    
    def _get_knowledge(self):
        """Lazy load Knowledge instance."""
        if self._knowledge is None:
            try:
                from praisonaiagents import Knowledge
                self._knowledge = Knowledge()
            except ImportError:
                self.print_status(
                    "Knowledge requires praisonaiagents. Install with: pip install praisonaiagents",
                    "error"
                )
                return None
        return self._knowledge
    
    def action_add(self, args: List[str], **kwargs) -> bool:
        """
        Add document(s) to knowledge base.
        
        Args:
            args: List containing file/directory paths
            
        Returns:
            True if successful
        """
        if not args:
            self.print_status("Usage: praisonai knowledge add <file|directory>", "error")
            return False
        
        knowledge = self._get_knowledge()
        if not knowledge:
            return False
        
        path = args[0]
        
        # Expand path
        if not os.path.isabs(path):
            path = os.path.join(self.workspace, path)
        
        if not os.path.exists(path):
            self.print_status(f"Path not found: {path}", "error")
            return False
        
        try:
            if os.path.isdir(path):
                # Add all files in directory
                count = 0
                for root, _, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        knowledge.add(file_path)
                        count += 1
                self.print_status(f"✅ Added {count} files from {path}", "success")
            else:
                knowledge.add(path)
                self.print_status(f"✅ Added: {path}", "success")
            return True
        except Exception as e:
            self.print_status(f"Failed to add: {e}", "error")
            return False
    
    def action_search(self, args: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        Search knowledge base.
        
        Args:
            args: List containing search query
            
        Returns:
            List of search results
        """
        if not args:
            self.print_status("Usage: praisonai knowledge search <query>", "error")
            return []
        
        knowledge = self._get_knowledge()
        if not knowledge:
            return []
        
        query = ' '.join(args)
        limit = kwargs.get('limit', 5)
        
        try:
            results = knowledge.search(query, k=limit)
            
            if results:
                self.print_status(f"\n🔍 Search results for '{query}':\n", "info")
                for i, result in enumerate(results, 1):
                    content = str(result)[:200]
                    self.print_status(f"  {i}. {content}...", "info")
            else:
                self.print_status("No results found", "warning")
            
            return results
        except Exception as e:
            self.print_status(f"Search failed: {e}", "error")
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
    
    def action_info(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Show knowledge base info.
        
        Returns:
            Dictionary of info
        """
        knowledge = self._get_knowledge()
        if not knowledge:
            return {}
        
        info = {
            "workspace": self.workspace,
            "type": type(knowledge).__name__
        }
        
        try:
            if hasattr(knowledge, 'get_stats'):
                info.update(knowledge.get_stats())
            if hasattr(knowledge, 'count'):
                info['document_count'] = knowledge.count()
        except Exception:
            pass
        
        self.print_status("\n📊 Knowledge Base Info:", "info")
        for key, value in info.items():
            self.print_status(f"  {key}: {value}", "info")
        
        return info
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> Any:
        """Execute knowledge command action."""
        return super().execute(action, action_args, **kwargs)

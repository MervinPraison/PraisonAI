"""
Mentions Parser for PraisonAI Agents.

Provides @mention syntax support similar to Cursor IDE:
- @file:path/to/file.py - Include file content
- @web:query - Search the web
- @doc:name - Include doc from .praison/docs/
- @rule:name - Include specific rule

Usage:
    from praisonaiagents.tools.mentions import MentionsParser
    
    parser = MentionsParser()
    context, cleaned_prompt = parser.process("@file:main.py explain this code")
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MentionsParser:
    """
    Parse and process @mentions in prompts.
    
    Supports:
    - @file:path - Include file content
    - @web:query - Web search (requires web search tool)
    - @doc:name - Include doc from .praison/docs/
    - @rule:name - Include specific rule
    - @url:https://... - Fetch URL content
    """
    
    # Patterns for different mention types
    PATTERNS = {
        "file": re.compile(r'@file:([^\s]+)'),
        "web": re.compile(r'@web:([^\s]+(?:\s+[^\s@]+)*)'),
        "doc": re.compile(r'@doc:([^\s]+)'),
        "rule": re.compile(r'@rule:([^\s]+)'),
        "url": re.compile(r'@url:(https?://[^\s]+)'),
    }
    
    # Default max file chars: 500K (~125K tokens) - fits GPT-4o (128K), Claude 3.5 (200K)
    DEFAULT_MAX_FILE_CHARS = 500000
    
    def __init__(
        self,
        workspace_path: Optional[str] = None,
        verbose: int = 0,
        max_file_chars: Optional[int] = None
    ):
        """
        Initialize MentionsParser.
        
        Args:
            workspace_path: Path to workspace/project root
            verbose: Verbosity level
            max_file_chars: Maximum characters to include from files.
                           Default: 500000 (500K chars, ~125K tokens).
                           Set to 0 for no limit.
                           Can be overridden via PRAISON_MAX_FILE_CHARS env var.
        """
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()
        self.verbose = verbose
        
        # Configure max file chars: constructor > env var > default
        if max_file_chars is not None:
            self.max_file_chars = max_file_chars
        else:
            env_val = os.environ.get('PRAISON_MAX_FILE_CHARS')
            if env_val is not None:
                self.max_file_chars = int(env_val)
            else:
                self.max_file_chars = self.DEFAULT_MAX_FILE_CHARS
        
        # Lazy-loaded managers
        self._docs_manager = None
        self._rules_manager = None
    
    def _log(self, msg: str, level: int = logging.INFO):
        """Log message if verbose."""
        if self.verbose >= 1:
            logger.log(level, msg)
    
    def _get_docs_manager(self):
        """Lazy load DocsManager."""
        if self._docs_manager is None:
            try:
                from praisonaiagents.memory.docs_manager import DocsManager
                self._docs_manager = DocsManager(workspace_path=str(self.workspace_path))
            except ImportError:
                self._log("DocsManager not available", logging.WARNING)
        return self._docs_manager
    
    def _get_rules_manager(self):
        """Lazy load RulesManager."""
        if self._rules_manager is None:
            try:
                from praisonaiagents.memory.rules_manager import RulesManager
                self._rules_manager = RulesManager(workspace_path=str(self.workspace_path))
            except ImportError:
                self._log("RulesManager not available", logging.WARNING)
        return self._rules_manager
    
    def process(self, prompt: str) -> Tuple[str, str]:
        """
        Process a prompt and extract @mentions.
        
        Args:
            prompt: The input prompt with @mentions
            
        Returns:
            Tuple of (context_string, cleaned_prompt)
        """
        context_parts = []
        cleaned_prompt = prompt
        
        # Process each mention type
        for mention_type, pattern in self.PATTERNS.items():
            matches = pattern.findall(prompt)
            for match in matches:
                context = self._process_mention(mention_type, match)
                if context:
                    context_parts.append(context)
                # Remove the mention from the prompt
                cleaned_prompt = pattern.sub('', cleaned_prompt, count=1)
        
        # Clean up extra whitespace
        cleaned_prompt = ' '.join(cleaned_prompt.split())
        
        # Build context string
        context_string = ""
        if context_parts:
            context_string = "\n\n".join(context_parts) + "\n\n"
        
        return context_string, cleaned_prompt
    
    def _process_mention(self, mention_type: str, value: str) -> Optional[str]:
        """
        Process a single mention.
        
        Args:
            mention_type: Type of mention (file, web, doc, rule, url)
            value: The mention value
            
        Returns:
            Context string or None
        """
        if mention_type == "file":
            return self._process_file_mention(value)
        elif mention_type == "web":
            return self._process_web_mention(value)
        elif mention_type == "doc":
            return self._process_doc_mention(value)
        elif mention_type == "rule":
            return self._process_rule_mention(value)
        elif mention_type == "url":
            return self._process_url_mention(value)
        return None
    
    def _process_file_mention(self, file_path: str) -> Optional[str]:
        """Process @file:path mention."""
        try:
            # Resolve path relative to workspace
            full_path = self.workspace_path / file_path
            if not full_path.exists():
                # Try as absolute path
                full_path = Path(file_path)
            
            if not full_path.exists():
                self._log(f"File not found: {file_path}", logging.WARNING)
                return f"# File: {file_path}\n[File not found]"
            
            content = full_path.read_text(encoding="utf-8")
            
            # Limit content size (0 means no limit)
            if self.max_file_chars > 0 and len(content) > self.max_file_chars:
                original_size = len(content)
                content = content[:self.max_file_chars] + "\n... (truncated)"
                self._log(
                    f"File {file_path} truncated from {original_size:,} to {self.max_file_chars:,} chars. "
                    f"Set PRAISON_MAX_FILE_CHARS=0 for no limit.",
                    logging.WARNING
                )
            
            # Detect language for code fence
            ext = full_path.suffix.lower()
            lang_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".jsx": "jsx",
                ".tsx": "tsx",
                ".java": "java",
                ".cpp": "cpp",
                ".c": "c",
                ".go": "go",
                ".rs": "rust",
                ".rb": "ruby",
                ".php": "php",
                ".swift": "swift",
                ".kt": "kotlin",
                ".md": "markdown",
                ".json": "json",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".xml": "xml",
                ".html": "html",
                ".css": "css",
                ".sql": "sql",
                ".sh": "bash",
            }
            lang = lang_map.get(ext, "")
            
            return f"# File: {file_path}\n```{lang}\n{content}\n```"
            
        except Exception as e:
            self._log(f"Error reading file {file_path}: {e}", logging.ERROR)
            return f"# File: {file_path}\n[Error reading file: {e}]"
    
    def _process_web_mention(self, query: str) -> Optional[str]:
        """Process @web:query mention."""
        try:
            # Try to use web search
            from praisonaiagents.tools import duckduckgo_search
            
            results = duckduckgo_search(query, max_results=3)
            if results:
                return f"# Web Search: {query}\n{results}"
            else:
                return f"# Web Search: {query}\n[No results found]"
                
        except ImportError:
            self._log("Web search not available", logging.WARNING)
            return f"# Web Search: {query}\n[Web search not available. Install with: pip install duckduckgo-search]"
        except Exception as e:
            self._log(f"Error in web search: {e}", logging.ERROR)
            return f"# Web Search: {query}\n[Error: {e}]"
    
    def _process_doc_mention(self, doc_name: str) -> Optional[str]:
        """Process @doc:name mention."""
        docs = self._get_docs_manager()
        if not docs:
            return f"# Doc: {doc_name}\n[DocsManager not available]"
        
        doc = docs.get_doc(doc_name)
        if doc:
            return f"# Doc: {doc.name}\n{doc.content}"
        else:
            return f"# Doc: {doc_name}\n[Doc not found]"
    
    def _process_rule_mention(self, rule_name: str) -> Optional[str]:
        """Process @rule:name mention."""
        rules = self._get_rules_manager()
        if not rules:
            return f"# Rule: {rule_name}\n[RulesManager not available]"
        
        rule = rules.get_rule(rule_name)
        if rule:
            return f"# Rule: {rule.name}\n{rule.content}"
        else:
            return f"# Rule: {rule_name}\n[Rule not found]"
    
    def _process_url_mention(self, url: str) -> Optional[str]:
        """Process @url:https://... mention."""
        try:
            import urllib.request
            
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; PraisonAI/1.0)'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8', errors='ignore')
            
            # Limit content size (0 means no limit)
            if self.max_file_chars > 0 and len(content) > self.max_file_chars:
                content = content[:self.max_file_chars] + "\n... (truncated)"
            
            # Try to extract text from HTML
            if '<html' in content.lower():
                # Simple HTML text extraction
                import re
                # Remove scripts and styles
                content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
                # Remove tags
                content = re.sub(r'<[^>]+>', ' ', content)
                # Clean whitespace
                content = ' '.join(content.split())
            
            return f"# URL: {url}\n{content[:10000]}"
            
        except Exception as e:
            self._log(f"Error fetching URL {url}: {e}", logging.ERROR)
            return f"# URL: {url}\n[Error fetching URL: {e}]"
    
    def extract_mentions(self, prompt: str) -> Dict[str, List[str]]:
        """
        Extract all mentions from a prompt without processing them.
        
        Args:
            prompt: The input prompt
            
        Returns:
            Dict mapping mention types to lists of values
        """
        mentions = {}
        for mention_type, pattern in self.PATTERNS.items():
            matches = pattern.findall(prompt)
            if matches:
                mentions[mention_type] = matches
        return mentions
    
    def has_mentions(self, prompt: str) -> bool:
        """Check if a prompt contains any @mentions."""
        for pattern in self.PATTERNS.values():
            if pattern.search(prompt):
                return True
        return False


def process_mentions(prompt: str, workspace_path: Optional[str] = None) -> Tuple[str, str]:
    """
    Convenience function to process mentions in a prompt.
    
    Args:
        prompt: The input prompt with @mentions
        workspace_path: Optional workspace path
        
    Returns:
        Tuple of (context_string, cleaned_prompt)
    """
    parser = MentionsParser(workspace_path=workspace_path)
    return parser.process(prompt)


# Export
__all__ = ["MentionsParser", "process_mentions"]

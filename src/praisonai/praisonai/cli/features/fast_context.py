"""
Fast Context Handler for CLI.

Provides codebase search capability using FastContext.
Usage: praisonai "Find authentication code" --fast-context ./src
"""

import os
from typing import Any, Dict, Tuple, List
from .base import FlagHandler


class FastContextHandler(FlagHandler):
    """
    Handler for --fast-context flag.
    
    Searches codebase for relevant context before agent execution.
    
    Example:
        praisonai "Find authentication code" --fast-context ./src
        praisonai "Explain the database schema" --fast-context /path/to/project
    """
    
    @property
    def feature_name(self) -> str:
        return "fast_context"
    
    @property
    def flag_name(self) -> str:
        return "fast-context"
    
    @property
    def flag_help(self) -> str:
        return "Path to search for relevant code context"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if FastContext is available."""
        try:
            import importlib.util
            if importlib.util.find_spec("praisonaiagents") is not None:
                return True, ""
            return False, "praisonaiagents not installed"
        except ImportError:
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
    
    def validate_search_path(self, path: str) -> Tuple[bool, str]:
        """
        Validate that the search path exists.
        
        Args:
            path: Path to search directory
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not path:
            return False, "No search path provided"
        
        if not os.path.isdir(path):
            return False, f"Directory not found: {path}"
        
        return True, ""
    
    def search_context(self, query: str, path: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for relevant context in the codebase.
        
        Args:
            query: Search query
            path: Path to search
            **kwargs: Additional search options
            
        Returns:
            List of matching results
        """
        available, msg = self.check_dependencies()
        if not available:
            self.print_status(msg, "error")
            return []
        
        valid, msg = self.validate_search_path(path)
        if not valid:
            self.print_status(msg, "error")
            return []
        
        try:
            from praisonaiagents import FastContext
            
            fc = FastContext(
                path=path,
                model=kwargs.get('model', 'gpt-4o-mini'),
                max_turns=kwargs.get('max_turns', 4),
                parallelism=kwargs.get('parallelism', 8),
                timeout=kwargs.get('timeout', 30.0)
            )
            
            result = fc.search(query)
            
            # Convert to list of dicts
            matches = []
            if hasattr(result, 'files'):
                for file_match in result.files:
                    matches.append({
                        'file': file_match.path,
                        'lines': [(lr.start, lr.end) for lr in file_match.line_ranges],
                        'relevance': getattr(file_match, 'relevance', 1.0)
                    })
            
            self.print_status(f"🔍 Found {len(matches)} relevant files", "success")
            return matches
            
        except Exception as e:
            self.log(f"FastContext search error: {e}", "error")
            return []
    
    def format_context_for_prompt(self, matches: List[Dict[str, Any]], max_chars: int = 10000) -> str:
        """
        Format search results as context for the prompt.
        
        Args:
            matches: List of search results
            max_chars: Maximum characters to include
            
        Returns:
            Formatted context string
        """
        if not matches:
            return ""
        
        context_parts = ["## Relevant Code Context\n"]
        total_chars = 0
        
        for match in matches:
            file_path = match.get('file', '')
            lines = match.get('lines', [])
            
            if not file_path or not os.path.exists(file_path):
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.readlines()
                
                for start, end in lines:
                    snippet = ''.join(content[max(0, start-1):end])
                    
                    if total_chars + len(snippet) > max_chars:
                        break
                    
                    context_parts.append(f"\n### {file_path} (lines {start}-{end})\n```\n{snippet}```\n")
                    total_chars += len(snippet)
                    
            except Exception:
                continue
        
        return '\n'.join(context_parts)
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply fast context configuration.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Search path
            
        Returns:
            Modified configuration
        """
        if flag_value:
            config['fast_context'] = True
            config['fast_context_path'] = flag_value
        return config
    
    def execute(self, query: str = None, path: str = None, **kwargs) -> str:
        """
        Execute fast context search and return formatted context.
        
        Args:
            query: Search query
            path: Search path
            
        Returns:
            Formatted context string
        """
        if not query or not path:
            return ""
        
        matches = self.search_context(query, path, **kwargs)
        return self.format_context_for_prompt(matches)

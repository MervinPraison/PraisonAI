"""
Fast Context Handler for CLI.

Provides codebase search capability using FastContext.
Usage: praisonai "Find authentication code" --fast-context ./src

Fast Context Strategy:
1. Extract search keywords from natural language query using LLM
2. Provide folder tree context to help understand codebase structure
3. Use both file name search AND content search (ripgrep-style)
4. Return relevant code snippets for context
"""

import os
import logging
from typing import Any, Dict, Tuple, List
from .base import FlagHandler

logger = logging.getLogger(__name__)


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
    
    def _count_files_quick(self, path: str, max_count: int = 1000) -> int:
        """Quickly count files in directory, stopping at max_count."""
        count = 0
        ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.cache', 'dist', 'build'}
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')]
            count += len(files)
            if count >= max_count:
                return count
        return count
    
    def _get_folder_tree(self, path: str, max_depth: int = 2) -> str:
        """
        Get a compact folder tree structure for context.
        
        Optimized for large directories:
        - Limits depth to max_depth (default 2)
        - Shows max 10 files per directory
        - Truncates total output to 50 lines
        - Skips common non-code directories
        """
        # Quick check for very large directories
        file_count = self._count_files_quick(path, 500)
        if file_count >= 500:
            # For large directories, reduce depth and show summary
            max_depth = 1
            logger.debug(f"Large directory detected ({file_count}+ files), reducing tree depth")
        
        tree_lines = []
        ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.cache', 'dist', 'build', 'coverage', '.pytest_cache', '.mypy_cache', 'eggs', '*.egg-info'}
        ignore_exts = {'.pyc', '.pyo', '.so', '.o', '.a', '.dylib', '.class', '.jar'}
        total_files = 0
        max_total_files = 100  # Stop after seeing this many files
        
        def walk_tree(current_path, prefix="", depth=0):
            nonlocal total_files
            if depth > max_depth or total_files >= max_total_files:
                return
            
            try:
                entries = sorted(os.listdir(current_path))
            except PermissionError:
                return
            
            dirs = []
            files = []
            for entry in entries:
                full_path = os.path.join(current_path, entry)
                if os.path.isdir(full_path):
                    if entry not in ignore_dirs and not entry.startswith('.'):
                        dirs.append(entry)
                else:
                    ext = os.path.splitext(entry)[1]
                    if ext not in ignore_exts and not entry.startswith('.'):
                        files.append(entry)
            
            # Limit directories shown at each level
            dirs_to_show = dirs[:15]
            for i, d in enumerate(dirs_to_show):
                is_last = (i == len(dirs_to_show) - 1) and not files
                tree_lines.append(f"{prefix}{'└── ' if is_last else '├── '}{d}/")
                walk_tree(os.path.join(current_path, d), 
                         prefix + ('    ' if is_last else '│   '), depth + 1)
            if len(dirs) > 15:
                tree_lines.append(f"{prefix}    ... and {len(dirs) - 15} more directories")
            
            # Limit files shown
            files_to_show = files[:10]
            total_files += len(files)
            for i, f in enumerate(files_to_show):
                is_last = i == len(files_to_show) - 1
                tree_lines.append(f"{prefix}{'└── ' if is_last else '├── '}{f}")
            if len(files) > 10:
                tree_lines.append(f"{prefix}    ... and {len(files) - 10} more files")
        
        tree_lines.append(os.path.basename(path) + "/")
        walk_tree(path)
        return "\n".join(tree_lines[:50])  # Limit total lines
    
    def _extract_keywords(self, query: str, folder_tree: str) -> List[str]:
        """Extract search keywords from natural language query using LLM."""
        try:
            from praisonaiagents import Agent
            
            extractor = Agent(
                name="KeywordExtractor",
                role="Search Query Analyzer",
                goal="Extract file search keywords from natural language",
                backstory="Expert at understanding code search queries",
                llm="gpt-4o-mini", output="minimal"
            )
            
            prompt = f"""Given this folder structure:
{folder_tree}

And this search query: "{query}"

Extract 1-5 specific keywords/patterns to search for in file names and content.
Return ONLY the keywords, one per line, no explanations.
Focus on: file names, function names, class names, variable names that might match.
If the query mentions a folder name that exists, include files from that folder."""

            response = extractor.chat(prompt, stream=False)
            keywords = [k.strip() for k in str(response).strip().split('\n') if k.strip()]
            logger.debug(f"Extracted keywords: {keywords}")
            return keywords[:5]  # Limit to 5 keywords
        except Exception as e:
            logger.debug(f"Keyword extraction failed: {e}")
            # Fallback: extract words from query
            return [w for w in query.split() if len(w) > 2][:3]
    
    def _search_files_by_name(self, path: str, keywords: List[str]) -> List[Dict[str, Any]]:
        """Search for files matching keywords in their names."""
        matches = []
        path = os.path.abspath(path)
        
        ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for filename in files:
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, path)
                
                # Check if any keyword matches filename or path
                for kw in keywords:
                    kw_lower = kw.lower()
                    if kw_lower in filename.lower() or kw_lower in rel_path.lower():
                        matches.append({
                            'file': rel_path,
                            'lines': [(1, 50)],  # First 50 lines
                            'relevance': 1.0,
                            'match_type': 'filename'
                        })
                        break
        
        return matches[:20]  # Limit results
    
    def _search_files_by_content(self, path: str, keywords: List[str]) -> List[Dict[str, Any]]:
        """Search for files containing keywords in content."""
        matches = []
        path = os.path.abspath(path)
        
        ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}
        code_exts = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.rb', '.sh', '.yaml', '.yml', '.json', '.md', '.txt'}
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for filename in files:
                ext = os.path.splitext(filename)[1]
                if ext not in code_exts:
                    continue
                    
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, path)
                
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(50000)  # Read first 50KB
                    
                    content_lower = content.lower()
                    for kw in keywords:
                        if kw.lower() in content_lower:
                            # Find line numbers with matches
                            lines = content.split('\n')
                            match_lines = []
                            for i, line in enumerate(lines[:200], 1):  # Check first 200 lines
                                if kw.lower() in line.lower():
                                    match_lines.append((max(1, i-2), min(len(lines), i+2)))
                            
                            if match_lines:
                                matches.append({
                                    'file': rel_path,
                                    'lines': match_lines[:5],  # Limit line ranges
                                    'relevance': 0.8,
                                    'match_type': 'content'
                                })
                            break
                except Exception:
                    continue
        
        return matches[:15]  # Limit results
    
    def search_context(self, query: str, path: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for relevant context in the codebase.
        
        Uses a smart multi-step approach:
        1. Get folder tree structure
        2. Use LLM to extract search keywords from query
        3. Search by filename AND content
        4. Return combined results
        
        Args:
            query: Natural language search query
            path: Path to search
            **kwargs: Additional search options
                - use_llm_keywords: Use LLM to extract keywords (default: True)
            
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
            use_llm_keywords = kwargs.get('use_llm_keywords', True)
            
            # Step 1: Get folder tree for context
            logger.debug(f"Getting folder tree for: {path}")
            folder_tree = self._get_folder_tree(path)
            logger.debug(f"Folder tree:\n{folder_tree}")
            
            # Step 2: Extract keywords
            if use_llm_keywords:
                logger.debug(f"Extracting keywords from query: {query}")
                keywords = self._extract_keywords(query, folder_tree)
            else:
                keywords = [w for w in query.split() if len(w) > 2][:3]
            
            logger.debug(f"Search keywords: {keywords}")
            
            if not keywords:
                self.print_status("Could not extract search keywords", "warning")
                return []
            
            # Step 3: Search by filename
            logger.debug("Searching by filename...")
            filename_matches = self._search_files_by_name(path, keywords)
            logger.debug(f"Found {len(filename_matches)} filename matches")
            
            # Step 4: Search by content
            logger.debug("Searching by content...")
            content_matches = self._search_files_by_content(path, keywords)
            logger.debug(f"Found {len(content_matches)} content matches")
            
            # Combine and deduplicate
            seen_files = set()
            matches = []
            
            for m in filename_matches + content_matches:
                if m['file'] not in seen_files:
                    seen_files.add(m['file'])
                    matches.append(m)
            
            self.print_status(f"🔍 Found {len(matches)} relevant files", "success")
            return matches
            
        except Exception as e:
            logger.error(f"FastContext search error: {e}")
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
            # Note: fast_context params removed from Agent - FastContext is now accessed
            # via the context module directly. This flag enables CLI-level fast context.
            config['_fast_context_path'] = flag_value  # Internal CLI flag
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

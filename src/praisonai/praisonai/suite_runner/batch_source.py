"""
Batch Source - Adapter for running local Python files with PraisonAI imports.

Discovers and prepares Python files in the current directory (or specified path)
that contain imports from praisonaiagents or praisonai packages.

This is designed for quick debugging - running multiple local scripts at once.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .models import RunItem
from .discovery import FileDiscovery, get_pythonpath_for_dev


# Import detection patterns - matches 'from praisonai...' or 'import praisonai...'
PRAISONAI_IMPORT_PATTERN = re.compile(
    r'^(?:from|import)\s+praisonai(?:agents)?\b',
    re.MULTILINE
)

# Agent-centric detection patterns (reused from examples_source)
AGENT_PATTERN = re.compile(r'\bAgent\s*\(')
AGENTS_PATTERN = re.compile(r'\b(?:Agents|PraisonAIAgents)\s*\(')
WORKFLOW_PATTERN = re.compile(r'\bWorkflow\s*\(')

# Directive parsing regex (reused from examples_source)
DIRECTIVE_PATTERN = re.compile(r'^#\s*praisonai:\s*(\w+)=(.+)$', re.MULTILINE)
INPUT_PATTERN = re.compile(r'\binput\s*\(')

# Test file patterns to exclude by default
TEST_FILE_PATTERNS = {'test_*.py', '*_test.py', 'conftest.py'}

# Server detection patterns - scripts that start long-running servers
SERVER_PATTERNS = [
    re.compile(r'uvicorn\.run\s*\('),           # uvicorn.run()
    re.compile(r'\.launch\s*\('),                # agent.launch(), demo.launch()
    re.compile(r'app\.run\s*\('),                # Flask app.run()
    re.compile(r'^\s*import\s+streamlit\b', re.MULTILINE),  # import streamlit
    re.compile(r'^\s*from\s+streamlit\b', re.MULTILINE),    # from streamlit import
    re.compile(r'^\s*import\s+gradio\b', re.MULTILINE),     # import gradio
    re.compile(r'^\s*from\s+gradio\b', re.MULTILINE),       # from gradio import
    re.compile(r'FastAPI\s*\('),                 # FastAPI()
    re.compile(r'Flask\s*\('),                   # Flask()
    re.compile(r'\.serve\s*\('),                 # server.serve()
    re.compile(r'mcp\.run\s*\('),                # mcp.run()
    re.compile(r'server\.run\s*\('),             # server.run()
]


class BatchSource:
    """
    Discovers and prepares local Python files with PraisonAI imports.
    
    Unlike ExamplesSource (for repo examples) or DocsSource (for docs),
    this source is designed for quick local debugging of user scripts.
    
    Only files containing 'from praisonaiagents' or 'from praisonai'
    are included. Test files are excluded by default.
    
    Parses directives from comments:
    - # praisonai: skip=true
    - # praisonai: timeout=120
    - # praisonai: require_env=KEY1,KEY2
    - # praisonai: xfail=reason
    """
    
    def __init__(
        self,
        root: Optional[Path] = None,
        recursive: bool = False,
        depth: Optional[int] = None,
        exclude_tests: bool = True,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        exclude_servers: bool = True,
        server_only: bool = False,
        filter_type: Optional[str] = None,
    ):
        """
        Initialize batch source.
        
        Args:
            root: Root directory to search (default: current directory).
            recursive: Whether to search subdirectories.
            depth: Maximum recursion depth (None = unlimited when recursive).
            exclude_tests: Whether to exclude test files (test_*.py, *_test.py).
            include_patterns: Glob patterns to include.
            exclude_patterns: Glob patterns to exclude.
            groups: Specific groups (subdirs) to include.
            exclude_servers: Whether to exclude server scripts (default: True).
            server_only: Only include server scripts (for --server mode).
            filter_type: Filter by agent type ('agent', 'agents', 'workflow').
        """
        self.root = Path(root).resolve() if root else Path.cwd().resolve()
        self.recursive = recursive
        self.depth = depth
        self.exclude_tests = exclude_tests
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns or []
        self.groups = groups
        self.exclude_servers = exclude_servers
        self.server_only = server_only
        self.filter_type = filter_type
        
        # Add test exclusions if enabled
        if exclude_tests:
            self.exclude_patterns = list(self.exclude_patterns) + [
                'test_*.py', '*_test.py', 'conftest.py'
            ]
        
        self._discovery = FileDiscovery(
            root=self.root,
            extensions=['.py'],
            include_patterns=include_patterns,
            exclude_patterns=self.exclude_patterns,
            ignore_underscore=True,
        )
    
    def _has_praisonai_import(self, content: str) -> bool:
        """
        Check if file content contains PraisonAI imports.
        
        Args:
            content: File content to check.
            
        Returns:
            True if file contains 'from praisonai...' or 'import praisonai...'.
        """
        # Check each line to avoid matching commented imports
        for line in content.split('\n'):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith('#'):
                continue
            # Check for import
            if PRAISONAI_IMPORT_PATTERN.match(stripped):
                return True
        return False
    
    def _is_server_script(self, content: str) -> bool:
        """
        Check if file content contains server patterns that would hang.
        
        Detects: uvicorn.run, .launch(), app.run, streamlit, gradio, FastAPI, Flask, etc.
        
        Args:
            content: File content to check.
            
        Returns:
            True if file contains server patterns.
        """
        for pattern in SERVER_PATTERNS:
            if pattern.search(content):
                return True
        return False
    
    def _get_files_at_depth(self, max_depth: Optional[int] = None) -> List[Path]:
        """
        Get files respecting depth limit.
        
        Args:
            max_depth: Maximum depth (0 = root only, 1 = root + immediate subdirs, etc.)
            
        Returns:
            List of file paths.
        """
        if not self.recursive:
            # Non-recursive: only files in root directory
            files = []
            for path in self.root.glob('*.py'):
                if path.is_file() and not path.name.startswith('_'):
                    # Apply exclude patterns
                    if self.exclude_patterns:
                        import fnmatch
                        if any(fnmatch.fnmatch(path.name, p) for p in self.exclude_patterns):
                            continue
                    files.append(path)
            return sorted(files)
        
        # Recursive with optional depth limit
        all_files = self._discovery.discover()
        
        if max_depth is None:
            return all_files
        
        # Filter by depth
        filtered = []
        for path in all_files:
            rel_path = path.relative_to(self.root)
            # Depth is number of parent directories
            depth = len(rel_path.parts) - 1  # -1 because last part is filename
            if depth <= max_depth:
                filtered.append(path)
        
        return filtered
    
    def discover(self) -> List[RunItem]:
        """
        Discover all Python files with PraisonAI imports.
        
        Returns:
            List of RunItem objects for files that contain PraisonAI imports.
        """
        files = self._get_files_at_depth(self.depth)
        
        # Filter by groups if specified
        if self.groups:
            filtered_files = []
            for path in files:
                group = self._get_group_for_path(path)
                if group in self.groups:
                    filtered_files.append(path)
            files = filtered_files
        
        items = []
        for path in files:
            # Read file content
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            
            # Check for PraisonAI imports
            if not self._has_praisonai_import(content):
                continue
            
            # Create RunItem
            item = self._create_item(path, content)
            
            # Apply server filtering
            if self.server_only:
                # Only include server scripts
                if not item.is_server:
                    continue
            elif self.exclude_servers:
                # Exclude server scripts (default behavior)
                if item.is_server:
                    continue
            
            # Apply agent type filtering
            if self.filter_type:
                if self.filter_type == "agent" and not item.uses_agent:
                    continue
                elif self.filter_type == "agents" and not item.uses_agents:
                    continue
                elif self.filter_type == "workflow" and not item.uses_workflow:
                    continue
            
            items.append(item)
        
        return items
    
    def _get_group_for_path(self, path: Path) -> str:
        """Get group name for a file path."""
        try:
            rel_path = path.relative_to(self.root)
            if len(rel_path.parts) > 1:
                return rel_path.parts[0]
            return "root"
        except ValueError:
            return "unknown"
    
    def _create_item(self, path: Path, content: str) -> RunItem:
        """Create RunItem from file."""
        group = self._get_group_for_path(path)
        rel_path = path.relative_to(self.root).as_posix()
        item_id = rel_path.replace('/', '__').replace('.py', '')
        
        # Parse directives from first 30 lines
        lines = content.split('\n')[:30]
        header = '\n'.join(lines)
        
        skip = False
        skip_reason = None
        timeout = None
        require_env = []
        xfail = None
        
        for match in DIRECTIVE_PATTERN.finditer(header):
            key, value = match.group(1), match.group(2).strip()
            
            if key == 'skip':
                skip = value.lower() in ('true', '1', 'yes')
                if skip:
                    skip_reason = "skip=true directive"
            elif key == 'timeout':
                try:
                    timeout = int(value)
                except ValueError:
                    pass
            elif key == 'require_env':
                require_env = [k.strip() for k in value.split(',') if k.strip()]
            elif key == 'xfail':
                xfail = value
        
        # Detect interactive input() calls
        is_interactive = bool(INPUT_PATTERN.search(content))
        if is_interactive and not skip:
            skip = True
            skip_reason = "Interactive script (contains input())"
        
        # Detect agent-centric usage
        uses_agent = bool(AGENT_PATTERN.search(content))
        uses_agents = bool(AGENTS_PATTERN.search(content))
        uses_workflow = bool(WORKFLOW_PATTERN.search(content))
        
        # Detect server scripts
        is_server = self._is_server_script(content)
        
        # Determine runnable status
        runnable = not skip
        runnable_decision = "runnable" if runnable else (skip_reason or "skipped")
        
        return RunItem(
            item_id=item_id,
            suite="batch",
            group=group,
            source_path=path,
            block_index=0,
            language="python",
            code=content,
            script_path=path,  # Run directly
            runnable=runnable,
            runnable_decision=runnable_decision,
            skip=skip,
            skip_reason=skip_reason,
            timeout=timeout,
            require_env=require_env,
            xfail=xfail,
            is_interactive=is_interactive,
            uses_agent=uses_agent,
            uses_agents=uses_agents,
            uses_workflow=uses_workflow,
            is_server=is_server,
        )
    
    def get_groups(self) -> List[str]:
        """Get available groups (directories containing matching files)."""
        items = self.discover()
        groups = set(item.group for item in items)
        return sorted(groups)
    
    def get_pythonpath(self) -> List[str]:
        """Get PYTHONPATH additions for dev mode."""
        return get_pythonpath_for_dev(self.root)

"""
Docs Source - Adapter for docs code execution suite.

Extracts and prepares Python code blocks from Markdown/MDX documentation.
Uses the shared suite_runner engine.
"""

from __future__ import annotations

import re
import tempfile
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple

from .models import RunItem
from .discovery import FileDiscovery, get_pythonpath_for_dev


# Patterns for fence detection
FENCE_START_PATTERN = re.compile(r'^(\s*)(`{3,}|~{3,})(\w*)\s*(.*)$')

# Directive pattern for HTML comments
DIRECTIVE_PATTERN = re.compile(
    r'<!--\s*praisonai:\s*([^>]+)\s*-->',
    re.IGNORECASE
)
DIRECTIVE_KV_PATTERN = re.compile(r'(\w+)=([^\s]+)')

# Interactive detection
INPUT_PATTERN = re.compile(r'\binput\s*\(|\bgetpass\s*\.')

# Import detection
IMPORT_PATTERN = re.compile(r'^(?:from\s+\S+\s+)?import\s+', re.MULTILINE)

# Terminal action detection
TERMINAL_ACTIONS = [
    r'\.start\s*\(',
    r'\.run\s*\(',
    r'\.chat\s*\(',
    r'\bprint\s*\(',
    r'asyncio\.run\s*\(',
    r'if\s+__name__\s*==',
    r'\.execute\s*\(',
    r'\.main\s*\(',
]
TERMINAL_PATTERN = re.compile('|'.join(TERMINAL_ACTIONS))

# Agent-centric detection patterns
AGENT_PATTERN = re.compile(r'\bAgent\s*\(')
AGENTS_PATTERN = re.compile(r'\b(?:Agents|PraisonAIAgents)\s*\(')
WORKFLOW_PATTERN = re.compile(r'\bWorkflow\s*\(')


class DocsSource:
    """
    Extracts and prepares Python code blocks from documentation.
    
    Parses directives from HTML comments:
    - <!-- praisonai: runnable=true -->
    - <!-- praisonai: skip=true -->
    - <!-- praisonai: timeout=120 -->
    - <!-- praisonai: require_env=KEY1,KEY2 -->
    """
    
    def __init__(
        self,
        root: Path,
        languages: Optional[List[str]] = None,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        folders: Optional[List[str]] = None,
        exclude_groups: Optional[List[str]] = None,
        workspace_dir: Optional[Path] = None,
    ):
        """
        Initialize docs source.
        
        Args:
            root: Root documentation directory.
            languages: Languages to extract (default: ['python']).
            include_patterns: Glob patterns to include.
            exclude_patterns: Glob patterns to exclude.
            groups: Specific groups (top-level subdirs) to include.
            folders: Specific folders (nested paths like 'examples/agent-recipes').
            exclude_groups: Groups to exclude (e.g., ['js'] to skip JavaScript docs).
            workspace_dir: Directory for extracted scripts.
        """
        self.root = Path(root).resolve()
        self.languages = languages or ['python']
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.groups = groups
        self.folders = folders
        self.exclude_groups = exclude_groups
        
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir)
        else:
            self.workspace_dir = Path(tempfile.mkdtemp(prefix="praisonai_docs_"))
        
        self._discovery = FileDiscovery(
            root=self.root,
            extensions=['.md', '.mdx'],
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            ignore_underscore=False,
        )
    
    def discover(self) -> List[RunItem]:
        """
        Discover all code blocks and create RunItems.
        
        Returns:
            List of RunItem objects.
        """
        # Start with files filtered by folders (nested paths) or groups (top-level)
        if self.folders:
            files = self._discovery.discover_by_folder(self.folders)
        elif self.groups:
            grouped = self._discovery.discover_by_group(self.groups)
            files = []
            for group_files in grouped.values():
                files.extend(group_files)
            files = sorted(files, key=lambda p: p.relative_to(self.root).as_posix())
        else:
            files = self._discovery.discover()
        
        # Filter out excluded groups
        if self.exclude_groups:
            filtered_files = []
            for f in files:
                group = FileDiscovery.get_group_for_path(f, self.root)
                if group not in self.exclude_groups:
                    filtered_files.append(f)
            files = filtered_files
        
        items = []
        for doc_path in files:
            blocks = self._extract_blocks(doc_path)
            items.extend(blocks)
        
        return items
    
    def _extract_blocks(self, doc_path: Path) -> List[RunItem]:
        """Extract code blocks from a document."""
        try:
            content = doc_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return []
        
        group = FileDiscovery.get_group_for_path(doc_path, self.root)
        blocks = []
        lines = content.split('\n')
        
        i = 0
        block_index = 0
        
        while i < len(lines):
            line = lines[i]
            match = FENCE_START_PATTERN.match(line)
            
            if match:
                indent = match.group(1)
                fence = match.group(2)
                language = match.group(3) or ''
                title = match.group(4).strip() if match.group(4) else None
                
                # Find closing fence
                code_lines = []
                fence_start_line = i + 1  # 1-indexed
                j = i + 1
                
                while j < len(lines):
                    close_line = lines[j]
                    # Check if this is the closing fence
                    if close_line.strip() == fence or (
                        close_line.startswith(indent) and 
                        close_line[len(indent):].startswith(fence) and
                        close_line[len(indent):].strip() == fence
                    ):
                        break
                    code_lines.append(close_line)
                    j += 1
                
                if j < len(lines):  # Found closing fence
                    code_content = '\n'.join(code_lines)
                    code_start = fence_start_line + 1
                    code_end = code_start + len(code_lines) - 1 if code_lines else code_start
                    
                    # Check if language matches target
                    if language.lower() in [lang.lower() for lang in self.languages]:
                        # Look for directive in previous lines
                        directive = self._parse_directive(lines, i)
                        
                        # Create item
                        item = self._create_item(
                            doc_path=doc_path,
                            group=group,
                            block_index=block_index,
                            language=language.lower(),
                            code=code_content,
                            line_start=code_start,
                            line_end=code_end,
                            title=title,
                            directive=directive,
                        )
                        blocks.append(item)
                        block_index += 1
                    
                    i = j + 1
                    continue
            
            i += 1
        
        return blocks
    
    def _parse_directive(self, lines: List[str], fence_line: int) -> dict:
        """Parse directive from lines before fence."""
        directive = {
            'runnable': None,
            'skip': False,
            'timeout': None,
            'require_env': [],
        }
        
        # Check up to 5 lines before
        start = max(0, fence_line - 5)
        pre_text = '\n'.join(lines[start:fence_line])
        
        match = DIRECTIVE_PATTERN.search(pre_text)
        if match:
            directive_text = match.group(1)
            for kv_match in DIRECTIVE_KV_PATTERN.finditer(directive_text):
                key, value = kv_match.group(1).lower(), kv_match.group(2)
                
                if key == 'runnable':
                    directive['runnable'] = value.lower() in ('true', '1', 'yes')
                elif key == 'skip':
                    directive['skip'] = value.lower() in ('true', '1', 'yes')
                elif key == 'timeout':
                    try:
                        directive['timeout'] = int(value)
                    except ValueError:
                        pass
                elif key == 'require_env':
                    directive['require_env'] = [e.strip() for e in value.split(',') if e.strip()]
        
        return directive
    
    def _create_item(
        self,
        doc_path: Path,
        group: str,
        block_index: int,
        language: str,
        code: str,
        line_start: int,
        line_end: int,
        title: Optional[str],
        directive: dict,
    ) -> RunItem:
        """Create RunItem from extracted code block."""
        rel_path = doc_path.relative_to(self.root).as_posix()
        item_id = f"{rel_path.replace('/', '__').replace('.mdx', '').replace('.md', '')}__{block_index}"
        
        # Dedent code for MDX indentation
        dedented_code = textwrap.dedent(code)
        
        # Classify runnable status
        runnable, runnable_decision = self._classify(dedented_code, directive)
        
        # Check for interactive
        is_interactive = bool(INPUT_PATTERN.search(dedented_code))
        if is_interactive and runnable:
            runnable = False
            runnable_decision = "interactive_input"
        
        # Handle directive skip
        skip = directive.get('skip', False)
        skip_reason = None
        if skip:
            runnable = False
            runnable_decision = "directive_skip"
            skip_reason = "Directive skip"
        
        # Detect agent-centric usage
        uses_agent = bool(AGENT_PATTERN.search(dedented_code))
        uses_agents = bool(AGENTS_PATTERN.search(dedented_code))
        uses_workflow = bool(WORKFLOW_PATTERN.search(dedented_code))
        
        # Write script to workspace
        script_path = None
        if runnable:
            script_path = self._write_script(item_id, dedented_code)
        
        return RunItem(
            item_id=item_id,
            suite="docs",
            group=group,
            source_path=doc_path,
            block_index=block_index,
            language=language,
            line_start=line_start,
            line_end=line_end,
            code=dedented_code,
            script_path=script_path,
            runnable=runnable,
            runnable_decision=runnable_decision,
            skip=skip,
            skip_reason=skip_reason,
            timeout=directive.get('timeout'),
            require_env=directive.get('require_env', []),
            is_interactive=is_interactive,
            title=title,
            uses_agent=uses_agent,
            uses_agents=uses_agents,
            uses_workflow=uses_workflow,
        )
    
    def _classify(self, code: str, directive: dict) -> Tuple[bool, str]:
        """
        Classify if code block is runnable.
        
        Returns:
            (is_runnable, reason)
        """
        # Directive override
        if directive.get('runnable') is True:
            return True, "directive_runnable"
        if directive.get('runnable') is False:
            return False, "directive_not_runnable"
        
        # Too short
        lines = [line for line in code.strip().split('\n') if line.strip()]
        if len(lines) < 2:
            return False, "too_short"
        
        # Check for imports
        has_import = bool(IMPORT_PATTERN.search(code))
        
        # Check for terminal action
        has_terminal = bool(TERMINAL_PATTERN.search(code))
        
        # Heuristic: needs both import and terminal action
        if has_import and has_terminal:
            return True, "heuristic_standalone"
        
        if not has_import:
            return False, "no_import_partial"
        
        if not has_terminal:
            return False, "no_terminal_action_partial"
        
        return False, "partial"
    
    def _write_script(self, item_id: str, code: str) -> Path:
        """Write code to workspace as executable script."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Sanitize filename
        safe_id = item_id.replace('/', '_').replace('\\', '_')
        script_path = self.workspace_dir / f"{safe_id}.py"
        
        script_path.write_text(code, encoding='utf-8')
        return script_path
    
    def get_groups(self) -> List[str]:
        """Get available groups (top-level directories)."""
        return self._discovery.get_groups()
    
    def get_folders(self, max_depth: int = 3) -> List[str]:
        """Get available folders (including nested paths)."""
        return self._discovery.get_folders(max_depth)
    
    def get_pythonpath(self) -> List[str]:
        """Get PYTHONPATH additions for dev mode."""
        return get_pythonpath_for_dev(self.root)

"""
CLI Docs Source - Extracts CLI commands from documentation for validation.

Discovers and extracts praisonai CLI commands from bash code blocks
in Markdown/MDX documentation files.
"""

from __future__ import annotations

import re
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Set

from .models import RunItem
from .discovery import FileDiscovery


# Pattern to match bash/shell code blocks
BASH_FENCE_PATTERN = re.compile(
    r'^```(?:bash|shell|sh|zsh|console)\s*\n(.*?)^```',
    re.MULTILINE | re.DOTALL
)

# Pattern to extract praisonai commands (handles multi-line with \)
PRAISONAI_CMD_PATTERN = re.compile(
    r'^(?:#\s*)?(praisonai\s+[^\n\\]+(?:\\\n[^\n]+)*)',
    re.MULTILINE
)

# Pattern to detect help-only commands (just --help)
HELP_ONLY_PATTERN = re.compile(r'--help\s*$')

# Pattern to detect commands with placeholders that can't be run
PLACEHOLDER_PATTERNS = [
    re.compile(r'<[^>]+>'),  # <placeholder>
    re.compile(r'\[OPTIONS\]'),  # [OPTIONS]
    re.compile(r'\[ARGS\]'),  # [ARGS]
    re.compile(r'\[PROMPT\]'),  # [PROMPT]
    re.compile(r'\[COMMAND\]'),  # [COMMAND]
    re.compile(r'your[-_]?'),  # your_api_key, your-file
    re.compile(r'path/to/'),  # path/to/file
    re.compile(r'example\.com'),  # example.com
]

# Commands that are safe to run with --help
SAFE_HELP_COMMANDS = {
    'chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research',
    'memory', 'rules', 'workflow', 'hooks', 'knowledge', 'session', 'tools',
    'todo', 'docs', 'mcp', 'commit', 'serve', 'schedule', 'skills', 'profile',
    'eval', 'agents', 'run', 'thinking', 'compaction', 'output', 'deploy',
    'templates', 'recipe', 'endpoints', 'batch', 'examples', 'test',
    'config', 'traces', 'env', 'completion', 'version', 'debug', 'lsp',
    'diag', 'doctor', 'acp', 'tui', 'queue', 'benchmark', 'registry',
    'package', 'standardise', 'standardize', 'background', 'checkpoint',
}


class CLIDocsSource:
    """
    Extracts CLI commands from documentation for validation testing.
    
    Parses bash code blocks in .md/.mdx files and extracts praisonai commands.
    Commands are validated by running them with --help to ensure they exist.
    """
    
    def __init__(
        self,
        root: Path,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        help_only: bool = True,
    ):
        """
        Initialize CLI docs source.
        
        Args:
            root: Root documentation directory.
            include_patterns: Glob patterns to include.
            exclude_patterns: Glob patterns to exclude.
            groups: Specific groups (subdirs) to include.
            help_only: If True, only test commands with --help (safe mode).
        """
        self.root = Path(root).resolve()
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.groups = groups
        self.help_only = help_only
        
        self._discovery = FileDiscovery(
            root=self.root,
            extensions=['.md', '.mdx'],
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
        )
    
    def discover(self) -> List[RunItem]:
        """
        Discover all CLI commands from documentation.
        
        Returns:
            List of RunItem objects for each unique CLI command.
        """
        items = []
        seen_commands: Set[str] = set()
        
        for doc_path in self._discovery.discover():
            # Filter by group if specified
            group = self._get_group(doc_path)
            if self.groups and group not in self.groups:
                continue
            
            # Extract commands from this file
            file_items = self._extract_commands(doc_path, group)
            
            # Deduplicate commands
            for item in file_items:
                cmd_key = self._normalize_command(item.code)
                if cmd_key not in seen_commands:
                    seen_commands.add(cmd_key)
                    items.append(item)
        
        return items
    
    def _get_group(self, path: Path) -> str:
        """Get group name from path (top-level directory under root)."""
        try:
            rel = path.relative_to(self.root)
            parts = rel.parts
            if len(parts) > 1:
                return parts[0]
            return "root"
        except ValueError:
            return "root"
    
    def _normalize_command(self, cmd: str) -> str:
        """Normalize command for deduplication."""
        # Remove extra whitespace and normalize
        cmd = ' '.join(cmd.split())
        # Remove --help suffix for dedup purposes
        cmd = re.sub(r'\s+--help\s*$', '', cmd)
        return cmd
    
    def _extract_commands(self, doc_path: Path, group: str) -> List[RunItem]:
        """Extract CLI commands from a documentation file."""
        items = []
        
        try:
            content = doc_path.read_text(encoding='utf-8')
        except Exception:
            return items
        
        # Find all bash code blocks
        for match in BASH_FENCE_PATTERN.finditer(content):
            block_content = match.group(1)
            block_start = content[:match.start()].count('\n') + 1
            
            # Extract praisonai commands from block
            for cmd_match in PRAISONAI_CMD_PATTERN.finditer(block_content):
                raw_cmd = cmd_match.group(1)
                
                # Clean up multi-line commands
                cmd = self._clean_command(raw_cmd)
                
                if not cmd or not cmd.startswith('praisonai'):
                    continue
                
                # Determine if command is runnable
                runnable, decision = self._is_runnable(cmd)
                
                # Create test command (add --help for safe testing)
                test_cmd = self._create_test_command(cmd)
                
                # Generate unique ID
                cmd_line = block_start + block_content[:cmd_match.start()].count('\n')
                item_id = self._generate_id(doc_path, cmd, cmd_line)
                
                item = RunItem(
                    item_id=item_id,
                    suite='cli-docs',
                    group=group,
                    source_path=doc_path,
                    block_index=cmd_line,
                    language='bash',
                    code=cmd,
                    script_path=None,  # CLI commands don't need script files
                    runnable=runnable,
                    runnable_decision=decision,
                    skip=not runnable,
                    skip_reason=decision if not runnable else None,
                    line_start=cmd_line,
                    line_end=cmd_line,
                    title=test_cmd,  # Store test command in title field
                )
                items.append(item)
        
        return items
    
    def _clean_command(self, cmd: str) -> str:
        """Clean up a command string."""
        # Remove line continuations
        cmd = re.sub(r'\\\n\s*', ' ', cmd)
        # Remove comments at end
        cmd = re.sub(r'\s*#.*$', '', cmd)
        # Normalize whitespace
        cmd = ' '.join(cmd.split())
        return cmd.strip()
    
    def _is_runnable(self, cmd: str) -> tuple:
        """
        Determine if a command is runnable for testing.
        
        Returns:
            Tuple of (is_runnable, decision_reason)
        """
        # Check for placeholders
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(cmd):
                return False, f"Contains placeholder: {pattern.pattern}"
        
        # Extract base command (praisonai <subcommand>)
        parts = cmd.split()
        if len(parts) < 2:
            return False, "No subcommand"
        
        subcommand = parts[1]
        
        # Check if it's a known safe command
        if subcommand in SAFE_HELP_COMMANDS:
            return True, "Known safe command"
        
        # Check for file arguments that don't exist
        if subcommand.endswith('.yaml') or subcommand.endswith('.py'):
            return False, "File argument (may not exist)"
        
        # Check for quoted prompts (these are actual executions)
        if '"' in cmd or "'" in cmd:
            # These would actually run the AI - skip unless help_only is False
            if self.help_only:
                return False, "Contains prompt (would execute AI)"
        
        return True, "Runnable"
    
    def _create_test_command(self, cmd: str) -> str:
        """Create a safe test command (typically with --help)."""
        # If already has --help, use as-is
        if '--help' in cmd:
            return cmd
        
        # Extract base command without arguments
        parts = cmd.split()
        if len(parts) >= 2:
            # praisonai <subcommand> --help
            base_parts = [parts[0], parts[1]]
            
            # Handle nested subcommands (e.g., praisonai batch list)
            if len(parts) >= 3 and not parts[2].startswith('-'):
                # Check if third part looks like a subcommand
                if parts[2] in ('list', 'run', 'stats', 'report', 'show', 'add', 
                               'delete', 'create', 'update', 'get', 'set'):
                    base_parts.append(parts[2])
            
            return ' '.join(base_parts) + ' --help'
        
        return cmd + ' --help'
    
    def _generate_id(self, path: Path, cmd: str, line: int) -> str:
        """Generate unique ID for a command."""
        rel_path = path.relative_to(self.root).as_posix()
        # Hash the command for uniqueness
        cmd_hash = hashlib.md5(cmd.encode()).hexdigest()[:8]
        return f"{rel_path.replace('/', '__').replace('.mdx', '').replace('.md', '')}__{line}__{cmd_hash}"
    
    def get_groups(self) -> List[str]:
        """Get all available groups."""
        groups = set()
        for doc_path in self._discovery.discover():
            groups.add(self._get_group(doc_path))
        return sorted(groups)
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about discovered commands."""
        items = self.discover()
        
        stats = {
            'total': len(items),
            'runnable': sum(1 for i in items if i.runnable),
            'skipped': sum(1 for i in items if i.skip),
            'by_group': {},
        }
        
        for item in items:
            if item.group not in stats['by_group']:
                stats['by_group'][item.group] = {'total': 0, 'runnable': 0}
            stats['by_group'][item.group]['total'] += 1
            if item.runnable:
                stats['by_group'][item.group]['runnable'] += 1
        
        return stats

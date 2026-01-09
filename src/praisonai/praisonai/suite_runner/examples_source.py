"""
Examples Source - Adapter for examples suite.

Discovers and prepares Python example files for execution.
Uses the shared suite_runner engine.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .models import RunItem
from .discovery import FileDiscovery, get_pythonpath_for_dev


# Directive parsing regex
DIRECTIVE_PATTERN = re.compile(r'^#\s*praisonai:\s*(\w+)=(.+)$', re.MULTILINE)
INPUT_PATTERN = re.compile(r'\binput\s*\(')

# Agent-centric detection patterns
AGENT_PATTERN = re.compile(r'\bAgent\s*\(')
AGENTS_PATTERN = re.compile(r'\b(?:Agents|PraisonAIAgents)\s*\(')
WORKFLOW_PATTERN = re.compile(r'\bWorkflow\s*\(')


class ExamplesSource:
    """
    Discovers and prepares example Python files.
    
    Parses directives from comments:
    - # praisonai: skip=true
    - # praisonai: timeout=120
    - # praisonai: require_env=KEY1,KEY2
    - # praisonai: xfail=reason
    """
    
    def __init__(
        self,
        root: Path,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
    ):
        """
        Initialize examples source.
        
        Args:
            root: Root examples directory.
            include_patterns: Glob patterns to include.
            exclude_patterns: Glob patterns to exclude.
            groups: Specific groups (subdirs) to include.
        """
        self.root = Path(root).resolve()
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.groups = groups
        
        self._discovery = FileDiscovery(
            root=self.root,
            extensions=['.py'],
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            ignore_underscore=True,
        )
    
    def discover(self) -> List[RunItem]:
        """
        Discover all example files and create RunItems.
        
        Returns:
            List of RunItem objects.
        """
        if self.groups:
            grouped = self._discovery.discover_by_group(self.groups)
            files = []
            for group_files in grouped.values():
                files.extend(group_files)
            files = sorted(files, key=lambda p: p.relative_to(self.root).as_posix())
        else:
            files = self._discovery.discover()
        
        items = []
        for path in files:
            item = self._create_item(path)
            items.append(item)
        
        return items
    
    def _create_item(self, path: Path) -> RunItem:
        """Create RunItem from example file."""
        group = FileDiscovery.get_group_for_path(path, self.root)
        rel_path = path.relative_to(self.root).as_posix()
        item_id = rel_path.replace('/', '__').replace('.py', '')
        
        # Read file content
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            content = ""
        
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
            skip_reason = "Interactive example (contains input())"
        
        # Detect agent-centric usage
        uses_agent = bool(AGENT_PATTERN.search(content))
        uses_agents = bool(AGENTS_PATTERN.search(content))
        uses_workflow = bool(WORKFLOW_PATTERN.search(content))
        
        # Determine runnable status
        runnable = not skip
        runnable_decision = "runnable" if runnable else (skip_reason or "skipped")
        
        return RunItem(
            item_id=item_id,
            suite="examples",
            group=group,
            source_path=path,
            block_index=0,
            language="python",
            code=content,
            script_path=path,  # Examples run directly
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
        )
    
    def get_groups(self) -> List[str]:
        """Get available groups."""
        return self._discovery.get_groups()
    
    def get_pythonpath(self) -> List[str]:
        """Get PYTHONPATH additions for dev mode."""
        return get_pythonpath_for_dev(self.root)

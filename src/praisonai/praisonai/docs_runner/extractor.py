"""
Fence Extractor for Markdown/MDX documentation.

Parses code fences from documentation files with support for:
- Standard markdown fences (``` and ~~~)
- Titled fences (```python Title)
- PraisonAI directives (<!-- praisonai: ... -->)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# Patterns for fence detection
FENCE_START_PATTERN = re.compile(r'^(\s*)(`{3,}|~{3,})(\w*)\s*(.*)$')
DIRECTIVE_PATTERN = re.compile(
    r'<!--\s*praisonai:\s*([^>]+)\s*-->',
    re.IGNORECASE
)
DIRECTIVE_KV_PATTERN = re.compile(r'(\w+)=([^\s]+)')


@dataclass
class CodeBlock:
    """Represents an extracted code block from documentation."""
    
    doc_path: Path
    language: str
    code: str
    line_start: int
    line_end: int
    block_index: int
    title: Optional[str] = None
    directive_runnable: Optional[bool] = None
    directive_skip: Optional[bool] = None
    directive_timeout: Optional[int] = None
    directive_require_env: List[str] = field(default_factory=list)
    
    @property
    def code_hash(self) -> str:
        """Generate hash of code content for change tracking."""
        return hashlib.sha256(self.code.encode()).hexdigest()[:16]
    
    @property
    def slug(self) -> str:
        """Generate a filesystem-safe slug for this block."""
        doc_slug = self.doc_path.stem.replace(" ", "_").replace("-", "_")
        return f"{doc_slug}__{self.block_index}"


class FenceExtractor:
    """Extracts code fences from markdown/mdx files."""
    
    def __init__(self, languages: Optional[List[str]] = None):
        """
        Initialize extractor.
        
        Args:
            languages: If provided, only extract blocks with these languages.
                       Default is None (extract all).
        """
        self.languages = languages
    
    def extract(self, doc_path: Path) -> List[CodeBlock]:
        """
        Extract all code blocks from a documentation file.
        
        Args:
            doc_path: Path to the markdown/mdx file.
            
        Returns:
            List of CodeBlock objects.
        """
        try:
            content = doc_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return []
        
        blocks = []
        lines = content.split('\n')
        
        i = 0
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
                    # Check if this is the closing fence (same indent + same fence chars)
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
                    code_start = fence_start_line + 1  # Line after opening fence
                    code_end = code_start + len(code_lines) - 1 if code_lines else code_start
                    
                    # Look for directive in previous lines
                    directive_runnable = None
                    directive_skip = None
                    directive_timeout = None
                    directive_require_env = []
                    
                    # Check up to 5 lines before for directive
                    pre_lines = lines[max(0, i-5):i]
                    pre_text = '\n'.join(pre_lines)
                    directive_match = DIRECTIVE_PATTERN.search(pre_text)
                    if directive_match:
                        directive_text = directive_match.group(1)
                        for kv_match in DIRECTIVE_KV_PATTERN.finditer(directive_text):
                            key, value = kv_match.group(1).lower(), kv_match.group(2)
                            
                            if key == 'runnable':
                                directive_runnable = value.lower() in ('true', '1', 'yes')
                            elif key == 'skip':
                                directive_skip = value.lower() in ('true', '1', 'yes')
                            elif key == 'timeout':
                                try:
                                    directive_timeout = int(value)
                                except ValueError:
                                    pass
                            elif key == 'require_env':
                                directive_require_env = [e.strip() for e in value.split(',') if e.strip()]
                    
                    block = CodeBlock(
                        doc_path=doc_path,
                        language=language.lower() if language else '',
                        code=code_content,
                        line_start=code_start,
                        line_end=code_end,
                        block_index=len(blocks),
                        title=title if title else None,
                        directive_runnable=directive_runnable,
                        directive_skip=directive_skip,
                        directive_timeout=directive_timeout,
                        directive_require_env=directive_require_env,
                    )
                    blocks.append(block)
                    
                    i = j + 1  # Move past closing fence
                    continue
            
            i += 1
        
        return blocks
    
    def extract_from_directory(
        self,
        docs_path: Path,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> List[CodeBlock]:
        """
        Extract code blocks from all docs in a directory.
        
        Args:
            docs_path: Root documentation directory.
            include_patterns: Glob patterns to include.
            exclude_patterns: Glob patterns to exclude.
            
        Returns:
            List of all CodeBlock objects from all files.
        """
        import fnmatch
        
        all_blocks = []
        
        # Find all .md and .mdx files
        for ext in ('*.md', '*.mdx'):
            for doc_file in docs_path.rglob(ext):
                # Skip node_modules and hidden directories
                rel_path = doc_file.relative_to(docs_path)
                parts = rel_path.parts
                
                if any(p.startswith('.') or p == 'node_modules' for p in parts):
                    continue
                
                rel_str = rel_path.as_posix()
                
                # Apply include patterns
                if include_patterns:
                    if not any(fnmatch.fnmatch(rel_str, p) for p in include_patterns):
                        continue
                
                # Apply exclude patterns
                if exclude_patterns:
                    if any(fnmatch.fnmatch(rel_str, p) for p in exclude_patterns):
                        continue
                
                blocks = self.extract(doc_file)
                all_blocks.extend(blocks)
        
        return all_blocks

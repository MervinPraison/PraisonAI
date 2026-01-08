"""
Hierarchical Summarization for PraisonAI Agents (Phase 6).

Provides hierarchical summaries for massive corpora:
- File-level summaries
- Folder-level summaries
- Project-level summary
- Top-down query routing

No heavy imports at module level.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class SummarizerProtocol(Protocol):
    """Protocol for summarization implementations."""
    
    def summarize(self, text: str, max_tokens: int = 500) -> str:
        """Summarize text to max_tokens."""
        ...


@dataclass
class SummaryNode:
    """A node in the summary hierarchy."""
    path: str
    level: int  # 0=chunk, 1=file, 2=folder, 3=project
    summary: str = ""
    children: List[str] = field(default_factory=list)
    token_count: int = 0
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "level": self.level,
            "summary": self.summary,
            "children": self.children,
            "token_count": self.token_count,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummaryNode":
        return cls(
            path=data.get("path", ""),
            level=data.get("level", 0),
            summary=data.get("summary", ""),
            children=data.get("children", []),
            token_count=data.get("token_count", 0),
            created_at=data.get("created_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class HierarchyResult:
    """Result of hierarchy building or querying."""
    nodes: Dict[str, SummaryNode] = field(default_factory=dict)
    root_path: str = ""
    total_files: int = 0
    total_tokens: int = 0
    levels: int = 3
    built_at: Optional[str] = None


def estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token)."""
    if not text:
        return 0
    return len(text) // 4 + 1


class HierarchicalSummarizer:
    """
    Builds and queries hierarchical summaries for large corpora.
    
    Hierarchy levels:
    - Level 0: Individual chunks
    - Level 1: File summaries
    - Level 2: Folder summaries
    - Level 3: Project summary
    
    Query routing:
    - Start at project level
    - Route to relevant folders
    - Drill into relevant files
    - Return relevant chunks
    """
    
    def __init__(
        self,
        llm=None,
        persist_path: str = ".praison/summaries",
        verbose: bool = False,
    ):
        """
        Initialize summarizer.
        
        Args:
            llm: LLM for generating summaries
            persist_path: Path to persist summaries
            verbose: Enable verbose logging
        """
        self._llm = llm
        self._persist_path = persist_path
        self._verbose = verbose
        self._hierarchy: Dict[str, SummaryNode] = {}
    
    def build_hierarchy(
        self,
        corpus_path: str,
        levels: int = 3,
        force: bool = False,
    ) -> HierarchyResult:
        """
        Build summary hierarchy for corpus.
        
        Args:
            corpus_path: Path to corpus root
            levels: Number of hierarchy levels (1-3)
            force: Force rebuild even if cached
            
        Returns:
            HierarchyResult with built hierarchy
        """
        result = HierarchyResult(
            root_path=corpus_path,
            levels=levels,
            built_at=datetime.now().isoformat(),
        )
        
        # Check for cached hierarchy
        if not force:
            cached = self._load_hierarchy(corpus_path)
            if cached:
                return cached
        
        # Collect all files
        files = self._collect_files(corpus_path)
        result.total_files = len(files)
        
        # Build file-level summaries (Level 1)
        for filepath in files:
            node = self._build_file_summary(filepath, corpus_path)
            if node:
                self._hierarchy[filepath] = node
                result.nodes[filepath] = node
        
        # Build folder-level summaries (Level 2)
        if levels >= 2:
            folders = self._get_folders(files, corpus_path)
            for folder in folders:
                node = self._build_folder_summary(folder, corpus_path)
                if node:
                    self._hierarchy[folder] = node
                    result.nodes[folder] = node
        
        # Build project-level summary (Level 3)
        if levels >= 3:
            node = self._build_project_summary(corpus_path)
            if node:
                self._hierarchy[corpus_path] = node
                result.nodes[corpus_path] = node
        
        # Calculate total tokens
        result.total_tokens = sum(n.token_count for n in result.nodes.values())
        
        # Persist hierarchy
        self._save_hierarchy(corpus_path, result)
        
        return result
    
    def query_hierarchy(
        self,
        query: str,
        corpus_path: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Query hierarchy top-down to find relevant content.
        
        Args:
            query: Search query
            corpus_path: Path to corpus root
            max_results: Maximum results to return
            
        Returns:
            List of relevant chunks with paths
        """
        # Load hierarchy if not in memory
        if corpus_path not in self._hierarchy:
            cached = self._load_hierarchy(corpus_path)
            if cached:
                self._hierarchy.update(cached.nodes)
        
        # Start at project level
        project_node = self._hierarchy.get(corpus_path)
        if not project_node:
            return []
        
        # Score folders by relevance
        query_words = set(query.lower().split())
        relevant_paths = []
        
        for path, node in self._hierarchy.items():
            if node.level == 1:  # File level
                summary_words = set(node.summary.lower().split())
                overlap = len(query_words & summary_words)
                if overlap > 0:
                    relevant_paths.append((path, overlap, node))
        
        # Sort by relevance
        relevant_paths.sort(key=lambda x: x[1], reverse=True)
        
        # Return top results
        results = []
        for path, score, node in relevant_paths[:max_results]:
            results.append({
                "path": path,
                "summary": node.summary,
                "score": score,
                "level": node.level,
                "metadata": node.metadata,
            })
        
        return results
    
    def _collect_files(self, corpus_path: str) -> List[str]:
        """Collect all indexable files in corpus."""
        files = []
        extensions = {'.txt', '.md', '.py', '.js', '.ts', '.json', '.yaml', '.yml'}
        
        for root, dirs, filenames in os.walk(corpus_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in extensions:
                    files.append(os.path.join(root, filename))
        
        return files
    
    def _get_folders(self, files: List[str], corpus_path: str) -> List[str]:
        """Get unique folder paths from files."""
        folders = set()
        for filepath in files:
            folder = os.path.dirname(filepath)
            if folder != corpus_path:
                folders.add(folder)
        return list(folders)
    
    def _build_file_summary(self, filepath: str, corpus_path: str) -> Optional[SummaryNode]:
        """Build summary for a single file."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Simple extractive summary (first 500 chars + key lines)
            summary = self._extract_summary(content, max_chars=500)
            
            return SummaryNode(
                path=filepath,
                level=1,
                summary=summary,
                token_count=estimate_tokens(summary),
                created_at=datetime.now().isoformat(),
                metadata={
                    "filename": os.path.basename(filepath),
                    "relative_path": os.path.relpath(filepath, corpus_path),
                },
            )
        except Exception:
            return None
    
    def _build_folder_summary(self, folder: str, corpus_path: str) -> Optional[SummaryNode]:
        """Build summary for a folder from child summaries."""
        children = []
        child_summaries = []
        
        for path, node in self._hierarchy.items():
            if node.level == 1 and os.path.dirname(path) == folder:
                children.append(path)
                child_summaries.append(node.summary[:200])
        
        if not children:
            return None
        
        # Combine child summaries
        combined = " | ".join(child_summaries)
        summary = f"Folder contains {len(children)} files: {combined[:500]}"
        
        return SummaryNode(
            path=folder,
            level=2,
            summary=summary,
            children=children,
            token_count=estimate_tokens(summary),
            created_at=datetime.now().isoformat(),
            metadata={
                "folder_name": os.path.basename(folder),
                "file_count": len(children),
            },
        )
    
    def _build_project_summary(self, corpus_path: str) -> Optional[SummaryNode]:
        """Build project-level summary from folder summaries."""
        folders = []
        folder_summaries = []
        
        for path, node in self._hierarchy.items():
            if node.level == 2:
                folders.append(path)
                folder_summaries.append(node.summary[:100])
        
        # Also include direct file children
        files = []
        for path, node in self._hierarchy.items():
            if node.level == 1 and os.path.dirname(path) == corpus_path:
                files.append(path)
        
        combined = " | ".join(folder_summaries[:10])
        summary = f"Project with {len(folders)} folders and {len(files)} root files: {combined[:500]}"
        
        return SummaryNode(
            path=corpus_path,
            level=3,
            summary=summary,
            children=folders + files,
            token_count=estimate_tokens(summary),
            created_at=datetime.now().isoformat(),
            metadata={
                "folder_count": len(folders),
                "root_file_count": len(files),
            },
        )
    
    def _extract_summary(self, content: str, max_chars: int = 500) -> str:
        """Extract summary from content."""
        if not content:
            return ""
        
        # Get first paragraph or lines
        lines = content.split('\n')
        summary_lines = []
        char_count = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if char_count + len(line) > max_chars:
                break
            summary_lines.append(line)
            char_count += len(line)
        
        return ' '.join(summary_lines)
    
    def _save_hierarchy(self, corpus_path: str, result: HierarchyResult) -> None:
        """Save hierarchy to disk."""
        try:
            os.makedirs(self._persist_path, exist_ok=True)
            
            # Create safe filename from path
            safe_name = corpus_path.replace('/', '_').replace('\\', '_')
            filepath = os.path.join(self._persist_path, f"{safe_name}_hierarchy.json")
            
            data = {
                "root_path": result.root_path,
                "total_files": result.total_files,
                "total_tokens": result.total_tokens,
                "levels": result.levels,
                "built_at": result.built_at,
                "nodes": {k: v.to_dict() for k, v in result.nodes.items()},
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def _load_hierarchy(self, corpus_path: str) -> Optional[HierarchyResult]:
        """Load hierarchy from disk."""
        try:
            safe_name = corpus_path.replace('/', '_').replace('\\', '_')
            filepath = os.path.join(self._persist_path, f"{safe_name}_hierarchy.json")
            
            if not os.path.exists(filepath):
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            result = HierarchyResult(
                root_path=data.get("root_path", ""),
                total_files=data.get("total_files", 0),
                total_tokens=data.get("total_tokens", 0),
                levels=data.get("levels", 3),
                built_at=data.get("built_at"),
            )
            
            for path, node_data in data.get("nodes", {}).items():
                result.nodes[path] = SummaryNode.from_dict(node_data)
            
            return result
        except Exception:
            return None

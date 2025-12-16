"""
Result classes for Fast Context.

These dataclasses represent the output of Fast Context searches,
providing structured file and line range information.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time


@dataclass
class LineRange:
    """Represents a range of lines in a file.
    
    Attributes:
        start: Starting line number (1-indexed)
        end: Ending line number (1-indexed, inclusive)
        content: Optional content of the lines
        relevance_score: Score indicating relevance (0.0-1.0)
    """
    start: int
    end: int
    content: Optional[str] = None
    relevance_score: float = 1.0
    
    def __post_init__(self):
        if self.start < 1:
            self.start = 1
        if self.end < self.start:
            self.end = self.start
    
    @property
    def line_count(self) -> int:
        """Number of lines in this range."""
        return self.end - self.start + 1
    
    def overlaps(self, other: "LineRange") -> bool:
        """Check if this range overlaps with another."""
        return not (self.end < other.start or self.start > other.end)
    
    def merge(self, other: "LineRange") -> "LineRange":
        """Merge with another overlapping range."""
        if not self.overlaps(other):
            raise ValueError("Cannot merge non-overlapping ranges")
        return LineRange(
            start=min(self.start, other.start),
            end=max(self.end, other.end),
            content=None,  # Content needs to be re-fetched
            relevance_score=max(self.relevance_score, other.relevance_score)
        )


@dataclass
class FileMatch:
    """Represents a file match from Fast Context search.
    
    Attributes:
        path: Absolute or relative path to the file
        line_ranges: List of relevant line ranges in the file
        relevance_score: Overall relevance score (0.0-1.0)
        match_count: Number of pattern matches found
    """
    path: str
    line_ranges: List[LineRange] = field(default_factory=list)
    relevance_score: float = 1.0
    match_count: int = 0
    
    def add_line_range(self, line_range: LineRange) -> None:
        """Add a line range, merging with existing overlapping ranges."""
        # Find overlapping ranges
        overlapping = []
        non_overlapping = []
        for existing in self.line_ranges:
            if existing.overlaps(line_range):
                overlapping.append(existing)
            else:
                non_overlapping.append(existing)
        
        # Merge all overlapping ranges
        merged = line_range
        for overlap in overlapping:
            merged = merged.merge(overlap)
        
        self.line_ranges = non_overlapping + [merged]
        self.line_ranges.sort(key=lambda r: r.start)
    
    @property
    def total_lines(self) -> int:
        """Total number of lines across all ranges."""
        return sum(r.line_count for r in self.line_ranges)


@dataclass
class FastContextResult:
    """Result of a Fast Context search operation.
    
    Attributes:
        files: List of matching files with line ranges
        query: The original search query
        search_time_ms: Time taken for the search in milliseconds
        turns_used: Number of turns used by the subagent
        total_tool_calls: Total number of tool calls made
        from_cache: Whether result was retrieved from cache
    """
    files: List[FileMatch] = field(default_factory=list)
    query: str = ""
    search_time_ms: int = 0
    turns_used: int = 0
    total_tool_calls: int = 0
    from_cache: bool = False
    
    _start_time: float = field(default=0.0, repr=False)
    
    def start_timer(self) -> None:
        """Start the search timer."""
        self._start_time = time.perf_counter()
    
    def stop_timer(self) -> None:
        """Stop the timer and record elapsed time."""
        if self._start_time > 0:
            elapsed = time.perf_counter() - self._start_time
            self.search_time_ms = int(elapsed * 1000)
    
    def add_file(self, file_match: FileMatch) -> None:
        """Add a file match, merging with existing if same path."""
        for existing in self.files:
            if existing.path == file_match.path:
                # Merge line ranges
                for lr in file_match.line_ranges:
                    existing.add_line_range(lr)
                existing.relevance_score = max(
                    existing.relevance_score, 
                    file_match.relevance_score
                )
                existing.match_count += file_match.match_count
                return
        self.files.append(file_match)
    
    def sort_by_relevance(self) -> None:
        """Sort files by relevance score (highest first)."""
        self.files.sort(key=lambda f: f.relevance_score, reverse=True)
    
    @property
    def total_files(self) -> int:
        """Total number of files found."""
        return len(self.files)
    
    @property
    def total_lines(self) -> int:
        """Total number of lines across all files."""
        return sum(f.total_lines for f in self.files)
    
    def to_context_string(self, max_files: int = 10, include_content: bool = True) -> str:
        """Convert result to a context string for the main agent.
        
        Args:
            max_files: Maximum number of files to include
            include_content: Whether to include line content
            
        Returns:
            Formatted context string
        """
        if not self.files:
            return "No relevant files found."
        
        lines = [f"Found {self.total_files} relevant file(s):"]
        
        for i, file_match in enumerate(self.files[:max_files]):
            lines.append(f"\n## {file_match.path}")
            if file_match.line_ranges:
                for lr in file_match.line_ranges:
                    lines.append(f"  Lines {lr.start}-{lr.end}")
                    if include_content and lr.content:
                        # Indent content
                        content_lines = lr.content.split('\n')
                        for cl in content_lines:
                            lines.append(f"    {cl}")
        
        if len(self.files) > max_files:
            lines.append(f"\n... and {len(self.files) - max_files} more files")
        
        return '\n'.join(lines)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "files": [
                {
                    "path": f.path,
                    "relevance_score": f.relevance_score,
                    "match_count": f.match_count,
                    "line_ranges": [
                        {
                            "start": lr.start,
                            "end": lr.end,
                            "relevance_score": lr.relevance_score
                        }
                        for lr in f.line_ranges
                    ]
                }
                for f in self.files
            ],
            "query": self.query,
            "search_time_ms": self.search_time_ms,
            "turns_used": self.turns_used,
            "total_tool_calls": self.total_tool_calls,
            "from_cache": self.from_cache
        }

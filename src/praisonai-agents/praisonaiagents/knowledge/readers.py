"""
Data Reader Adapter Protocol for PraisonAI Agents.

This module defines the protocol for document readers and a registry system.
NO heavy imports - only stdlib and typing.

Implementations are provided by the wrapper layer (praisonai.adapters.readers).
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """
    Lightweight document representation.
    
    Attributes:
        content: The text content of the document
        metadata: Optional metadata dict (source, filename, page, etc.)
        doc_id: Optional unique identifier
        embedding: Optional pre-computed embedding
    """
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    doc_id: Optional[str] = None
    embedding: Optional[List[float]] = None
    
    def __post_init__(self):
        if self.doc_id is None:
            import uuid
            self.doc_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "metadata": self.metadata,
            "doc_id": self.doc_id,
            "embedding": self.embedding
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        """Create from dictionary."""
        return cls(
            content=data.get("content", ""),
            metadata=data.get("metadata", {}),
            doc_id=data.get("doc_id"),
            embedding=data.get("embedding")
        )


@runtime_checkable
class ReaderProtocol(Protocol):
    """
    Protocol for document readers.
    
    Implementations must provide:
    - name: Identifier for the reader
    - supported_extensions: List of file extensions this reader handles
    - load(): Method to load documents from a source
    """
    
    name: str
    supported_extensions: List[str]
    
    def load(
        self, 
        source: str, 
        *, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Load documents from a source.
        
        Args:
            source: File path, URL, or other source identifier
            metadata: Optional metadata to attach to all documents
            
        Returns:
            List of Document objects
        """
        ...
    
    def can_handle(self, source: str) -> bool:
        """
        Check if this reader can handle the given source.
        
        Args:
            source: File path, URL, or other source identifier
            
        Returns:
            True if this reader can handle the source
        """
        ...


class ReaderRegistry:
    """
    Registry for document readers.
    
    Provides lazy loading and automatic reader selection based on source type.
    """
    
    _instance: Optional["ReaderRegistry"] = None
    
    def __new__(cls) -> "ReaderRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._readers: Dict[str, Callable[[], ReaderProtocol]] = {}
            cls._instance._extension_map: Dict[str, str] = {}
            cls._instance._initialized_readers: Dict[str, ReaderProtocol] = {}
        return cls._instance
    
    def register(
        self, 
        name: str, 
        factory: Callable[[], ReaderProtocol],
        extensions: Optional[List[str]] = None
    ) -> None:
        """
        Register a reader factory.
        
        Args:
            name: Unique name for the reader
            factory: Callable that returns a ReaderProtocol instance
            extensions: List of file extensions this reader handles
        """
        self._readers[name] = factory
        if extensions:
            for ext in extensions:
                ext_lower = ext.lower().lstrip(".")
                self._extension_map[ext_lower] = name
    
    def get(self, name: str) -> Optional[ReaderProtocol]:
        """
        Get a reader by name (lazy initialization).
        
        Args:
            name: Reader name
            
        Returns:
            ReaderProtocol instance or None
        """
        if name in self._initialized_readers:
            return self._initialized_readers[name]
        
        if name in self._readers:
            try:
                reader = self._readers[name]()
                self._initialized_readers[name] = reader
                return reader
            except Exception as e:
                logger.warning(f"Failed to initialize reader '{name}': {e}")
                return None
        return None
    
    def get_for_source(self, source: str) -> Optional[ReaderProtocol]:
        """
        Get the best reader for a given source.
        
        Args:
            source: File path, URL, or other source identifier
            
        Returns:
            Best matching ReaderProtocol or None
        """
        source_kind = detect_source_kind(source)
        
        if source_kind == "file":
            ext = os.path.splitext(source)[1].lower().lstrip(".")
            if ext in self._extension_map:
                return self.get(self._extension_map[ext])
        elif source_kind == "url":
            # Try URL reader
            if "url" in self._readers:
                return self.get("url")
        elif source_kind == "directory":
            if "directory" in self._readers:
                return self.get("directory")
        
        # Fallback to auto reader if available
        if "auto" in self._readers:
            return self.get("auto")
        
        return None
    
    def list_readers(self) -> List[str]:
        """List all registered reader names."""
        return list(self._readers.keys())
    
    def list_extensions(self) -> Dict[str, str]:
        """List all registered extensions and their readers."""
        return dict(self._extension_map)
    
    def clear(self) -> None:
        """Clear all registered readers (mainly for testing)."""
        self._readers.clear()
        self._extension_map.clear()
        self._initialized_readers.clear()


def get_reader_registry() -> ReaderRegistry:
    """Get the global reader registry instance."""
    return ReaderRegistry()


def detect_source_kind(source: str) -> str:
    """
    Detect the kind of source without importing heavy libraries.
    
    Args:
        source: File path, URL, directory, or glob pattern
        
    Returns:
        One of: "file", "url", "directory", "glob", "unknown"
    """
    if not isinstance(source, str):
        return "unknown"
    
    source = source.strip()
    
    # Check for URL
    if source.startswith(("http://", "https://", "ftp://", "s3://", "gs://")):
        return "url"
    
    # Check for glob pattern
    if "*" in source or "?" in source or "[" in source:
        return "glob"
    
    # Check if it's a directory
    if os.path.isdir(source):
        return "directory"
    
    # Check if it's a file
    if os.path.isfile(source):
        return "file"
    
    # Check if it looks like a file path (has extension)
    if os.path.splitext(source)[1]:
        return "file"
    
    return "unknown"


def get_file_extension(source: str) -> str:
    """
    Get the file extension from a source path.
    
    Args:
        source: File path or URL
        
    Returns:
        Lowercase extension without dot, or empty string
    """
    # Handle URLs by extracting path
    if source.startswith(("http://", "https://")):
        from urllib.parse import urlparse
        path = urlparse(source).path
        return os.path.splitext(path)[1].lower().lstrip(".")
    
    return os.path.splitext(source)[1].lower().lstrip(".")


# Default extension mappings (reader name -> extensions)
DEFAULT_EXTENSION_MAPPINGS = {
    "text": ["txt", "text"],
    "markdown": ["md", "markdown"],
    "json": ["json", "jsonl"],
    "csv": ["csv", "tsv"],
    "html": ["html", "htm"],
    "xml": ["xml"],
    "pdf": ["pdf"],
    "docx": ["docx", "doc"],
    "xlsx": ["xlsx", "xls"],
    "pptx": ["pptx", "ppt"],
    "image": ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp"],
    "audio": ["mp3", "wav", "ogg", "m4a", "flac"],
    "video": ["mp4", "avi", "mov", "mkv", "webm"],
}

"""
Reader Adapters for PraisonAI.

Provides concrete implementations of ReaderProtocol:
- TextReader: Plain text files
- MarkItDownReader: Uses markitdown for documents
- DirectoryReader: Reads all files in a directory
- AutoReader: Automatic file type detection and routing
"""

import os
import glob as glob_module
import logging
import importlib.util
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy import flags
_MARKITDOWN_AVAILABLE = None
_LLAMA_INDEX_AVAILABLE = None


def _check_markitdown():
    """Check if markitdown is available."""
    global _MARKITDOWN_AVAILABLE
    if _MARKITDOWN_AVAILABLE is None:
        _MARKITDOWN_AVAILABLE = importlib.util.find_spec("markitdown") is not None
    return _MARKITDOWN_AVAILABLE


def _check_llama_index():
    """Check if llama_index is available."""
    global _LLAMA_INDEX_AVAILABLE
    if _LLAMA_INDEX_AVAILABLE is None:
        _LLAMA_INDEX_AVAILABLE = importlib.util.find_spec("llama_index") is not None
    return _LLAMA_INDEX_AVAILABLE


class TextReader:
    """Simple text file reader."""
    
    name: str = "text"
    supported_extensions: List[str] = ["txt", "text", "log"]
    
    def load(
        self, 
        source: str, 
        *, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Load a text file."""
        from praisonaiagents.knowledge.readers import Document
        
        try:
            with open(source, 'r', encoding='utf-8') as f:
                content = f.read()
            
            doc_metadata = metadata or {}
            doc_metadata.update({
                "source": source,
                "filename": os.path.basename(source),
                "file_type": "text"
            })
            
            return [Document(content=content, metadata=doc_metadata)]
        except Exception as e:
            logger.error(f"Failed to read text file {source}: {e}")
            return []
    
    def can_handle(self, source: str) -> bool:
        """Check if this reader can handle the source."""
        ext = os.path.splitext(source)[1].lower().lstrip(".")
        return ext in self.supported_extensions


class MarkItDownReader:
    """Reader using markitdown for document conversion."""
    
    name: str = "markitdown"
    supported_extensions: List[str] = [
        "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
        "html", "htm", "md", "markdown", "csv", "json", "xml",
        "jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp",
        "mp3", "wav", "ogg", "m4a", "flac"
    ]
    
    def __init__(self):
        self._converter = None
    
    @property
    def converter(self):
        """Lazy load markitdown converter."""
        if self._converter is None:
            if not _check_markitdown():
                raise ImportError(
                    "markitdown is required for document conversion. "
                    "Install with: pip install markitdown"
                )
            from markitdown import MarkItDown
            self._converter = MarkItDown()
        return self._converter
    
    def load(
        self, 
        source: str, 
        *, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Load a document using markitdown."""
        from praisonaiagents.knowledge.readers import Document
        
        try:
            result = self.converter.convert(source)
            content = result.text_content
            
            if not content:
                logger.warning(f"No content extracted from {source}")
                return []
            
            doc_metadata = metadata or {}
            doc_metadata.update({
                "source": source,
                "filename": os.path.basename(source),
                "file_type": os.path.splitext(source)[1].lower().lstrip(".")
            })
            
            return [Document(content=content, metadata=doc_metadata)]
        except Exception as e:
            logger.error(f"Failed to convert document {source}: {e}")
            return []
    
    def can_handle(self, source: str) -> bool:
        """Check if this reader can handle the source."""
        ext = os.path.splitext(source)[1].lower().lstrip(".")
        return ext in self.supported_extensions and _check_markitdown()


class DirectoryReader:
    """Reader for directories - recursively reads all files."""
    
    name: str = "directory"
    supported_extensions: List[str] = []  # Handles directories, not extensions
    
    def __init__(self, recursive: bool = True, exclude_patterns: Optional[List[str]] = None):
        self.recursive = recursive
        self.exclude_patterns = exclude_patterns or [
            "*.pyc", "__pycache__", ".git", ".svn", "node_modules",
            "*.egg-info", ".env", ".venv", "venv"
        ]
    
    def load(
        self, 
        source: str, 
        *, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Load all files from a directory."""
        from praisonaiagents.knowledge.readers import get_reader_registry
        
        if not os.path.isdir(source):
            logger.error(f"Not a directory: {source}")
            return []
        
        documents = []
        registry = get_reader_registry()
        
        # Walk directory
        if self.recursive:
            for root, dirs, files in os.walk(source):
                # Filter out excluded directories
                dirs[:] = [d for d in dirs if not self._should_exclude(d)]
                
                for file in files:
                    if self._should_exclude(file):
                        continue
                    
                    file_path = os.path.join(root, file)
                    reader = registry.get_for_source(file_path)
                    
                    if reader and reader.name != "directory":
                        file_metadata = (metadata or {}).copy()
                        file_metadata["parent_dir"] = source
                        loaded_docs = reader.load(file_path, metadata=file_metadata)
                        documents.extend(loaded_docs)
        else:
            for file in os.listdir(source):
                if self._should_exclude(file):
                    continue
                
                file_path = os.path.join(source, file)
                if os.path.isfile(file_path):
                    reader = registry.get_for_source(file_path)
                    if reader and reader.name != "directory":
                        file_metadata = (metadata or {}).copy()
                        file_metadata["parent_dir"] = source
                        docs = reader.load(file_path, metadata=file_metadata)
                        documents.extend(docs)
        
        return documents
    
    def can_handle(self, source: str) -> bool:
        """Check if this reader can handle the source."""
        return os.path.isdir(source)
    
    def _should_exclude(self, name: str) -> bool:
        """Check if a file/directory should be excluded."""
        import fnmatch
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False


class GlobReader:
    """Reader for glob patterns."""
    
    name: str = "glob"
    supported_extensions: List[str] = []
    
    def load(
        self, 
        source: str, 
        *, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Load files matching a glob pattern."""
        from praisonaiagents.knowledge.readers import get_reader_registry
        
        documents = []
        registry = get_reader_registry()
        
        for file_path in glob_module.glob(source, recursive=True):
            if os.path.isfile(file_path):
                reader = registry.get_for_source(file_path)
                if reader and reader.name not in ("glob", "directory"):
                    file_metadata = (metadata or {}).copy()
                    file_metadata["glob_pattern"] = source
                    docs = reader.load(file_path, metadata=file_metadata)
                    documents.extend(docs)
        
        return documents
    
    def can_handle(self, source: str) -> bool:
        """Check if this is a glob pattern."""
        return "*" in source or "?" in source or "[" in source


class URLReader:
    """Reader for URLs (HTML pages)."""
    
    name: str = "url"
    supported_extensions: List[str] = []
    
    def load(
        self, 
        source: str, 
        *, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Load content from a URL."""
        from praisonaiagents.knowledge.readers import Document
        
        try:
            import httpx
        except ImportError:
            try:
                import requests as httpx
            except ImportError:
                logger.error("httpx or requests required for URL reading")
                return []
        
        try:
            response = httpx.get(source, timeout=30, follow_redirects=True)
            response.raise_for_status()
            content = response.text
            
            # Try to extract text from HTML
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                content = soup.get_text(separator='\n', strip=True)
            except ImportError:
                # Fall back to raw content
                pass
            
            doc_metadata = metadata or {}
            doc_metadata.update({
                "source": source,
                "url": source,
                "file_type": "html"
            })
            
            return [Document(content=content, metadata=doc_metadata)]
        except Exception as e:
            logger.error(f"Failed to fetch URL {source}: {e}")
            return []
    
    def can_handle(self, source: str) -> bool:
        """Check if this is a URL."""
        return source.startswith(("http://", "https://"))


class AutoReader:
    """
    Automatic reader that detects source type and routes to appropriate reader.
    
    Selection policy:
    1. If LlamaIndex reader is installed + supports the type → use it
    2. Else if MarkItDown supports → use it
    3. Else use simple built-in reader
    """
    
    name: str = "auto"
    supported_extensions: List[str] = []  # Handles everything
    
    def load(
        self, 
        source: str, 
        *, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Load from any source type."""
        from praisonaiagents.knowledge.readers import get_reader_registry, detect_source_kind
        
        registry = get_reader_registry()
        source_kind = detect_source_kind(source)
        
        # Route based on source kind
        if source_kind == "url":
            reader = registry.get("url")
        elif source_kind == "directory":
            reader = registry.get("directory")
        elif source_kind == "glob":
            reader = registry.get("glob")
        elif source_kind == "file":
            # Find best reader for file type
            reader = registry.get_for_source(source)
            if reader and reader.name == "auto":
                # Avoid infinite recursion - use markitdown or text
                ext = os.path.splitext(source)[1].lower().lstrip(".")
                if ext in MarkItDownReader.supported_extensions and _check_markitdown():
                    reader = registry.get("markitdown")
                else:
                    reader = registry.get("text")
        else:
            # Unknown - try markitdown then text
            if _check_markitdown():
                reader = registry.get("markitdown")
            else:
                reader = registry.get("text")
        
        if reader:
            return reader.load(source, metadata=metadata)
        
        logger.warning(f"No reader found for source: {source}")
        return []
    
    def can_handle(self, source: str) -> bool:
        """AutoReader can handle anything."""
        return True


def register_default_readers():
    """Register all default readers with the registry."""
    from praisonaiagents.knowledge.readers import get_reader_registry
    
    registry = get_reader_registry()
    
    # Register text reader
    registry.register("text", TextReader, ["txt", "text", "log"])
    
    # Register markitdown reader
    registry.register("markitdown", MarkItDownReader, MarkItDownReader.supported_extensions)
    
    # Register directory reader
    registry.register("directory", DirectoryReader)
    
    # Register glob reader
    registry.register("glob", GlobReader)
    
    # Register URL reader
    registry.register("url", URLReader)
    
    # Register auto reader
    registry.register("auto", AutoReader)
    
    logger.debug("Registered default readers")


# Auto-register on import
register_default_readers()

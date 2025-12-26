"""
Template Cache

Disk-based caching for templates with TTL support.
Pinned versions are cached indefinitely, 'latest' has configurable TTL.
"""

import hashlib
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .resolver import ResolvedTemplate, TemplateSource


@dataclass
class CacheMetadata:
    """Metadata for a cached template."""
    fetched_at: float
    etag: Optional[str] = None
    sha256: Optional[str] = None
    ttl_seconds: int = 86400  # 24 hours default
    source_url: Optional[str] = None
    version: Optional[str] = None
    is_pinned: bool = False
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        if self.is_pinned:
            return False  # Pinned versions never expire
        return time.time() > (self.fetched_at + self.ttl_seconds)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "fetched_at": self.fetched_at,
            "etag": self.etag,
            "sha256": self.sha256,
            "ttl_seconds": self.ttl_seconds,
            "source_url": self.source_url,
            "version": self.version,
            "is_pinned": self.is_pinned,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheMetadata":
        """Create from dictionary."""
        return cls(
            fetched_at=data.get("fetched_at", 0),
            etag=data.get("etag"),
            sha256=data.get("sha256"),
            ttl_seconds=data.get("ttl_seconds", 86400),
            source_url=data.get("source_url"),
            version=data.get("version"),
            is_pinned=data.get("is_pinned", False),
        )


@dataclass
class CachedTemplate:
    """A cached template with its metadata."""
    path: Path
    metadata: CacheMetadata
    config: Dict[str, Any] = field(default_factory=dict)


class TemplateCache:
    """
    Disk-based template cache with TTL support.
    
    Cache structure:
    ~/.praison/cache/templates/
    ├── github/
    │   └── owner/
    │       └── repo/
    │           └── template-name/
    │               └── ref/
    │                   ├── TEMPLATE.yaml
    │                   ├── workflow.yaml
    │                   └── .cache_meta.json
    ├── package/
    │   └── package_name/
    │       └── template-name/
    └── http/
        └── hash-of-url/
    """
    
    DEFAULT_CACHE_DIR = Path.home() / ".praison" / "cache" / "templates"
    DEFAULT_TTL = 86400  # 24 hours
    METADATA_FILE = ".cache_meta.json"
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        default_ttl: int = DEFAULT_TTL
    ):
        """
        Initialize the template cache.
        
        Args:
            cache_dir: Custom cache directory (default: ~/.praison/cache/templates)
            default_ttl: Default TTL in seconds for non-pinned templates
        """
        self.cache_dir = cache_dir or self.DEFAULT_CACHE_DIR
        self.default_ttl = default_ttl
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self) -> None:
        """Ensure the cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, resolved: ResolvedTemplate) -> Path:
        """Get the cache path for a resolved template."""
        if resolved.source == TemplateSource.LOCAL:
            # Local templates are not cached
            return Path(resolved.path)
        
        elif resolved.source == TemplateSource.PACKAGE:
            # package/package_name/template
            return self.cache_dir / "package" / resolved.path
        
        elif resolved.source == TemplateSource.GITHUB:
            # github/owner/repo/template/ref
            ref = resolved.ref or "main"
            return (
                self.cache_dir / "github" / 
                resolved.owner / resolved.repo / 
                resolved.path / ref
            )
        
        elif resolved.source == TemplateSource.HTTP:
            # http/hash-of-url
            url_hash = hashlib.sha256(resolved.url.encode()).hexdigest()[:16]
            return self.cache_dir / "http" / url_hash
        
        raise ValueError(f"Unknown template source: {resolved.source}")
    
    def get(
        self,
        resolved: ResolvedTemplate,
        offline: bool = False
    ) -> Optional[CachedTemplate]:
        """
        Get a cached template if it exists and is valid.
        
        Args:
            resolved: Resolved template reference
            offline: If True, return cached version even if expired
            
        Returns:
            CachedTemplate if found and valid, None otherwise
        """
        if resolved.source == TemplateSource.LOCAL:
            # Local templates are not cached, return path directly
            path = Path(resolved.path)
            if path.exists():
                return CachedTemplate(
                    path=path,
                    metadata=CacheMetadata(
                        fetched_at=time.time(),
                        is_pinned=True
                    )
                )
            return None
        
        cache_path = self._get_cache_path(resolved)
        meta_path = cache_path / self.METADATA_FILE
        
        if not cache_path.exists() or not meta_path.exists():
            return None
        
        # Load metadata
        try:
            with open(meta_path, "r") as f:
                metadata = CacheMetadata.from_dict(json.load(f))
        except (json.JSONDecodeError, IOError):
            return None
        
        # Check expiration (unless offline mode)
        if not offline and metadata.is_expired():
            return None
        
        return CachedTemplate(
            path=cache_path,
            metadata=metadata
        )
    
    def put(
        self,
        resolved: ResolvedTemplate,
        content_dir: Path,
        etag: Optional[str] = None,
        sha256: Optional[str] = None
    ) -> CachedTemplate:
        """
        Store a template in the cache.
        
        Args:
            resolved: Resolved template reference
            content_dir: Directory containing template files to cache
            etag: Optional ETag for cache validation
            sha256: Optional SHA256 checksum
            
        Returns:
            CachedTemplate with the cached location
        """
        if resolved.source == TemplateSource.LOCAL:
            # Don't cache local templates
            return CachedTemplate(
                path=Path(resolved.path),
                metadata=CacheMetadata(
                    fetched_at=time.time(),
                    is_pinned=True
                )
            )
        
        cache_path = self._get_cache_path(resolved)
        
        # Remove existing cache entry
        if cache_path.exists():
            shutil.rmtree(cache_path)
        
        # Copy content to cache
        cache_path.mkdir(parents=True, exist_ok=True)
        
        if content_dir.is_dir():
            for item in content_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, cache_path / item.name)
                elif item.is_dir():
                    shutil.copytree(item, cache_path / item.name)
        else:
            # Single file
            shutil.copy2(content_dir, cache_path / content_dir.name)
        
        # Create metadata
        metadata = CacheMetadata(
            fetched_at=time.time(),
            etag=etag,
            sha256=sha256,
            ttl_seconds=self.default_ttl,
            source_url=resolved.url if resolved.source == TemplateSource.HTTP else None,
            version=resolved.ref,
            is_pinned=resolved.is_pinned
        )
        
        # Save metadata
        meta_path = cache_path / self.METADATA_FILE
        with open(meta_path, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)
        
        return CachedTemplate(
            path=cache_path,
            metadata=metadata
        )
    
    def invalidate(self, resolved: ResolvedTemplate) -> bool:
        """
        Invalidate a cached template.
        
        Args:
            resolved: Resolved template reference
            
        Returns:
            True if cache was invalidated, False if not found
        """
        cache_path = self._get_cache_path(resolved)
        if cache_path.exists():
            shutil.rmtree(cache_path)
            return True
        return False
    
    def clear(self, source: Optional[TemplateSource] = None) -> int:
        """
        Clear the cache.
        
        Args:
            source: If specified, only clear templates from this source
            
        Returns:
            Number of templates cleared
        """
        count = 0
        
        if source is None:
            # Clear everything
            if self.cache_dir.exists():
                for item in self.cache_dir.iterdir():
                    if item.is_dir():
                        count += sum(1 for _ in item.rglob(self.METADATA_FILE))
                        shutil.rmtree(item)
        else:
            # Clear specific source
            source_dir = self.cache_dir / source.value
            if source_dir.exists():
                count = sum(1 for _ in source_dir.rglob(self.METADATA_FILE))
                shutil.rmtree(source_dir)
        
        return count
    
    def list_cached(
        self,
        source: Optional[TemplateSource] = None
    ) -> list:
        """
        List all cached templates.
        
        Args:
            source: If specified, only list templates from this source
            
        Returns:
            List of (cache_path, metadata) tuples
        """
        results = []
        
        search_dirs = []
        if source is None:
            search_dirs = [
                self.cache_dir / s.value 
                for s in TemplateSource 
                if s != TemplateSource.LOCAL
            ]
        else:
            search_dirs = [self.cache_dir / source.value]
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            
            for meta_path in search_dir.rglob(self.METADATA_FILE):
                try:
                    with open(meta_path, "r") as f:
                        metadata = CacheMetadata.from_dict(json.load(f))
                    results.append((meta_path.parent, metadata))
                except (json.JSONDecodeError, IOError):
                    continue
        
        return results
    
    def get_cache_size(self) -> int:
        """Get total cache size in bytes."""
        if not self.cache_dir.exists():
            return 0
        return sum(f.stat().st_size for f in self.cache_dir.rglob("*") if f.is_file())


def clear_cache(source: Optional[str] = None) -> int:
    """
    Convenience function to clear the template cache.
    
    Args:
        source: Optional source type ('github', 'package', 'http')
        
    Returns:
        Number of templates cleared
    """
    cache = TemplateCache()
    source_enum = None
    if source:
        source_enum = TemplateSource(source)
    return cache.clear(source_enum)

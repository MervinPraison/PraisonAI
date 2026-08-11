"""
Template Cache

Disk-based caching for templates with TTL support.
Pinned versions are cached indefinitely, 'latest' has configurable TTL.
"""

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
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
    # Reserved subdirectory that in-flight put() writes are staged into. Kept
    # inside cache_dir (same filesystem, so os.replace stays atomic) but skipped
    # by clear()/list so a concurrent clear() can't rmtree a half-written entry.
    STAGING_DIR = ".staging"

    # Locks are keyed by the absolute cache path and shared *process-wide* (not
    # per-instance) so two independent ``TemplateCache`` objects pointing at the
    # same directory still serialise their destructive mutations against each
    # other. A per-instance dict would let a concurrent ``clear()`` on a second
    # instance rmtree a staging directory mid-``put()``.
    _KEY_LOCKS_GUARD = threading.Lock()
    _KEY_LOCKS: Dict[str, threading.Lock] = defaultdict(threading.Lock)

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

    @classmethod
    def _lock_for(cls, cache_path: Path) -> threading.Lock:
        """Return the process-wide lock guarding a single cache key.

        Shared across all instances so separate caches over the same directory
        coordinate their put/invalidate/clear/get on a given key.
        """
        with cls._KEY_LOCKS_GUARD:
            return cls._KEY_LOCKS[str(cache_path)]

    def _root_lock(self) -> threading.Lock:
        """Return the lock guarding whole-tree operations (``clear``)."""
        return self._lock_for(self.cache_dir)

    @contextmanager
    def _write_locks(self, cache_path: Path):
        """Hold the root lock then the per-key lock for a destructive write.

        The root lock serialises against ``clear()`` (which can rmtree a whole
        subtree); the per-key lock serialises against other writers and readers
        of the same key. Always acquired root-then-key so the ordering is
        consistent and can't deadlock against ``clear()``.
        """
        with self._root_lock(), self._lock_for(cache_path):
            yield

    def _ensure_cache_dir(self) -> None:
        """Ensure the cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_segment(value: str) -> str:
        if not value or ".." in value or "/" in value or "\\" in value:
            raise ValueError(f"Invalid cache path segment: {value!r}")
        return value
    
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
            ref = self._safe_segment(resolved.ref or "main")
            return (
                self.cache_dir / "github" / 
                self._safe_segment(resolved.owner) / self._safe_segment(resolved.repo) / 
                self._safe_segment(resolved.path) / ref
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

        # Read under the same per-key lock the writers hold so a reader never
        # observes the brief window between the two renames in put()/invalidate()
        # where cache_path is being pivoted out and the replacement installed.
        with self._lock_for(cache_path):
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
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Create metadata up front so it can be written into the staging dir
        # before the atomic install (readers never see a dir without metadata).
        metadata = CacheMetadata(
            fetched_at=time.time(),
            etag=etag,
            sha256=sha256,
            ttl_seconds=self.default_ttl,
            source_url=resolved.url if resolved.source == TemplateSource.HTTP else None,
            version=resolved.ref,
            is_pinned=resolved.is_pinned
        )

        # Stage the write into the reserved staging dir, then atomically swap it
        # into place. Readers keep seeing the old cache_path until os.replace()
        # runs, so a concurrent reader never observes a half-populated directory
        # or a partially written metadata file. Staging lives under cache_dir (so
        # os.replace is a same-filesystem atomic rename) but in a reserved
        # subdir that clear() skips, so a concurrent clear() can't delete it.
        staging_root = self.cache_dir / self.STAGING_DIR
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="stage_", dir=str(staging_root)))
        try:
            if content_dir.is_dir():
                for item in content_dir.iterdir():
                    if item.is_file():
                        shutil.copy2(item, staging / item.name)
                    elif item.is_dir():
                        shutil.copytree(item, staging / item.name)
            else:
                # Single file
                shutil.copy2(content_dir, staging / content_dir.name)

            with open(staging / self.METADATA_FILE, "w") as f:
                json.dump(metadata.to_dict(), f, indent=2)

            with self._write_locks(cache_path):
                # Re-create the parent under the lock in case a concurrent
                # clear() removed it after mkdtemp staged the write.
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                if cache_path.exists():
                    # Pivot the old entry out of the read path atomically, then
                    # delete it out-of-band so readers never race the rmtree.
                    trash = cache_path.with_name(cache_path.name + ".old")
                    shutil.rmtree(trash, ignore_errors=True)
                    os.replace(cache_path, trash)
                    shutil.rmtree(trash, ignore_errors=True)
                os.replace(staging, cache_path)  # atomic install
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

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
        with self._write_locks(cache_path):
            if cache_path.exists():
                # Pivot out of the read path before deleting so a concurrent
                # reader never races the rmtree on the live cache_path.
                trash = cache_path.with_name(cache_path.name + ".old")
                shutil.rmtree(trash, ignore_errors=True)
                os.replace(cache_path, trash)
                shutil.rmtree(trash, ignore_errors=True)
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

        # Hold the root lock so a whole-tree clear can't rmtree a directory (or
        # its parent) while a concurrent put() is staging/installing into it.
        with self._root_lock():
            if source is None:
                # Clear everything except the reserved staging dir, which may
                # hold a put() in flight on another thread.
                if self.cache_dir.exists():
                    for item in self.cache_dir.iterdir():
                        if item.is_dir() and item.name != self.STAGING_DIR:
                            count += sum(1 for _ in item.rglob(self.METADATA_FILE))
                            shutil.rmtree(item, ignore_errors=True)
            else:
                # Clear specific source
                source_dir = self.cache_dir / source.value
                if source_dir.exists():
                    count = sum(1 for _ in source_dir.rglob(self.METADATA_FILE))
                    shutil.rmtree(source_dir, ignore_errors=True)

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

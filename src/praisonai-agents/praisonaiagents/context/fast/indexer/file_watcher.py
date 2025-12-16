"""
File Watcher for Incremental Indexing.

Monitors file system changes and triggers incremental index updates:
- Watches for file creation, modification, deletion
- Debounces rapid changes
- Supports background indexing
"""

import os
import time
import logging
import threading
from typing import Dict, Set, Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Types of file system changes."""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class FileChange:
    """Represents a file system change.
    
    Attributes:
        path: Path to the changed file
        change_type: Type of change
        timestamp: When the change was detected
    """
    path: str
    change_type: ChangeType
    timestamp: float


class FileWatcher:
    """Watches for file system changes and triggers callbacks.
    
    Uses polling-based approach for cross-platform compatibility.
    For production use, consider using watchdog library.
    
    Attributes:
        workspace_path: Root directory to watch
        extensions: File extensions to watch
        poll_interval: Seconds between polls
    """
    
    def __init__(
        self,
        workspace_path: str,
        extensions: Optional[Set[str]] = None,
        poll_interval: float = 1.0,
        debounce_delay: float = 0.5,
        on_change: Optional[Callable[[FileChange], None]] = None
    ):
        """Initialize file watcher.
        
        Args:
            workspace_path: Root directory to watch
            extensions: File extensions to watch (None = all)
            poll_interval: Seconds between polls
            debounce_delay: Delay before processing changes
            on_change: Callback for file changes
        """
        self.workspace_path = os.path.abspath(workspace_path)
        self.extensions = extensions or {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.java',
            '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift'
        }
        self.poll_interval = poll_interval
        self.debounce_delay = debounce_delay
        self.on_change = on_change
        
        # State tracking
        self._file_mtimes: Dict[str, float] = {}
        self._pending_changes: Dict[str, FileChange] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def _scan_files(self) -> Dict[str, float]:
        """Scan workspace and get file modification times.
        
        Returns:
            Dict mapping file paths to modification times
        """
        mtimes = {}
        
        for root, dirs, files in os.walk(self.workspace_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in self.extensions:
                    file_path = os.path.join(root, filename)
                    try:
                        mtimes[file_path] = os.path.getmtime(file_path)
                    except OSError:
                        pass
        
        return mtimes
    
    def _detect_changes(self, new_mtimes: Dict[str, float]) -> None:
        """Detect changes between old and new file states.
        
        Args:
            new_mtimes: New file modification times
        """
        old_paths = set(self._file_mtimes.keys())
        new_paths = set(new_mtimes.keys())
        
        now = time.time()
        
        # Detect created files
        for path in new_paths - old_paths:
            self._add_pending_change(FileChange(
                path=path,
                change_type=ChangeType.CREATED,
                timestamp=now
            ))
        
        # Detect deleted files
        for path in old_paths - new_paths:
            self._add_pending_change(FileChange(
                path=path,
                change_type=ChangeType.DELETED,
                timestamp=now
            ))
        
        # Detect modified files
        for path in old_paths & new_paths:
            if new_mtimes[path] > self._file_mtimes[path]:
                self._add_pending_change(FileChange(
                    path=path,
                    change_type=ChangeType.MODIFIED,
                    timestamp=now
                ))
        
        self._file_mtimes = new_mtimes
    
    def _add_pending_change(self, change: FileChange) -> None:
        """Add a change to pending queue (with debouncing).
        
        Args:
            change: File change to add
        """
        with self._lock:
            self._pending_changes[change.path] = change
    
    def _process_pending_changes(self) -> None:
        """Process pending changes after debounce delay."""
        with self._lock:
            now = time.time()
            to_process = []
            
            for path, change in list(self._pending_changes.items()):
                if now - change.timestamp >= self.debounce_delay:
                    to_process.append(change)
                    del self._pending_changes[path]
        
        # Process changes outside lock
        for change in to_process:
            if self.on_change:
                try:
                    self.on_change(change)
                except Exception as e:
                    logger.error(f"Error processing change {change.path}: {e}")
    
    def _poll_loop(self) -> None:
        """Main polling loop."""
        # Initial scan
        self._file_mtimes = self._scan_files()
        
        while self._running:
            try:
                # Scan for changes
                new_mtimes = self._scan_files()
                self._detect_changes(new_mtimes)
                
                # Process pending changes
                self._process_pending_changes()
                
            except Exception as e:
                logger.error(f"Error in file watcher: {e}")
            
            time.sleep(self.poll_interval)
    
    def start(self) -> None:
        """Start watching for file changes."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(f"File watcher started for {self.workspace_path}")
    
    def stop(self) -> None:
        """Stop watching for file changes."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("File watcher stopped")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class IncrementalIndexer:
    """Manages incremental index updates based on file changes.
    
    Combines FileIndexer/SymbolIndexer with FileWatcher for
    automatic index updates when files change.
    """
    
    def __init__(
        self,
        workspace_path: str,
        file_indexer: Optional[Any] = None,
        symbol_indexer: Optional[Any] = None,
        poll_interval: float = 2.0
    ):
        """Initialize incremental indexer.
        
        Args:
            workspace_path: Root directory to index
            file_indexer: FileIndexer instance (optional)
            symbol_indexer: SymbolIndexer instance (optional)
            poll_interval: Seconds between file system polls
        """
        self.workspace_path = os.path.abspath(workspace_path)
        self.file_indexer = file_indexer
        self.symbol_indexer = symbol_indexer
        
        self._watcher = FileWatcher(
            workspace_path=workspace_path,
            poll_interval=poll_interval,
            on_change=self._handle_change
        )
        
        # Statistics
        self.changes_processed = 0
        self.last_change_time: Optional[float] = None
    
    def _handle_change(self, change: FileChange) -> None:
        """Handle a file change.
        
        Args:
            change: File change to process
        """
        rel_path = os.path.relpath(change.path, self.workspace_path)
        logger.debug(f"Processing {change.change_type.value}: {rel_path}")
        
        if change.change_type == ChangeType.DELETED:
            # Remove from indexes
            if self.file_indexer and hasattr(self.file_indexer, 'files'):
                self.file_indexer.files.pop(rel_path, None)
            if self.symbol_indexer and hasattr(self.symbol_indexer, 'symbols'):
                self.symbol_indexer.symbols.pop(rel_path, None)
        else:
            # Re-index the file
            if self.file_indexer and hasattr(self.file_indexer, 'index_file'):
                # FileIndexer doesn't have index_file, so we skip
                pass
            if self.symbol_indexer and hasattr(self.symbol_indexer, 'index_file'):
                self.symbol_indexer.index_file(change.path)
        
        self.changes_processed += 1
        self.last_change_time = time.time()
    
    def start(self) -> None:
        """Start incremental indexing."""
        # Initial full index
        if self.file_indexer:
            self.file_indexer.index()
        if self.symbol_indexer:
            self.symbol_indexer.index()
        
        # Start watching
        self._watcher.start()
    
    def stop(self) -> None:
        """Stop incremental indexing."""
        self._watcher.stop()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get indexer statistics.
        
        Returns:
            Dictionary with stats
        """
        stats = {
            "changes_processed": self.changes_processed,
            "last_change_time": self.last_change_time
        }
        
        if self.file_indexer:
            stats["file_indexer"] = self.file_indexer.get_stats()
        if self.symbol_indexer:
            stats["symbol_indexer"] = self.symbol_indexer.get_stats()
        
        return stats
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

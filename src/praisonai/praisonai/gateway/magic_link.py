"""
Magic-link authentication store for PraisonAI Gateway.

Provides HMAC-signed nonces with TTL, one-time consumption,
and file-locked JSON persistence for multi-worker safety.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)

try:
    import filelock
    FILELOCK_AVAILABLE = True
except ImportError:
    # Graceful fallback if filelock not available
    FILELOCK_AVAILABLE = False
    import threading
    
    # Module-level mapping from lock path to shared threading.Lock
    _locks_by_path: Dict[str, threading.Lock] = {}
    _locks_creation_lock = threading.Lock()
    
    class FileLock:
        """Fallback implementation using threading.Lock shared by path"""
        def __init__(self, path: str):
            self.path = path
            # Get or create a shared lock for this path
            with _locks_creation_lock:
                if path not in _locks_by_path:
                    _locks_by_path[path] = threading.Lock()
                self._lock = _locks_by_path[path]
        
        def __enter__(self):
            self._lock.acquire()
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            self._lock.release()


@dataclass
class MagicLinkEntry:
    """A magic link entry stored in the registry."""
    nonce: str
    created_at: float
    expires_at: float
    consumed: bool = False
    consumed_at: Optional[float] = None


class MagicLinkStore:
    """HMAC-signed magic link store with TTL and one-time consumption.
    
    Features:
    - HMAC-SHA256 signed nonces
    - 10-minute TTL by default
    - One-time consumption
    - File-locked JSON persistence
    - Multi-worker safe
    
    Example:
        store = MagicLinkStore()
        nonce = store.mint(ttl=600)  # 10 minutes
        
        # Later, in a request handler:
        if store.consume(nonce):
            # Proceed with authentication
            pass
        else:
            # Invalid or expired nonce
            pass
    """
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        storage_path: Optional[Union[str, Path]] = None,
        default_ttl: int = 600,  # 10 minutes
    ):
        """Initialize the magic link store.
        
        Args:
            secret_key: HMAC secret key (generated if not provided)
            storage_path: Path to JSON storage file (default: ~/.praisonai/magic-links.json)
            default_ttl: Default TTL in seconds (10 minutes)
        """
        self.secret_key = secret_key or self._get_or_create_secret()
        self.default_ttl = default_ttl
        
        # Storage setup
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            praisonai_home = Path(os.environ.get("PRAISONAI_HOME", Path.home() / ".praisonai"))
            self.storage_path = praisonai_home / "magic-links.json"
        
        # Ensure parent directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Set proper permissions
        try:
            os.chmod(self.storage_path.parent, 0o700)
        except (OSError, FileNotFoundError):
            pass
        
        # Thread safety
        self._local_lock = RLock()
        
        # Create file lock
        lock_path = str(self.storage_path) + ".lock"
        if FILELOCK_AVAILABLE:
            self._file_lock = filelock.FileLock(lock_path)
        else:
            self._file_lock = FileLock(lock_path)
    
    def _get_or_create_secret(self) -> str:
        """Get or create a persistent secret key for HMAC signing."""
        praisonai_home = Path(os.environ.get("PRAISONAI_HOME", Path.home() / ".praisonai"))
        secret_file = praisonai_home / ".magic-secret"
        
        praisonai_home.mkdir(parents=True, exist_ok=True)
        
        if secret_file.exists():
            try:
                secret = secret_file.read_text().strip()
                if secret and len(secret) >= 32:
                    return secret
            except (OSError, ValueError):
                pass
        
        # Generate new secret
        secret = secrets.token_hex(32)
        try:
            secret_file.write_text(secret)
            os.chmod(secret_file, 0o600)
        except OSError:
            pass
        
        return secret
    
    def _generate_nonce(self) -> str:
        """Generate a cryptographically secure nonce."""
        return secrets.token_hex(16)
    
    def _sign_nonce(self, nonce: str, timestamp: float) -> str:
        """Sign a nonce with HMAC-SHA256."""
        message = f"{nonce}:{timestamp}".encode()
        signature = hmac.new(
            self.secret_key.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _verify_nonce_signature(self, nonce: str, timestamp: float, signature: str) -> bool:
        """Verify a nonce signature."""
        expected = self._sign_nonce(nonce, timestamp)
        return hmac.compare_digest(expected, signature)
    
    def _load_entries(self) -> Dict[str, MagicLinkEntry]:
        """Load entries from storage."""
        try:
            if not self.storage_path.exists():
                return {}
            
            data = json.loads(self.storage_path.read_text())
            entries = {}
            for nonce, entry_data in data.items():
                # Handle legacy entries without expires_at field
                expires_at = entry_data.get("expires_at")
                if expires_at is None:
                    # Legacy entry, calculate expires_at from created_at and default_ttl
                    expires_at = entry_data["created_at"] + self.default_ttl
                
                entries[nonce] = MagicLinkEntry(
                    nonce=entry_data["nonce"],
                    created_at=entry_data["created_at"],
                    expires_at=expires_at,
                    consumed=entry_data.get("consumed", False),
                    consumed_at=entry_data.get("consumed_at"),
                )
            return entries
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return {}
    
    def _save_entries(self, entries: Dict[str, MagicLinkEntry]) -> bool:
        """Save entries to storage.
        
        Returns:
            True if successfully saved, False if failed
        """
        try:
            data = {}
            for nonce, entry in entries.items():
                data[nonce] = {
                    "nonce": entry.nonce,
                    "created_at": entry.created_at,
                    "expires_at": entry.expires_at,
                    "consumed": entry.consumed,
                    "consumed_at": entry.consumed_at,
                }
            
            # Write atomically with temp file
            temp_path = self.storage_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, indent=2))
            
            # Set permissions before moving
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            
            # Atomic rename
            os.replace(temp_path, self.storage_path)
            return True
            
        except OSError as e:
            logger.error(f"Failed to save magic link entries: {e}")
            return False
    
    def _cleanup_expired(self, entries: Dict[str, MagicLinkEntry]) -> Dict[str, MagicLinkEntry]:
        """Remove expired entries."""
        now = time.time()
        cleaned = {}
        for nonce, entry in entries.items():
            # Use stored expires_at for TTL check
            if now <= entry.expires_at:
                cleaned[nonce] = entry
        return cleaned
    
    def mint(self, ttl: Optional[int] = None) -> str:
        """Mint a new magic link nonce.
        
        Args:
            ttl: Time-to-live in seconds (uses default_ttl if not specified)
            
        Returns:
            HMAC-signed nonce string
        """
        ttl = ttl or self.default_ttl
        nonce = self._generate_nonce()
        timestamp = time.time()
        int_timestamp = int(timestamp)
        signature = self._sign_nonce(nonce, int_timestamp)
        
        # Combine into signed nonce
        signed_nonce = f"{nonce}.{int_timestamp}.{signature}"
        
        with self._local_lock:
            with self._file_lock:
                entries = self._load_entries()
                entries = self._cleanup_expired(entries)
                
                # Store the entry
                expires_at = timestamp + ttl
                entries[signed_nonce] = MagicLinkEntry(
                    nonce=signed_nonce,
                    created_at=timestamp,
                    expires_at=expires_at,
                )
                
                if not self._save_entries(entries):
                    raise OSError("Failed to persist magic link entry")
        
        return signed_nonce
    
    def consume(self, signed_nonce: str) -> bool:
        """Consume a magic link nonce.
        
        Args:
            signed_nonce: The signed nonce to consume
            
        Returns:
            True if successfully consumed, False if invalid/expired/already used
        """
        if not signed_nonce:
            return False
        
        try:
            parts = signed_nonce.split(".")
            if len(parts) != 3:
                return False
            
            nonce, timestamp_str, signature = parts
            timestamp = int(timestamp_str)
            
            # Verify signature
            if not self._verify_nonce_signature(nonce, timestamp, signature):
                return False
            
            with self._local_lock:
                with self._file_lock:
                    entries = self._load_entries()
                    entries = self._cleanup_expired(entries)
                    
                    entry = entries.get(signed_nonce)
                    if not entry:
                        # Entry not found, but nonce is valid and not expired
                        # This shouldn't happen in normal operation, but let's be defensive
                        return False
                    
                    # Check TTL using stored expires_at
                    now = time.time()
                    if now > entry.expires_at:
                        return False
                    
                    if entry.consumed:
                        return False
                    
                    # Mark as consumed
                    entry.consumed = True
                    entry.consumed_at = now
                    
                    if not self._save_entries(entries):
                        return False  # Failed to persist consumed state
                    
            return True
            
        except (ValueError, TypeError):
            return False
    
    def revoke(self, signed_nonce: str) -> bool:
        """Revoke a magic link nonce.
        
        Args:
            signed_nonce: The signed nonce to revoke
            
        Returns:
            True if successfully revoked, False if not found
        """
        with self._local_lock:
            with self._file_lock:
                entries = self._load_entries()
                if signed_nonce in entries:
                    del entries[signed_nonce]
                    self._save_entries(entries)
                    return True
                return False
    
    def list_active(self) -> list:
        """List all active (non-consumed, non-expired) nonces.
        
        Returns:
            List of active signed nonces
        """
        with self._local_lock:
            with self._file_lock:
                entries = self._load_entries()
                entries = self._cleanup_expired(entries)
                
                active = []
                for nonce, entry in entries.items():
                    if not entry.consumed:
                        active.append(nonce)
                
                return active
    
    def cleanup(self) -> int:
        """Clean up expired and consumed entries.
        
        Returns:
            Number of entries cleaned up
        """
        with self._local_lock:
            with self._file_lock:
                entries = self._load_entries()
                original_count = len(entries)
                
                # Keep only non-expired, non-consumed entries
                now = time.time()
                cleaned = {}
                for nonce, entry in entries.items():
                    if (now <= entry.expires_at and 
                        not entry.consumed):
                        cleaned[nonce] = entry
                
                self._save_entries(cleaned)
                return original_count - len(cleaned)
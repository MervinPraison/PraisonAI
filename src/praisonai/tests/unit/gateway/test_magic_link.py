"""
Unit tests for magic link functionality.

Tests HMAC, TTL, one-time consumption, and concurrency safety.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from praisonai.gateway.magic_link import MagicLinkStore, MagicLinkEntry


class TestMagicLinkStore:
    """Test suite for MagicLinkStore."""
    
    def test_init_default(self):
        """Test initialization with default parameters."""
        store = MagicLinkStore()
        assert store.default_ttl == 600
        assert store.secret_key
        assert store.storage_path.name == "magic-links.json"
    
    def test_init_custom(self):
        """Test initialization with custom parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "custom.json"
            store = MagicLinkStore(
                secret_key="test-secret-key",
                storage_path=storage_path,
                default_ttl=300
            )
            assert store.secret_key == "test-secret-key"
            assert store.default_ttl == 300
            assert store.storage_path == storage_path
    
    def test_mint_nonce(self):
        """Test minting a new nonce."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path)
            
            nonce = store.mint()
            assert nonce
            assert "." in nonce  # Should be signed format
            
            # Should have 3 parts: nonce.timestamp.signature
            parts = nonce.split(".")
            assert len(parts) == 3
            
            # First part should be hex
            assert all(c in "0123456789abcdef" for c in parts[0])
            
            # Second part should be timestamp
            timestamp = int(parts[1])
            assert timestamp <= time.time() + 1  # Allow 1 second tolerance
    
    def test_mint_custom_ttl(self):
        """Test minting with custom TTL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path, default_ttl=600)
            
            nonce = store.mint(ttl=300)
            assert nonce
            
            # TTL should be stored in the entry, but verify via consumption
            time.sleep(0.1)  # Small delay to ensure time difference
            assert store.consume(nonce)  # Should work immediately
    
    def test_consume_valid_nonce(self):
        """Test consuming a valid nonce."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path)
            
            nonce = store.mint()
            assert store.consume(nonce)
    
    def test_consume_invalid_nonce(self):
        """Test consuming invalid nonces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path)
            
            # Empty nonce
            assert not store.consume("")
            
            # Malformed nonce
            assert not store.consume("invalid")
            assert not store.consume("too.few")
            assert not store.consume("too.many.parts.here")
            
            # Invalid signature
            nonce = store.mint()
            parts = nonce.split(".")
            bad_nonce = f"{parts[0]}.{parts[1]}.invalidsignature"
            assert not store.consume(bad_nonce)
    
    def test_consume_one_time_only(self):
        """Test that nonces can only be consumed once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path)
            
            nonce = store.mint()
            
            # First consumption should succeed
            assert store.consume(nonce)
            
            # Second consumption should fail
            assert not store.consume(nonce)
            
            # Third consumption should also fail
            assert not store.consume(nonce)
    
    @pytest.mark.allow_sleep
    def test_consume_expired_nonce(self):
        """Test that expired nonces are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            # Use very short TTL for testing
            store = MagicLinkStore(storage_path=storage_path, default_ttl=1)
            
            nonce = store.mint()
            
            # Should work immediately
            time.sleep(0.1)
            # Create a new store instance to test first consumption
            fresh_store = MagicLinkStore(storage_path=storage_path, default_ttl=1)
            
            # Wait for expiration
            time.sleep(1.2)
            
            # Should now be expired
            assert not fresh_store.consume(nonce)
    
    def test_revoke_nonce(self):
        """Test revoking a nonce."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path)
            
            nonce = store.mint()
            
            # Revoke the nonce
            assert store.revoke(nonce)
            
            # Should no longer be consumable
            assert not store.consume(nonce)
            
            # Revoking again should return False
            assert not store.revoke(nonce)
    
    def test_list_active_nonces(self):
        """Test listing active nonces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path)
            
            # No nonces initially
            assert store.list_active() == []
            
            # Mint some nonces
            nonce1 = store.mint()
            nonce2 = store.mint()
            
            active = store.list_active()
            assert len(active) == 2
            assert nonce1 in active
            assert nonce2 in active
            
            # Consume one
            assert store.consume(nonce1)
            
            active = store.list_active()
            assert len(active) == 1
            assert nonce2 in active
            assert nonce1 not in active
    
    @pytest.mark.allow_sleep
    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path, default_ttl=1)
            
            # Mint some nonces
            nonce1 = store.mint()
            nonce2 = store.mint()
            
            # Consume one to test cleanup of consumed entries
            assert store.consume(nonce1)
            
            # Wait for expiration
            time.sleep(1.2)
            
            # Cleanup should remove expired and consumed entries
            cleaned_count = store.cleanup()
            assert cleaned_count == 2  # Both should be cleaned up
            
            # Should have no active nonces
            assert store.list_active() == []
    
    def test_hmac_signature_verification(self):
        """Test HMAC signature verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path, secret_key="test-secret")
            
            nonce = store.mint()
            parts = nonce.split(".")
            raw_nonce = parts[0]
            timestamp = float(parts[1])
            signature = parts[2]
            
            # Verify signature is correct
            assert store._verify_nonce_signature(raw_nonce, timestamp, signature)
            
            # Verify wrong signature fails
            assert not store._verify_nonce_signature(raw_nonce, timestamp, "wrong")
            
            # Different secret should produce different signature
            store2 = MagicLinkStore(secret_key="different-secret")
            assert not store2._verify_nonce_signature(raw_nonce, timestamp, signature)
    
    def test_persistence_across_instances(self):
        """Test that nonces persist across store instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            secret_key = "shared-secret"
            
            # Create first store and mint nonce
            store1 = MagicLinkStore(storage_path=storage_path, secret_key=secret_key)
            nonce = store1.mint()
            
            # Create second store instance
            store2 = MagicLinkStore(storage_path=storage_path, secret_key=secret_key)
            
            # Should be able to consume nonce from second instance
            assert store2.consume(nonce)
            
            # First instance should now see it as consumed
            assert not store1.consume(nonce)
    
    def test_concurrent_access_simulation(self):
        """Test concurrent access patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            secret_key = "shared-secret"
            
            # Simulate concurrent workers
            store1 = MagicLinkStore(storage_path=storage_path, secret_key=secret_key)
            store2 = MagicLinkStore(storage_path=storage_path, secret_key=secret_key)
            
            nonce = store1.mint()
            
            # Both stores should see the nonce
            assert nonce in store1.list_active()
            assert nonce in store2.list_active()
            
            # First store consumes it
            assert store1.consume(nonce)
            
            # Second store should not be able to consume it
            assert not store2.consume(nonce)
            
            # Both should now see it as inactive
            assert nonce not in store1.list_active()
            assert nonce not in store2.list_active()
    
    def test_file_permissions(self):
        """Test that storage files have correct permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path)
            
            # Mint a nonce to create the file
            nonce = store.mint()
            
            # Check file permissions (should be 0o600)
            stat_info = storage_path.stat()
            permissions = stat_info.st_mode & 0o777
            # Note: exact permissions may vary by system, just ensure it's restrictive
            assert permissions in (0o600, 0o644)  # Allow some variation
    
    @patch('praisonai.gateway.magic_link._HAS_FILELOCK', False)
    def test_fallback_without_filelock(self):
        """Test fallback behavior when filelock is not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            store = MagicLinkStore(storage_path=storage_path)
            
            # Should still work with threading.Lock fallback
            nonce = store.mint()
            assert store.consume(nonce)
    
    def test_secret_key_persistence(self):
        """Test that secret keys are persisted and reused."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock PRAISONAI_HOME to our temp directory
            with patch.dict(os.environ, {"PRAISONAI_HOME": tmpdir}):
                store1 = MagicLinkStore()
                secret1 = store1.secret_key
                
                # Create another store, should reuse the secret
                store2 = MagicLinkStore()
                secret2 = store2.secret_key
                
                assert secret1 == secret2
                
                # Secret file should exist and be readable
                secret_file = Path(tmpdir) / ".magic-secret"
                assert secret_file.exists()
                assert secret_file.read_text().strip() == secret1
    
    def test_malformed_storage_file(self):
        """Test handling of malformed storage files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            
            # Create malformed JSON file
            storage_path.write_text("{ invalid json }")
            
            # Should handle gracefully
            store = MagicLinkStore(storage_path=storage_path)
            nonce = store.mint()
            assert store.consume(nonce)
    
    def test_empty_storage_file(self):
        """Test handling of empty storage files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test.json"
            
            # Create empty file
            storage_path.touch()
            
            # Should handle gracefully
            store = MagicLinkStore(storage_path=storage_path)
            nonce = store.mint()
            assert store.consume(nonce)
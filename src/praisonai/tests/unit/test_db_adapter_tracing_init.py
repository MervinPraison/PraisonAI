"""
Unit tests for PraisonAIDB adapter tracing hooks store initialization.

Tests that all tracing hooks (_init_stores() calls) prevent silent data loss
by ensuring stores are initialized before any write operations.
"""

import unittest
from unittest.mock import Mock, patch
import time


class TestPraisonAIDBTracingInit(unittest.TestCase):
    """Test that tracing hooks properly initialize stores before use."""

    def setUp(self):
        """Set up test fixtures."""
        from praisonai.db.adapter import PraisonAIDB
        self.db = PraisonAIDB()
        
    def test_on_trace_start_calls_init_stores(self):
        """Test that on_trace_start calls _init_stores() before writing."""
        # Mock _init_stores to track calls
        with patch.object(self.db, '_init_stores') as mock_init:
            # Mock _state_store to prevent actual writes
            self.db._state_store = Mock()
            
            # Call tracing hook
            self.db.on_trace_start(
                trace_id="test-trace",
                session_id="test-session",
                agent_name="test-agent"
            )
            
            # Verify _init_stores was called before accessing _state_store
            mock_init.assert_called_once()
            self.db._state_store.set.assert_called_once()

    def test_on_trace_end_calls_init_stores(self):
        """Test that on_trace_end calls _init_stores() before writing."""
        with patch.object(self.db, '_init_stores') as mock_init:
            self.db._state_store = Mock()
            self.db._state_store.get.return_value = {"metadata": {}}
            
            self.db.on_trace_end(
                trace_id="test-trace",
                status="completed"
            )
            
            mock_init.assert_called_once()
            self.db._state_store.get.assert_called_once()
            self.db._state_store.set.assert_called_once()

    def test_on_span_start_calls_init_stores(self):
        """Test that on_span_start calls _init_stores() before writing."""
        with patch.object(self.db, '_init_stores') as mock_init:
            self.db._state_store = Mock()
            
            self.db.on_span_start(
                span_id="test-span",
                trace_id="test-trace",
                name="test-operation"
            )
            
            mock_init.assert_called_once()
            self.db._state_store.set.assert_called_once()

    def test_on_span_end_calls_init_stores(self):
        """Test that on_span_end calls _init_stores() before writing."""
        with patch.object(self.db, '_init_stores') as mock_init:
            self.db._state_store = Mock()
            self.db._state_store.get.return_value = {"attributes": {}}
            
            self.db.on_span_end(
                span_id="test-span",
                status="completed"
            )
            
            mock_init.assert_called_once()
            self.db._state_store.get.assert_called_once()
            self.db._state_store.set.assert_called_once()

    def test_tracing_hooks_prevent_silent_data_loss(self):
        """Test that tracing hooks prevent silent data loss when stores not initialized."""
        # Test scenario where _init_stores() is critical
        # Start with uninitialized adapter (no stores configured)
        db = self.db
        self.assertIsNone(db._state_store)
        self.assertFalse(db._initialized)
        
        # Mock _init_stores to simulate successful initialization
        def mock_init():
            db._state_store = Mock()
            db._initialized = True
        
        with patch.object(db, '_init_stores', side_effect=mock_init):
            # Call tracing hook - should not fail silently
            db.on_trace_start("trace1", session_id="session1")
            
            # Verify store was initialized and data was written
            self.assertIsNotNone(db._state_store)
            self.assertTrue(db._initialized)
            db._state_store.set.assert_called_once()

    def test_init_stores_idempotent(self):
        """Test that _init_stores() can be called multiple times safely."""
        # Configure minimal database URLs
        db = self.db
        db._state_url = "memory://"
        
        # Mock the store creation to avoid actual dependencies
        with patch('praisonai.persistence.factory.create_state_store') as mock_create:
            mock_store = Mock()
            mock_create.return_value = mock_store
            
            # Call _init_stores multiple times
            db._init_stores()
            db._init_stores()
            db._init_stores()
            
            # Should only initialize once due to idempotent behavior
            self.assertTrue(db._initialized)
            self.assertEqual(db._state_store, mock_store)

    def test_tracing_without_state_url_graceful_degradation(self):
        """Test that tracing hooks degrade gracefully when no state_url configured."""
        # No state_url configured - tracing should not crash
        db = self.db
        self.assertIsNone(db._state_url)
        
        # These should not raise exceptions
        db.on_trace_start("trace1")
        db.on_trace_end("trace1")
        db.on_span_start("span1", "trace1", "operation")
        db.on_span_end("span1")
        
        # Store should remain None (graceful degradation)
        self.assertIsNone(db._state_store)


if __name__ == '__main__':
    unittest.main()
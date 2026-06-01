"""
Tests for the Session Hierarchy module.

TDD: Tests for parent-child sessions, forking, snapshots, and revert.
"""

import os
import shutil
import tempfile
import time

from praisonaiagents.session.hierarchy import (
    HierarchicalSessionStore,
    ExtendedSessionData,
    SessionSnapshot,
    get_hierarchical_session_store,
)


class TestSessionSnapshot:
    """Tests for SessionSnapshot."""
    
    def test_snapshot_creation(self):
        """Test basic snapshot creation."""
        snapshot = SessionSnapshot(
            session_id="session_123",
            message_index=5,
            label="Before refactor"
        )
        
        assert snapshot.session_id == "session_123"
        assert snapshot.message_index == 5
        assert snapshot.label == "Before refactor"
        assert snapshot.id is not None
    
    def test_snapshot_serialization(self):
        """Test snapshot round-trip."""
        snapshot = SessionSnapshot(
            session_id="session_123",
            message_index=5,
            label="Test"
        )
        
        d = snapshot.to_dict()
        restored = SessionSnapshot.from_dict(d)
        
        assert restored.session_id == snapshot.session_id
        assert restored.message_index == snapshot.message_index
        assert restored.label == snapshot.label


class TestExtendedSessionData:
    """Tests for ExtendedSessionData."""
    
    def test_extended_session_creation(self):
        """Test extended session creation."""
        session = ExtendedSessionData(
            session_id="session_123",
            title="Test Session",
            parent_id="parent_123"
        )
        
        assert session.session_id == "session_123"
        assert session.title == "Test Session"
        assert session.parent_id == "parent_123"
        assert session.children_ids == []
        assert session.snapshots == []
    
    def test_extended_session_serialization(self):
        """Test extended session round-trip."""
        session = ExtendedSessionData(
            session_id="session_123",
            title="Test",
            parent_id="parent_123",
            children_ids=["child_1", "child_2"],
            is_shared=True,
        )
        session.snapshots.append(SessionSnapshot(
            session_id="session_123",
            message_index=3
        ))
        
        d = session.to_dict()
        restored = ExtendedSessionData.from_dict(d)
        
        assert restored.session_id == session.session_id
        assert restored.title == session.title
        assert restored.parent_id == session.parent_id
        assert restored.children_ids == session.children_ids
        assert restored.is_shared == session.is_shared
        assert len(restored.snapshots) == 1


class TestHierarchicalSessionStore:
    """Tests for HierarchicalSessionStore."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = HierarchicalSessionStore(session_dir=self.temp_dir)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_message_preserves_concurrent_writes(self):
        """Concurrent add_message must not lose messages (same as DefaultSessionStore)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = HierarchicalSessionStore(session_dir=tmpdir)
            reader = HierarchicalSessionStore(session_dir=tmpdir)

            writer.add_user_message("session-1", "first")
            reader._load_session("session-1")
            writer.add_user_message("session-1", "second")

            history = writer.get_chat_history("session-1")
            assert len(history) == 2
            assert history[1]["content"] == "second"

    def test_get_extended_session_sees_writes_from_other_store(self):
        """Extended reads must reload from disk, not stale _extended_cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = HierarchicalSessionStore(session_dir=tmpdir)
            reader = HierarchicalSessionStore(session_dir=tmpdir)

            writer.add_user_message("session-1", "first")
            reader._load_extended_session("session-1")
            writer.add_user_message("session-1", "second")

            session = reader.get_extended_session("session-1")
            assert len(session.messages) == 2
            assert session.messages[1].content == "second"

    def test_stale_cache_write_preserves_concurrent_updates(self):
        """Metadata writes must not overwrite concurrent message additions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = HierarchicalSessionStore(session_dir=tmpdir)
            reader = HierarchicalSessionStore(session_dir=tmpdir)

            # Writer creates session and adds initial message
            session_id = writer.create_session(title="Test")
            writer.add_user_message(session_id, "first")
            
            # Reader loads (warms cache)
            reader.get_extended_session(session_id)
            
            # Writer adds another message
            writer.add_user_message(session_id, "second")
            
            # Reader calls set_title (metadata write) - should not lose "second" message
            reader.set_title(session_id, "Updated Title")
            
            # Verify both messages preserved
            final_session = writer.get_extended_session(session_id)
            assert len(final_session.messages) == 2
            assert final_session.messages[1].content == "second"
            assert final_session.title == "Updated Title"

    def test_update_session_metadata_preserves_extended_fields(self):
        """Metadata updates must not strip parent_id, snapshots, etc."""
        session_id = self.store.create_session(title="Parent")
        self.store.add_message(session_id, "user", "hello")
        parent_id = self.store.create_session(title="Child", parent_id=session_id)
        snapshot_id = self.store.create_snapshot(session_id, label="checkpoint")

        assert self.store.update_session_metadata(session_id, model="gpt-4o-mini")

        session = self.store.get_extended_session(session_id)
        assert session.metadata.get("model") == "gpt-4o-mini"
        assert session.title == "Parent"
        assert parent_id in session.children_ids
        assert any(s.id == snapshot_id for s in session.snapshots)

    def test_create_session(self):
        """Test creating a session."""
        session_id = self.store.create_session(title="Test Session")
        
        assert session_id is not None
        session = self.store.get_extended_session(session_id)
        assert session.title == "Test Session"
    
    def test_create_session_with_parent(self):
        """Test creating a session with a parent."""
        parent_id = self.store.create_session(title="Parent")
        child_id = self.store.create_session(title="Child", parent_id=parent_id)
        
        child = self.store.get_extended_session(child_id)
        parent = self.store.get_extended_session(parent_id)
        
        assert child.parent_id == parent_id
        assert child_id in parent.children_ids
    
    def test_fork_session(self):
        """Test forking a session."""
        # Create parent with messages
        parent_id = self.store.create_session(title="Parent")
        self.store.add_message(parent_id, "user", "Message 1")
        self.store.add_message(parent_id, "assistant", "Response 1")
        self.store.add_message(parent_id, "user", "Message 2")
        self.store.add_message(parent_id, "assistant", "Response 2")
        
        # Fork from message index 1 (after first response)
        forked_id = self.store.fork_session(parent_id, from_message_index=1)
        
        forked = self.store.get_extended_session(forked_id)
        parent = self.store.get_extended_session(parent_id)
        
        assert forked.parent_id == parent_id
        assert len(forked.messages) == 2  # Only first 2 messages
        assert forked_id in parent.children_ids
    
    def test_fork_session_all_messages(self):
        """Test forking with all messages."""
        parent_id = self.store.create_session(title="Parent")
        self.store.add_message(parent_id, "user", "Message 1")
        self.store.add_message(parent_id, "assistant", "Response 1")
        
        forked_id = self.store.fork_session(parent_id)  # No index = all messages
        
        forked = self.store.get_extended_session(forked_id)
        assert len(forked.messages) == 2
    
    def test_get_children(self):
        """Test getting child sessions."""
        parent_id = self.store.create_session(title="Parent")
        child1_id = self.store.create_session(title="Child 1", parent_id=parent_id)
        child2_id = self.store.create_session(title="Child 2", parent_id=parent_id)
        
        children = self.store.get_children(parent_id)
        
        assert len(children) == 2
        assert child1_id in children
        assert child2_id in children
    
    def test_get_parent(self):
        """Test getting parent session."""
        parent_id = self.store.create_session(title="Parent")
        child_id = self.store.create_session(title="Child", parent_id=parent_id)
        
        assert self.store.get_parent(child_id) == parent_id
        assert self.store.get_parent(parent_id) is None
    
    def test_get_session_tree(self):
        """Test getting session tree."""
        parent_id = self.store.create_session(title="Parent")
        child1_id = self.store.create_session(title="Child 1", parent_id=parent_id)
        child2_id = self.store.create_session(title="Child 2", parent_id=parent_id)
        grandchild_id = self.store.create_session(title="Grandchild", parent_id=child1_id)
        
        tree = self.store.get_session_tree(parent_id)
        
        assert tree["session_id"] == parent_id
        assert len(tree["children"]) == 2
        
        # Find child1 in tree
        child1_tree = next(c for c in tree["children"] if c["session_id"] == child1_id)
        assert len(child1_tree["children"]) == 1
        assert child1_tree["children"][0]["session_id"] == grandchild_id
    
    def test_create_snapshot(self):
        """Test creating a snapshot."""
        session_id = self.store.create_session(title="Test")
        self.store.add_message(session_id, "user", "Message 1")
        self.store.add_message(session_id, "assistant", "Response 1")
        
        snapshot_id = self.store.create_snapshot(session_id, label="Checkpoint 1")
        
        snapshots = self.store.get_snapshots(session_id)
        assert len(snapshots) == 1
        assert snapshots[0].id == snapshot_id
        assert snapshots[0].label == "Checkpoint 1"
        assert snapshots[0].message_index == 1
    
    def test_revert_to_snapshot(self):
        """Test reverting to a snapshot."""
        session_id = self.store.create_session(title="Test")
        self.store.add_message(session_id, "user", "Message 1")
        self.store.add_message(session_id, "assistant", "Response 1")
        
        snapshot_id = self.store.create_snapshot(session_id, label="Checkpoint")
        
        self.store.add_message(session_id, "user", "Message 2")
        self.store.add_message(session_id, "assistant", "Response 2")
        
        # Force reload to get latest messages
        session = self.store._load_extended_session(session_id, force_reload=True)
        assert len(session.messages) == 4
        
        # Revert
        result = self.store.revert_to_snapshot(session_id, snapshot_id)
        assert result is True
        
        # Force reload and check
        session = self.store._load_extended_session(session_id, force_reload=True)
        assert len(session.messages) == 2
    
    def test_revert_to_message(self):
        """Test reverting to a specific message."""
        session_id = self.store.create_session(title="Test")
        self.store.add_message(session_id, "user", "Message 1")
        self.store.add_message(session_id, "assistant", "Response 1")
        self.store.add_message(session_id, "user", "Message 2")
        self.store.add_message(session_id, "assistant", "Response 2")
        
        result = self.store.revert_to_message(session_id, 1)
        assert result is True
        
        self.store.invalidate_cache(session_id)
        self.store._extended_cache.pop(session_id, None)
        session = self.store.get_extended_session(session_id)
        assert len(session.messages) == 2
    
    def test_share_unshare_session(self):
        """Test sharing and unsharing sessions."""
        session_id = self.store.create_session(title="Test")
        
        assert self.store.is_shared(session_id) is False
        
        self.store.share_session(session_id)
        assert self.store.is_shared(session_id) is True
        
        self.store.unshare_session(session_id)
        assert self.store.is_shared(session_id) is False
    
    def test_set_title(self):
        """Test setting session title."""
        session_id = self.store.create_session(title="Original")
        
        self.store.set_title(session_id, "Updated Title")
        
        session = self.store.get_extended_session(session_id)
        assert session.title == "Updated Title"
    
    def test_export_import_session(self):
        """Test exporting and importing sessions."""
        # Create session with data
        session_id = self.store.create_session(title="Export Test")
        # Set title explicitly after creation
        self.store.set_title(session_id, "Export Test")
        self.store.add_message(session_id, "user", "Hello")
        self.store.add_message(session_id, "assistant", "Hi there!")
        
        # Export (force reload to get all data)
        exported = self.store.export_session(session_id)
        
        assert exported["title"] == "Export Test"
        assert len(exported["messages"]) == 2
        
        # Import to new session
        new_id = self.store.import_session(exported)
        
        new_session = self.store.get_extended_session(new_id)
        assert new_session.title == "Export Test"
        assert len(new_session.messages) == 2
        assert new_session.parent_id is None  # Cleared on import
    
    def test_export_import_with_custom_id(self):
        """Test importing with custom session ID."""
        session_id = self.store.create_session(title="Test")
        exported = self.store.export_session(session_id)
        
        custom_id = "custom-imported-session"
        new_id = self.store.import_session(exported, new_session_id=custom_id)
        
        assert new_id == custom_id
    
    def test_set_title_does_not_drop_messages_after_external_write(self):
        """
        Regression test for the stale cache bug.
        
        Reproduces the scenario where:
        1. Process A loads session (warms cache)
        2. Process B writes new messages
        3. Process A calls set_title() → should NOT drop Process B's messages
        """
        import json
        
        # Create session with initial messages
        session_id = self.store.create_session(title="Test Session")
        self.store.add_message(session_id, "user", "Message 1")
        self.store.add_message(session_id, "assistant", "Response 1")
        
        # Process A: Load session (warms cache)
        session_a = self.store.get_extended_session(session_id)
        assert len(session_a.messages) == 2
        
        # Process B: Simulate external write by directly modifying file
        # This mimics another process/store instance writing to the same session
        filepath = self.store._get_session_path(session_id)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Add messages from "Process B"
        data["messages"].extend([
            {"role": "user", "content": "Message 2", "timestamp": time.time(), "metadata": {}},
            {"role": "assistant", "content": "Response 2", "timestamp": time.time(), "metadata": {}}
        ])
        data["updated_at"] = time.time()
        
        # Write the updated data (simulating external process write)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # Brief sleep to ensure file mtime is different
        time.sleep(0.1)
        
        # Process A: Call set_title() - this should detect the external write
        # and reload fresh data instead of using stale cache
        result = self.store.set_title(session_id, "Updated Title")
        assert result is True
        
        # Verify no messages were lost - should have all 4 messages
        final_session = self.store.get_extended_session(session_id)
        assert len(final_session.messages) == 4, f"Expected 4 messages, got {len(final_session.messages)}"
        assert final_session.title == "Updated Title"
        assert final_session.messages[0].content == "Message 1"
        assert final_session.messages[1].content == "Response 1"
        assert final_session.messages[2].content == "Message 2"
        assert final_session.messages[3].content == "Response 2"
    
    def test_cache_performance_with_unchanged_files(self):
        """
        Test that performance optimization works - reads from cache when file hasn't changed.
        """
        session_id = self.store.create_session(title="Cache Test")
        self.store.add_message(session_id, "user", "Test message")
        
        # First read - loads from disk and caches
        session1 = self.store.get_extended_session(session_id)
        assert len(session1.messages) == 1
        
        # Second read should use cache (file hasn't changed)
        # We can't easily test this directly, but we can verify the cache is valid
        assert self.store._is_cache_valid(session_id) is True
        
        session2 = self.store.get_extended_session(session_id)
        assert len(session2.messages) == 1
        assert session2 is session1  # Should be same cached object
    
    def test_force_reload_bypasses_cache(self):
        """Test that force_reload=True always loads from disk."""
        session_id = self.store.create_session(title="Force Reload Test")
        self.store.add_message(session_id, "user", "Message 1")
        
        # Load and cache
        session1 = self.store._load_extended_session(session_id, force_reload=False)
        
        # Force reload should bypass cache
        session2 = self.store._load_extended_session(session_id, force_reload=True)
        
        # Both should have same data but force_reload ensures fresh read
        assert len(session1.messages) == len(session2.messages)
        assert session1.session_id == session2.session_id


class TestGlobalHierarchicalStore:
    """Tests for global hierarchical store."""
    
    def test_get_hierarchical_session_store(self):
        """Test getting global store."""
        store = get_hierarchical_session_store()
        
        assert isinstance(store, HierarchicalSessionStore)
    
    def test_singleton_behavior(self):
        """Test that global store is a singleton."""
        store1 = get_hierarchical_session_store()
        store2 = get_hierarchical_session_store()
        
        assert store1 is store2

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

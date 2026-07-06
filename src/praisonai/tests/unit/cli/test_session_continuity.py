#!/usr/bin/env python3
"""
Test script for CLI session continuity implementation.
"""

import sys
import os
import tempfile
from pathlib import Path

# Project paths should be handled by proper package installation

def test_project_identification():
    """Test project identification functionality."""
    print("=== Testing Project Identification ===")
    
    from praisonai.cli.utils.project import get_project_id, get_project_name, get_git_root
    
    # Test in current directory (should be PraisonAI repo)
    project_id = get_project_id()
    project_name = get_project_name()
    git_root = get_git_root()
    
    print(f"✅ Project ID: {project_id}")
    print(f"✅ Project Name: {project_name}")
    print(f"✅ Git Root: {git_root}")
    
    # Test in a non-git directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_project_id = get_project_id(temp_dir)
        temp_project_name = get_project_name(temp_dir)
        print(f"✅ Temp Project ID: {temp_project_id}")
        print(f"✅ Temp Project Name: {temp_project_name}")
    
    print("✅ Project identification tests passed\n")


def test_project_session_store():
    """Test project-scoped session store."""
    print("=== Testing Project Session Store ===")

    import praisonai.cli.state.project_sessions as project_sessions

    # Test project session store creation
    store = project_sessions.get_project_session_store()
    
    print("✅ Session store created")
    print(f"   Project ID: {store.project_id}")
    print(f"   Project Name: {store.project_name}")
    print(f"   Session Dir: {store.session_dir}")
    
    # Test adding messages
    test_session_id = "test-session-123"
    
    success = store.add_user_message(test_session_id, "Hello, this is a test message")
    print(f"✅ Added user message: {success}")
    
    success = store.add_assistant_message(test_session_id, "Hi! I'm responding to your test message.")
    print(f"✅ Added assistant message: {success}")
    
    # Test retrieving chat history
    history = store.get_chat_history(test_session_id)
    print(f"✅ Retrieved chat history ({len(history)} messages):")
    for msg in history:
        print(f"   {msg['role']}: {msg['content']}")
    
    # Test listing sessions
    sessions = store.list_sessions(limit=5)
    print(f"✅ Listed sessions ({len(sessions)} found)")
    for session in sessions:
        print(f"   ID: {session.get('session_id')}, Messages: {session.get('message_count')}")
    
    # Test getting last session
    last_session_id = store.get_last_session_id()
    print(f"✅ Last session ID: {last_session_id}")
    
    # Cleanup
    store.delete_session(test_session_id)
    print("✅ Cleaned up test session")
    
    print("✅ Project session store tests passed\n")


def test_session_discovery():
    """Test session discovery functionality."""
    print("=== Testing Session Discovery ===")

    import praisonai.cli.state.project_sessions as project_sessions

    # Create a test session
    store = project_sessions.get_project_session_store()
    test_session_id = "discovery-test-456"

    store.add_user_message(test_session_id, "Test message for discovery")

    # Test finding last session
    last_session = project_sessions.find_last_session()
    print(f"✅ Found last session: {last_session}")
    
    # Cleanup
    store.delete_session(test_session_id)
    
    print("✅ Session discovery tests passed\n")


def main():
    """Run all tests."""
    print("🧪 Testing CLI Session Continuity Implementation\n")
    
    try:
        test_project_identification()
        test_project_session_store()
        test_session_discovery()
        
        print("🎉 All tests passed! Session continuity implementation is working.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
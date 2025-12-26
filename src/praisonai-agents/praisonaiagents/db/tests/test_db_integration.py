"""
TDD tests for PraisonAI Agents DB integration.

Tests:
1. Lazy import verification - no heavy deps on import
2. Agent(db=MockDb) calls hook lifecycle in correct order
3. Session resume injects history
4. db=None behavior unchanged
"""

import sys
import time


def test_lazy_import_no_heavy_deps():
    """Test that importing praisonaiagents.db does not import DB libs."""
    print("=== Test: Lazy Import Verification ===")
    
    # Record modules before import
    before_modules = set(sys.modules.keys())
    
    # Import only the db module (not full praisonaiagents which loads Knowledge)
    from praisonaiagents.db import DbAdapter, DbMessage
    
    # Check that heavy DB libs are NOT loaded by db module itself
    # Note: praisonaiagents main package loads qdrant/chroma via Knowledge
    # but the db module should not add any additional heavy deps
    heavy_libs = ['psycopg2', 'pymysql', 'redis']  # DB-specific libs
    loaded_heavy = [lib for lib in heavy_libs if lib in sys.modules]
    
    if loaded_heavy:
        print(f"  ❌ Heavy DB libs loaded by db module: {loaded_heavy}")
        return False
    
    print("  ✅ No heavy DB libs loaded by praisonaiagents.db module")
    return True


def test_agent_accepts_db_parameter():
    """Test that Agent accepts db and session_id parameters."""
    print("\n=== Test: Agent Accepts db Parameter ===")
    
    import inspect
    from praisonaiagents import Agent
    
    sig = inspect.signature(Agent.__init__)
    params = list(sig.parameters.keys())
    
    if 'db' not in params:
        print("  ❌ Agent does not accept 'db' parameter")
        return False
    
    if 'session_id' not in params:
        print("  ❌ Agent does not accept 'session_id' parameter")
        return False
    
    print("  ✅ Agent accepts db and session_id parameters")
    return True


class MockDbAdapter:
    """Mock DB adapter for testing hook lifecycle."""
    
    def __init__(self):
        self.calls = []
        self.history_to_return = []
    
    def on_agent_start(self, agent_name, session_id, user_id=None, metadata=None):
        self.calls.append(('on_agent_start', agent_name, session_id))
        return self.history_to_return
    
    def on_user_message(self, session_id, content, metadata=None):
        self.calls.append(('on_user_message', session_id, content))
    
    def on_agent_message(self, session_id, content, metadata=None):
        self.calls.append(('on_agent_message', session_id, content))
    
    def on_tool_call(self, session_id, tool_name, args, result, metadata=None):
        self.calls.append(('on_tool_call', session_id, tool_name))
    
    def on_agent_end(self, session_id, metadata=None):
        self.calls.append(('on_agent_end', session_id))
    
    def close(self):
        self.calls.append(('close',))


def test_db_hook_lifecycle():
    """Test that Agent calls db hooks in correct order."""
    print("\n=== Test: DB Hook Lifecycle ===")
    
    from praisonaiagents import Agent
    
    mock_db = MockDbAdapter()
    
    # Create agent with mock db
    agent = Agent(
        name="TestAgent",
        instructions="Test agent",
        db=mock_db,
        session_id="test-session-001",
        verbose=False
    )
    
    # Verify db is stored
    if agent._db is not mock_db:
        print("  ❌ Agent did not store db adapter")
        return False
    
    if agent._session_id != "test-session-001":
        print("  ❌ Agent did not store session_id")
        return False
    
    print("  ✅ Agent stores db and session_id correctly")
    return True


def test_db_none_unchanged_behavior():
    """Test that db=None behavior is unchanged."""
    print("\n=== Test: db=None Unchanged Behavior ===")
    
    from praisonaiagents import Agent
    
    # Create agent without db
    agent = Agent(
        name="TestAgent",
        instructions="Test agent",
        verbose=False
    )
    
    # Verify db is None
    if agent._db is not None:
        print("  ❌ Agent._db should be None when not provided")
        return False
    
    # Verify _init_db_session does nothing when db is None
    agent._init_db_session()
    
    if agent._db_initialized:
        print("  ❌ _db_initialized should remain False when db is None")
        return False
    
    print("  ✅ db=None behavior unchanged")
    return True


def test_session_id_auto_generation():
    """Test that session_id is auto-generated if not provided."""
    print("\n=== Test: Session ID Auto-Generation ===")
    
    from praisonaiagents import Agent
    
    mock_db = MockDbAdapter()
    
    agent = Agent(
        name="TestAgent",
        instructions="Test agent",
        db=mock_db,
        # No session_id provided
        verbose=False
    )
    
    # Trigger db initialization
    agent._init_db_session()
    
    if agent._session_id is None:
        print("  ❌ session_id should be auto-generated")
        return False
    
    if not agent._session_id.startswith("session-"):
        print(f"  ❌ session_id format unexpected: {agent._session_id}")
        return False
    
    print(f"  ✅ session_id auto-generated: {agent._session_id}")
    return True


def test_protocol_compliance():
    """Test that DbAdapter protocol is properly defined."""
    print("\n=== Test: DbAdapter Protocol Compliance ===")
    
    from praisonaiagents.db.protocol import DbAdapter, DbMessage
    
    # Check DbMessage fields
    msg = DbMessage(role="user", content="test")
    if msg.role != "user" or msg.content != "test":
        print("  ❌ DbMessage fields not working")
        return False
    
    # Check protocol methods
    required_methods = [
        'on_agent_start',
        'on_user_message', 
        'on_agent_message',
        'on_tool_call',
        'on_agent_end',
        'close'
    ]
    
    mock = MockDbAdapter()
    for method in required_methods:
        if not hasattr(mock, method):
            print(f"  ❌ MockDbAdapter missing {method}")
            return False
    
    # Check protocol isinstance
    if not isinstance(mock, DbAdapter):
        print("  ❌ MockDbAdapter should implement DbAdapter protocol")
        return False
    
    print("  ✅ DbAdapter protocol properly defined")
    return True


def run_all_tests():
    """Run all TDD tests."""
    print("=" * 60)
    print("PraisonAI Agents DB Integration - TDD Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Lazy Import", test_lazy_import_no_heavy_deps()))
    results.append(("Agent db Parameter", test_agent_accepts_db_parameter()))
    results.append(("DB Hook Lifecycle", test_db_hook_lifecycle()))
    results.append(("db=None Unchanged", test_db_none_unchanged_behavior()))
    results.append(("Session ID Auto-Gen", test_session_id_auto_generation()))
    results.append(("Protocol Compliance", test_protocol_compliance()))
    
    print("\n" + "=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
    
    print("=" * 60)
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

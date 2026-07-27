#!/usr/bin/env python3
"""
Basic smoke tests for Terminal-Bench Integration

Tests basic functionality without requiring LLM calls or external dependencies.
"""
import sys
import os

# Add the package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'praisonai-agents'))

def test_imports():
    """Test that all required modules can be imported."""
    try:
        from praisonaiagents import Agent
        print("[OK] Agent imported successfully")
        
        from praisonaiagents.tools import execute_command
        print("[OK] execute_command tool imported successfully")
        
        from praisonaiagents.approval import get_approval_registry, AutoApproveBackend
        print("[OK] Approval system imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"[FAIL] Import failed: {ascii(e)}")
        return False

def test_agent_creation():
    """Test that Agent can be created without issues."""
    try:
        from praisonaiagents import Agent
        
        # Create agent without calling LLM
        agent = Agent(
            name='test-agent',
            instructions='Test agent for terminal tasks'
        )
        
        assert agent.name == 'test-agent'
        print("[OK] Agent creation successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] Agent creation failed: {ascii(e)}")
        return False

def test_approval_system():
    """Test approval system configuration."""
    try:
        from praisonaiagents.approval import get_approval_registry, AutoApproveBackend
        
        registry = get_approval_registry()
        registry.set_backend(AutoApproveBackend())
        
        print("[OK] Approval system configuration successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] Approval system test failed: {ascii(e)}")
        return False

def test_external_agent_import():
    """Test that our external agent can be imported."""
    try:
        # Mock Harbor imports for testing
        import sys
        from unittest.mock import MagicMock
        
        sys.modules['harbor'] = MagicMock()
        sys.modules['harbor.agents'] = MagicMock() 
        sys.modules['harbor.agents.base'] = MagicMock()
        sys.modules['harbor.environments'] = MagicMock()
        sys.modules['harbor.environments.base'] = MagicMock()
        sys.modules['harbor.models'] = MagicMock()
        sys.modules['harbor.models.agent'] = MagicMock()
        sys.modules['harbor.models.agent.context'] = MagicMock()
        
        # Now try to import our agent
        import praisonai_external_agent
        print("[OK] External agent import successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] External agent import failed: {ascii(e)}")
        return False

def test_multi_agent_import():
    """Test that multi-agent example can be imported.""" 
    try:
        import sys
        from unittest.mock import MagicMock
        
        # Mock Harbor for testing
        sys.modules['harbor'] = MagicMock()
        sys.modules['harbor.agents'] = MagicMock()
        sys.modules['harbor.agents.base'] = MagicMock()
        sys.modules['harbor.environments'] = MagicMock()
        sys.modules['harbor.environments.base'] = MagicMock()
        sys.modules['harbor.models'] = MagicMock()
        sys.modules['harbor.models.agent'] = MagicMock()
        sys.modules['harbor.models.agent.context'] = MagicMock()
        
        import multi_agent_example
        print("[OK] Multi-agent example import successful")
        return True
        
    except Exception as e:
        print(f"[FAIL] Multi-agent example import failed: {ascii(e)}")
        return False

def test_wrapper_agent_import():
    """Test that wrapper agent can be imported."""
    try:
        import sys
        from unittest.mock import MagicMock
        
        # Mock Harbor for testing
        sys.modules['harbor'] = MagicMock()
        sys.modules['harbor.agents'] = MagicMock()
        sys.modules['harbor.agents.base'] = MagicMock()
        sys.modules['harbor.environments'] = MagicMock()
        sys.modules['harbor.environments.base'] = MagicMock()
        sys.modules['harbor.models'] = MagicMock()
        sys.modules['harbor.models.agent'] = MagicMock()
        sys.modules['harbor.models.agent.context'] = MagicMock()
        
        import praisonai_wrapper_agent
        print("[OK] Wrapper agent import successful (CLI-based approach)")
        return True
        
    except Exception as e:
        print(f"[FAIL] Wrapper agent import failed: {ascii(e)}")
        return False

if __name__ == "__main__":
    print("PraisonAI Terminal-Bench Integration - Basic Tests")
    print("=" * 55)
    
    tests = [
        ("Basic Imports", test_imports),
        ("Agent Creation", test_agent_creation), 
        ("Approval System", test_approval_system),
        ("External Agent Import", test_external_agent_import),
        ("Multi-Agent Import", test_multi_agent_import),
        ("Wrapper Agent Import", test_wrapper_agent_import),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n[TEST] {test_name}...")
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"[FAIL] Test {test_name} crashed: {ascii(e)}")
    
    print("\n" + "=" * 55)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("[OK] ALL BASIC TESTS PASSED!")
        print("The Terminal-Bench integration components are properly structured.")
    else:
        print("[FAIL] Some tests failed - check output above")
        sys.exit(1)
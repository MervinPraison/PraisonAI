#!/usr/bin/env python3
"""
Basic syntax and import test for the fixes.
"""
import ast
import sys

def test_syntax():
    """Test that the modified file has correct Python syntax."""
    
    file_path = "src/praisonai-agents/praisonaiagents/agents/agents.py"
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Parse the AST to check for syntax errors
        ast.parse(content)
        print("✅ Python syntax check passed")
        
        # Check for specific patterns that were added
        assert "threading.RLock()" in content, "RLock fix not found"
        print("✅ RLock fix found in code")
        
        assert "async def aspawn_sub_agent" in content, "Async spawn method not found"
        print("✅ Async spawn method found")
        
        assert "async def aannounce_completion" in content, "Async announce method not found"
        print("✅ Async announce method found")
        
        assert "async def await_for_completions" in content, "Async wait method not found"
        print("✅ Async wait method found")
        
        # Check that the race condition fix is in place
        assert "with self._spawn_lock:" in content and "target_agents = agent_ids or list(self._spawned_agents.keys())" in content, "Race condition fix not found"
        print("✅ Race condition fix found")
        
        print("\n🎉 ALL SYNTAX AND PATTERN CHECKS PASSED!")
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Pattern check failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_syntax()
    sys.exit(0 if success else 1)
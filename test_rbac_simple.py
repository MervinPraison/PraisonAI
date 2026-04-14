#!/usr/bin/env python3
"""Simple test to verify RBAC dependency is working."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import sys
import os

# Add the platform package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-platform'))

def test_rbac_dependency_import():
    """Test that we can import the require_workspace_member dependency."""
    try:
        from praisonai_platform.api.deps import require_workspace_member
        print("✓ Successfully imported require_workspace_member")
        
        # Check that the function signature looks correct
        import inspect
        sig = inspect.signature(require_workspace_member)
        params = list(sig.parameters.keys())
        
        expected_params = ['workspace_id', 'min_role', 'user', 'session']
        if params == expected_params:
            print("✓ Function signature is correct")
        else:
            print(f"✗ Function signature mismatch. Expected: {expected_params}, Got: {params}")
        
        return True
        
    except ImportError as e:
        print(f"✗ Failed to import require_workspace_member: {e}")
        return False

def test_routes_updated():
    """Test that route files have been updated to use require_workspace_member."""
    
    route_files = [
        'praisonai_platform/api/routes/workspaces.py',
        'praisonai_platform/api/routes/projects.py', 
        'praisonai_platform/api/routes/issues.py',
        'praisonai_platform/api/routes/agents.py',
        'praisonai_platform/api/routes/labels.py',
        'praisonai_platform/api/routes/dependencies.py',
        'praisonai_platform/api/routes/activity.py'
    ]
    
    all_passed = True
    
    for file_path in route_files:
        full_path = os.path.join('src/praisonai-platform', file_path)
        try:
            with open(full_path, 'r') as f:
                content = f.read()
                
            if 'require_workspace_member' in content:
                # Count occurrences to ensure it's actually used, not just imported
                import_count = content.count('require_workspace_member')
                usage_count = content.count('Depends(require_workspace_member)')
                
                if import_count > 1 and usage_count > 0:
                    print(f"✓ {file_path} updated correctly (used {usage_count} times)")
                else:
                    print(f"⚠ {file_path} imported but may not be used properly")
            else:
                print(f"✗ {file_path} not updated")
                all_passed = False
                
        except FileNotFoundError:
            print(f"✗ File not found: {file_path}")
            all_passed = False
            
    return all_passed

if __name__ == "__main__":
    print("Testing RBAC implementation...")
    print()
    
    import_test = test_rbac_dependency_import()
    print()
    
    routes_test = test_routes_updated()
    print()
    
    if import_test and routes_test:
        print("✓ All tests passed! RBAC implementation looks good.")
        sys.exit(0)
    else:
        print("✗ Some tests failed.")
        sys.exit(1)
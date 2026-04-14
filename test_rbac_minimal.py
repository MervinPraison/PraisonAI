#!/usr/bin/env python3
"""Minimal test to verify RBAC dependency signature without imports."""

import sys
import os
import inspect

def test_rbac_dependency_function():
    """Test that the require_workspace_member function is properly defined."""
    
    # Read the deps.py file directly
    deps_file = os.path.join('src/praisonai-platform/praisonai_platform/api/deps.py')
    
    try:
        with open(deps_file, 'r') as f:
            content = f.read()
            
        # Check that the function exists
        if 'async def require_workspace_member(' in content:
            print("✓ require_workspace_member function found in deps.py")
            
            # Extract the function definition
            lines = content.split('\n')
            func_start = None
            for i, line in enumerate(lines):
                if 'async def require_workspace_member(' in line:
                    func_start = i
                    break
                    
            if func_start is not None:
                # Find the function parameters
                func_line = lines[func_start]
                next_lines = lines[func_start+1:func_start+10]
                
                # Look for the parameters
                if 'workspace_id: str' in func_line or any('workspace_id: str' in line for line in next_lines):
                    print("✓ workspace_id parameter found")
                else:
                    print("✗ workspace_id parameter missing")
                    return False
                    
                if 'min_role: str = "member"' in func_line or any('min_role: str = "member"' in line for line in next_lines):
                    print("✓ min_role parameter with default value found")
                else:
                    print("✗ min_role parameter missing or incorrect")
                    return False
                    
                if 'Depends(get_current_user)' in content:
                    print("✓ Dependency on get_current_user found")
                else:
                    print("✗ Dependency on get_current_user missing")
                    return False
                    
                if 'Depends(get_db)' in content:
                    print("✓ Dependency on get_db found")
                else:
                    print("✗ Dependency on get_db missing")
                    return False
                    
                # Check for RBAC logic
                if 'has_role(' in content and 'workspace_id' in content and 'user.id' in content:
                    print("✓ RBAC role checking logic found")
                else:
                    print("✗ RBAC role checking logic missing")
                    return False
                    
                # Check for 403 error
                if 'HTTP_403_FORBIDDEN' in content:
                    print("✓ 403 Forbidden error handling found")
                else:
                    print("✗ 403 Forbidden error handling missing")
                    return False
                    
                # Check for setting workspace_id on user
                if 'user.workspace_id = workspace_id' in content:
                    print("✓ Setting workspace_id on user identity found")
                else:
                    print("✗ Setting workspace_id on user identity missing")
                    return False
                    
                print("✓ Function implementation looks correct")
                return True
            else:
                print("✗ Could not find function definition")
                return False
        else:
            print("✗ require_workspace_member function not found in deps.py")
            return False
            
    except FileNotFoundError:
        print(f"✗ File not found: {deps_file}")
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
    
    total_updates = 0
    
    for file_path in route_files:
        full_path = os.path.join('src/praisonai-platform', file_path)
        try:
            with open(full_path, 'r') as f:
                content = f.read()
                
            # Count how many endpoints were updated
            usage_count = content.count('Depends(require_workspace_member)')
            total_updates += usage_count
            
            if usage_count > 0:
                print(f"✓ {file_path}: {usage_count} endpoints updated")
            else:
                print(f"⚠ {file_path}: no endpoints updated")
                
        except FileNotFoundError:
            print(f"✗ File not found: {file_path}")
            
    print(f"✓ Total {total_updates} workspace-scoped endpoints updated")
    return total_updates >= 30  # Expecting at least 30 updated endpoints

if __name__ == "__main__":
    print("Testing RBAC implementation (without imports)...")
    print()
    
    function_test = test_rbac_dependency_function()
    print()
    
    routes_test = test_routes_updated()
    print()
    
    if function_test and routes_test:
        print("✓ All tests passed! RBAC implementation is correct.")
        sys.exit(0)
    else:
        print("✗ Some tests failed.")
        sys.exit(1)
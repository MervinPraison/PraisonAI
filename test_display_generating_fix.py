#!/usr/bin/env python3
"""
Test script to verify that display_generating fix is working correctly.
This script checks that the problematic patterns have been removed from agent.py.
"""

import re
import sys
from pathlib import Path

def test_display_generating_fix():
    """Test that the display_generating fix has been applied correctly."""
    
    agent_file = Path("src/praisonai-agents/praisonaiagents/agent/agent.py")
    
    if not agent_file.exists():
        print(f"❌ ERROR: {agent_file} not found")
        return False
    
    content = agent_file.read_text()
    
    # Check that the old problematic patterns are gone
    old_pattern = r"display_fn=display_generating if \(not stream and self\.verbose\) else None"
    old_matches = re.findall(old_pattern, content)
    
    if old_matches:
        print(f"❌ FAILED: Found {len(old_matches)} instances of old problematic pattern:")
        print(f"   'display_fn=display_generating if (not stream and self.verbose) else None'")
        return False
    
    # Check that the new safe patterns are present
    new_pattern = r"display_fn=None,\s*# Don't use display_generating when stream=False to avoid streaming-like behavior"
    new_matches = re.findall(new_pattern, content)
    
    if len(new_matches) < 2:
        print(f"❌ FAILED: Expected at least 2 instances of new pattern, found {len(new_matches)}")
        print("   Expected: 'display_fn=None,  # Don't use display_generating when stream=False to avoid streaming-like behavior'")
        return False
    
    print("✅ SUCCESS: display_generating fix has been applied correctly!")
    print(f"   - Removed old problematic patterns: 0 found (expected 0)")
    print(f"   - Added new safe patterns: {len(new_matches)} found (expected >= 2)")
    
    # Show the context of the changes
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if "Don't use display_generating when stream=False" in line:
            print(f"   - Line {i}: {line.strip()}")
    
    return True

if __name__ == "__main__":
    success = test_display_generating_fix()
    sys.exit(0 if success else 1)
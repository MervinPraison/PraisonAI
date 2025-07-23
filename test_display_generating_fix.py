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
    
    # Also check for the custom LLM path problematic pattern
    old_custom_pattern = r"if \(not stream and self\.verbose\) and self\.console:\s*.*with Live\(\s*display_generating"
    old_custom_matches = re.findall(old_custom_pattern, content, re.MULTILINE | re.DOTALL)
    
    if old_matches:
        print(f"❌ FAILED: Found {len(old_matches)} instances of old problematic pattern:")
        print(f"   'display_fn=display_generating if (not stream and self.verbose) else None'")
        return False
    
    if old_custom_matches:
        print(f"❌ FAILED: Found {len(old_custom_matches)} instances of old custom LLM problematic pattern:")
        print(f"   'if (not stream and self.verbose) and self.console: ... display_generating'")
        return False
    
    # Check that the new safe patterns are present
    new_pattern = r"display_fn=None,\s*# Don't use display_generating when stream=False to avoid streaming-like behavior"
    new_matches = re.findall(new_pattern, content)
    
    # Check for the new custom LLM path fix
    new_custom_pattern = r"if False:\s*# Don't use display_generating when stream=False to avoid streaming-like behavior"
    new_custom_matches = re.findall(new_custom_pattern, content)
    
    expected_total = 3  # 2 OpenAI path + 1 custom LLM path
    actual_total = len(new_matches) + len(new_custom_matches)
    
    if actual_total < expected_total:
        print(f"❌ FAILED: Expected at least {expected_total} instances of new patterns, found {actual_total}")
        print("   Expected patterns:")
        print("   - 'display_fn=None,  # Don't use display_generating when stream=False to avoid streaming-like behavior'")
        print("   - 'if False:  # Don't use display_generating when stream=False to avoid streaming-like behavior'")
        return False
    
    print("✅ SUCCESS: display_generating fix has been applied correctly!")
    print(f"   - Removed old problematic patterns: 0 found (expected 0)")
    print(f"   - Added new safe patterns: {actual_total} found (expected >= {expected_total})")
    print(f"     * OpenAI path fixes: {len(new_matches)}")
    print(f"     * Custom LLM path fixes: {len(new_custom_matches)}")
    
    # Show the context of the changes
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if "Don't use display_generating when stream=False" in line:
            print(f"   - Line {i}: {line.strip()}")
    
    return True

if __name__ == "__main__":
    success = test_display_generating_fix()
    sys.exit(0 if success else 1)
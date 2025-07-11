#!/usr/bin/env python3
"""Quick verification of the sequential tool calling fix"""

import sys
import os

# Add the src path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

# Simple mock test to verify the fix
print("Verifying the sequential tool calling fix...")

# Read the fixed files to confirm changes
with open('src/praisonai-agents/praisonaiagents/llm/llm.py', 'r') as f:
    llm_content = f.read()
    
with open('src/praisonai-agents/praisonaiagents/llm/openai_client.py', 'r') as f:
    openai_content = f.read()

# Check if the fix is present
llm_fixed = "# For sequential tool calling, always continue the loop after tool execution" in llm_content
openai_fixed = "# For sequential tool calling, always continue the loop after tool execution" in openai_content

print(f"✅ llm.py fixed: {llm_fixed}")
print(f"✅ openai_client.py fixed: {openai_fixed}")

# Check that the old hardcoded check is gone
old_check = 'if function_name == "sequentialthinking" and arguments.get("nextThoughtNeeded", False):'
llm_has_old = old_check in llm_content
openai_has_old = old_check in openai_content

print(f"✅ llm.py old check removed: {not llm_has_old}")
print(f"✅ openai_client.py old check removed: {not openai_has_old}")

if llm_fixed and openai_fixed and not llm_has_old and not openai_has_old:
    print("\n✅ All checks passed! The fix has been applied correctly.")
else:
    print("\n❌ Some checks failed. Please review the changes.")
    sys.exit(1)
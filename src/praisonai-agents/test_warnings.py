#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src/praisonai-agents')

import warnings
warnings.simplefilter('always')  # Enable all warnings

print("Testing import with all warnings enabled...")
print("Importing praisonaiagents...")

try:
    import praisonaiagents
    print("✅ Import successful!")
    
    print("Testing Agent creation...")
    agent = praisonaiagents.Agent(instructions="Test agent", llm="gpt-5-nano")
    print("✅ Agent created successfully!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
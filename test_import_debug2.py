#!/usr/bin/env python3
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
# Add the praisonai-agents directory to the path  
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

print("Testing import functionality...")

# Check if praisonai is found
try:
    import praisonai
    print(f"✓ praisonai package found at: {praisonai.__file__}")
    print(f"praisonai.__path__: {praisonai.__path__}")
    print(f"praisonai dir: {dir(praisonai)}")
except Exception as e:
    print(f"Error importing praisonai: {e}")

# Check praisonai.praisonai
try:
    import praisonai.praisonai
    print(f"✓ praisonai.praisonai package found at: {praisonai.praisonai.__file__}")
    print(f"praisonai.praisonai dir: {dir(praisonai.praisonai)}")
    if hasattr(praisonai.praisonai, '__all__'):
        print(f"praisonai.praisonai.__all__: {praisonai.praisonai.__all__}")
    
    # Check what we can actually import
    print("\nTesting actual imports from praisonai.praisonai:")
    for symbol in ['PraisonAI', '__version__', 'Agent', 'Task', 'PraisonAIAgents']:
        if hasattr(praisonai.praisonai, symbol):
            print(f"✓ {symbol} is available")
        else:
            print(f"❌ {symbol} is NOT available")
            
except Exception as e:
    print(f"Error importing praisonai.praisonai: {e}")

# Test direct import
try:
    from praisonai.praisonai import PraisonAI, __version__
    print(f"✓ Direct import from praisonai.praisonai works: PraisonAI={PraisonAI}, __version__={__version__}")
except Exception as e:
    print(f"❌ Direct import from praisonai.praisonai failed: {e}")

# Test import from praisonaiagents
print("\nTesting praisonaiagents:")
try:
    import praisonaiagents
    print(f"✓ praisonaiagents is available: {praisonaiagents}")
    print(f"praisonaiagents.__all__: {praisonaiagents.__all__}")
except Exception as e:
    print(f"❌ praisonaiagents import failed: {e}")
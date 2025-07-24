#!/usr/bin/env python3

# Simple syntax checker
filename = "praisonaiagents/agent/agent.py"

try:
    with open(filename, 'r') as f:
        content = f.read()
    
    # Try to compile the code
    compile(content, filename, 'exec')
    print(f"✅ {filename} has valid syntax")
    
except SyntaxError as e:
    print(f"❌ Syntax error in {filename}:")
    print(f"   Line {e.lineno}: {e.text.strip() if e.text else 'N/A'}")
    print(f"   Error: {e.msg}")
    if e.offset:
        print(f"   {' ' * (e.offset-1)}^")
        
except Exception as e:
    print(f"❌ Error: {e}") 
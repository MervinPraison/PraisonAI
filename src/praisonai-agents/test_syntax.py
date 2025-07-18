#!/usr/bin/env python3
import ast
import sys

def check_syntax(filename):
    try:
        with open(filename, 'r') as f:
            content = f.read()
        
        # Try to parse the content
        ast.parse(content)
        print(f"✅ Syntax is valid for {filename}")
        return True
        
    except SyntaxError as e:
        print(f"❌ SyntaxError in {filename}:")
        print(f"   Line {e.lineno}: {e.text}")
        print(f"   Error: {e.msg}")
        print(f"   Position: {' ' * (e.offset - 1 if e.offset else 0)}^")
        return False
    except Exception as e:
        print(f"❌ Error reading {filename}: {e}")
        return False

if __name__ == "__main__":
    filename = "praisonaiagents/agent/agent.py"
    success = check_syntax(filename)
    sys.exit(0 if success else 1) 
import ast
import sys

def check_syntax(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to parse the AST
        ast.parse(content, filename=filename)
        print(f"✅ {filename} has valid syntax")
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error in {filename}:")
        print(f"   Line {e.lineno}: {e.text.strip() if e.text else 'N/A'}")
        print(f"   {' ' * (e.offset-1 if e.offset else 0)}^")
        print(f"   Error: {e.msg}")
        return False
    except Exception as e:
        print(f"❌ Error reading {filename}: {e}")
        return False

if __name__ == "__main__":
    check_syntax("praisonaiagents/agent/agent.py") 
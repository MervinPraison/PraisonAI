#!/usr/bin/env python3

print("Testing syntax fix...")
import ast
from pathlib import Path

agent_file = (
    Path(__file__).resolve().parent
    / "praisonaiagents"
    / "agent"
    / "agent.py"
)
try:
    # Test basic import

    # Parse the agent.py file to check for syntax errors
    with agent_file.open("r", encoding="utf-8") as f:
        content = f.read()

    # This will raise SyntaxError if there are issues
    ast.parse(content)
    print("✅ agent.py syntax is valid")

    # Test actual import
    from praisonaiagents.agent.agent import Agent
    print("✅ Agent import successful")

    print("🎉 All syntax checks passed!")

except SyntaxError as e:
    print(f"❌ Syntax error: {e}")
    print(f"   Line {e.lineno}: {e.text}")
    exit(1)
except Exception as e:
    print(f"❌ Import error: {e}")
    exit(1)

try:
    print("Testing import...")
    from praisonaiagents import Agent
    print("✅ Import successful - no syntax errors!")
    
    print("Creating agent...")
    agent = Agent(instructions="Test agent", llm="gpt-4o-mini")
    print("✅ Agent created successfully!")
    
except SyntaxError as e:
    print(f"❌ SyntaxError: {e}")
    print(f"   File: {e.filename}")
    print(f"   Line {e.lineno}: {e.text}")
except Exception as e:
    print(f"❌ Other error: {e}")
    import traceback
    traceback.print_exc() 
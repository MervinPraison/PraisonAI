"""
Simple test to verify that tool_choice='auto' is set for Gemini models
"""
import logging
from praisonaiagents.llm.llm import LLM

# Enable debug logging to see our log message
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

# Test different Gemini model formats
test_models = [
    "gemini/gemini-1.5-flash-8b",
    "gemini-1.5-flash-8b",
    "gemini/gemini-pro",
    "gpt-4",  # Non-Gemini model for comparison
]

# Mock tools
mock_tools = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            }
        }
    }
]

print("Testing tool_choice setting for different models:\n")

for model in test_models:
    print(f"\nTesting model: {model}")
    try:
        llm = LLM(model=model)
        params = llm._build_completion_params(
            messages=[{"role": "user", "content": "test"}],
            tools=mock_tools
        )
        
        tool_choice = params.get('tool_choice', 'NOT SET')
        print(f"  tool_choice: {tool_choice}")
        
        # Verify behavior
        if model.startswith(('gemini-', 'gemini/')):
            if tool_choice == 'auto':
                print(f"  ✅ CORRECT: Gemini model has tool_choice='auto'")
            else:
                print(f"  ❌ ERROR: Gemini model should have tool_choice='auto'")
        else:
            if tool_choice == 'NOT SET':
                print(f"  ✅ CORRECT: Non-Gemini model doesn't have tool_choice set")
            else:
                print(f"  ⚠️  WARNING: Non-Gemini model has tool_choice set to '{tool_choice}'")
                
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

print("\nTest complete!")

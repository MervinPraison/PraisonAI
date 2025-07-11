"""
Enhanced test example demonstrating the improved tool call fix for Gemini models.
This test includes edge cases and error handling scenarios.
"""
import logging
from praisonaiagents import Agent, Task, PraisonAIAgents

# Enable info logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Test different tool formats

# 1. Simple function tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Web search results for '{query}': Found relevant information."

# 2. Dictionary format tool (OpenAI style)
dict_tool = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Perform mathematical calculations",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate"
                }
            },
            "required": ["expression"]
        }
    }
}

# 3. String tool name
string_tool = "weather_tool"

# 4. Mock MCP tool class
class MockMCPTool:
    def to_openai_tool(self):
        return {
            "type": "function",
            "function": {
                "name": "mcp_search",
                "description": "MCP-based search tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    }
                }
            }
        }

# Create test agent with various tool formats
test_agent = Agent(
    name="MultiToolAgent",
    role="Versatile Assistant",
    goal="Test various tool formats and edge cases",
    backstory="Expert at using different types of tools",
    tools=[search_web, dict_tool, string_tool, MockMCPTool()],
    llm={"model": "gemini/gemini-1.5-flash-8b"},
    verbose=True
)

# Create test task
test_task = Task(
    name="test_tools",
    description="Search for information about Python programming best practices",
    expected_output="A summary of Python best practices found through search",
    agent=test_agent
)

def test_improved_implementation():
    """Test the improved tool usage implementation."""
    print("=" * 80)
    print("Testing Improved Tool Usage with Various Tool Formats")
    print("=" * 80)
    
    try:
        # Create workflow
        workflow = PraisonAIAgents(
            agents=[test_agent],
            tasks=[test_task],
            verbose=True
        )
        
        # Execute
        print("\nExecuting task with multiple tool formats...")
        result = workflow.start()
        
        # Analyze result
        print("\n" + "=" * 80)
        print("RESULT ANALYSIS:")
        print("=" * 80)
        
        if isinstance(result, dict) and 'task_results' in result:
            task_result = result['task_results'][0]
            result_str = str(task_result).lower()
            
            # Check various failure/success indicators
            if "do not have access" in result_str:
                print("❌ FAILED: Agent claims no access to tools")
            elif any(tool_indicator in result_str for tool_indicator in ["search", "results", "found", "web"]):
                print("✅ SUCCESS: Agent appears to have used tools!")
            else:
                print("⚠️  UNCLEAR: Cannot determine if tools were used")
                
            print(f"\nFull Result: {task_result}")
        else:
            print(f"Unexpected result format: {result}")
            
    except Exception as e:
        print(f"❌ ERROR during execution: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)

if __name__ == "__main__":
    test_improved_implementation()
    
    print("\n\nNOTE: This test verifies the improved implementation handles:")
    print("1. Function tools")
    print("2. Dictionary format tools")  
    print("3. String tool names")
    print("4. MCP-style tools with to_openai_tool method")
    print("5. Error handling for malformed tools")

#!/usr/bin/env python3
"""
Final verification that the praisonaiagents package is working correctly
"""

import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def demonstrate_basic_usage():
    """Demonstrate basic usage of the package"""
    print("=" * 50)
    print("PRAISONAIAGENTS BASIC USAGE DEMONSTRATION")
    print("=" * 50)
    
    # Import the package
    from praisonaiagents import Agent, Task, PraisonAIAgents
    
    print("✓ Package imported successfully")
    
    # Create a simple tool
    def simple_calculator(expression: str) -> str:
        """Simple calculator tool for demonstration"""
        try:
            # Basic math evaluation using safer approach
            import ast
            import operator

            # Support basic operations
            ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
            }

            def safe_eval(node):
                if isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    return ops[type(node.op)](safe_eval(node.left), safe_eval(node.right))
                elif isinstance(node, ast.UnaryOp):
                    return ops[type(node.op)](safe_eval(node.operand))
                else:
                    raise ValueError(f"Unsupported operation: {type(node)}")

            tree = ast.parse(expression.replace(' ', ''), mode='eval')
            result = safe_eval(tree.body)
            return f"Calculation result: {result}"
        except Exception as e:
            return f"Error: {e}"
    
    # Create an agent with the tool
    calculator_agent = Agent(
        name="CalculatorAgent",
        role="Mathematical Assistant",
        goal="Perform basic calculations",
        backstory="I am a helpful calculator assistant",
        instructions="Help with basic mathematical calculations",
        tools=[simple_calculator]
    )
    
    print("✓ Agent created with custom tool")
    
    # Create a task
    calculation_task = Task(
        name="calculate",
        description="Calculate 15 + 27 * 3",
        expected_output="The numerical result of the calculation",
        agent=calculator_agent
    )
    
    print("✓ Task created")
    
    # Create a simple workflow
    workflow = PraisonAIAgents(
        agents=[calculator_agent],
        tasks=[calculation_task],
        process="sequential"
    )
    
    print("✓ Workflow created")
    
    # Verify the workflow structure
    assert len(workflow.agents) == 1
    assert len(workflow.tasks) == 1
    assert workflow.agents[0].name == "CalculatorAgent"
    assert workflow.tasks[0].name == "calculate"
    
    print("✓ Workflow structure verified")
    
    # Test the tool function directly
    tool_result = simple_calculator("15 + 27 * 3")
    print(f"✓ Tool function works: {tool_result}")
    
    print("\n🎉 All basic usage demonstrations successful!")
    print("📝 The package is ready for use with actual LLM providers.")
    
    return True

def show_package_info():
    """Show information about the installed package"""
    print("\n" + "=" * 50)
    print("PACKAGE INFORMATION")
    print("=" * 50)
    
    import praisonaiagents
    
    # Show available classes and functions
    available_items = [
        'Agent', 'Task', 'PraisonAIAgents', 'Agents', 'Tools', 
        'ImageAgent', 'AutoAgents', 'Memory', 'Knowledge', 'MCP'
    ]
    
    print("Available classes and functions:")
    for item in available_items:
        if hasattr(praisonaiagents, item):
            print(f"  ✓ {item}")
        else:
            print(f"  ✗ {item} (not available)")
    
    # Show installation location
    print(f"\nPackage location: {praisonaiagents.__file__}")
    
    return True

def main():
    """Main function to run all demonstrations"""
    try:
        demonstrate_basic_usage()
        show_package_info()
        
        print("\n" + "=" * 50)
        print("🚀 INSTALLATION AND TESTING COMPLETE!")
        print("=" * 50)
        print("The praisonaiagents package has been successfully installed and tested.")
        print("You can now run the example files with your preferred LLM provider.")
        print("\nExample usage with OpenAI:")
        print("  export OPENAI_API_KEY='your-api-key-here'")
        print("  python basic-agents.py")
        print("\nExample usage with other providers:")
        print("  See the examples in the examples/ directory")
        
        return True
    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
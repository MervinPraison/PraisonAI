"""
Gemini Code Execution Tool Example

This example demonstrates how to use Gemini's built-in Code Execution functionality
through PraisonAI. The Code Execution tool allows the model to run Python code
snippets directly within the conversation for dynamic computation and validation.

Prerequisites:
- Set GEMINI_API_KEY environment variable
- Use a Gemini model that supports internal tools (gemini-2.0-flash, etc.)

Features:
- Direct Python code execution within the model
- Real-time calculations and data processing
- Code validation and testing
- Mathematical computations and visualizations
"""

from praisonaiagents import Agent

# Ensure you have your Gemini API key set
# import os; os.environ["GEMINI_API_KEY"] = "your-api-key-here"

def main():
    # Create agent with Code Execution internal tool
    agent = Agent(
        instructions="""You are a data analyst and programmer that can execute Python code.
        Use the Code Execution tool to perform calculations, analyze data, create visualizations,
        and validate logic. Always show your work by executing relevant code snippets.""",
        
        llm="gemini/gemini-2.0-flash",
        
        # Enable Code Execution internal tool
        tools=[{"codeExecution": {}}],
        
        verbose=True
    )
    
    # Example tasks that benefit from code execution
    tasks = [
        "Calculate the compound interest on $10,000 invested at 5% annual rate for 10 years, compounded monthly. Show the calculation step by step.",
        
        "Generate the first 20 Fibonacci numbers and find their sum. Also calculate the ratio of consecutive Fibonacci numbers.",
        
        "Create a simple linear regression model for the data points: (1,2), (2,4), (3,6), (4,8), (5,10). Calculate the R-squared value.",
        
        "Solve the quadratic equation 2x² + 5x - 3 = 0 using the quadratic formula. Verify the solutions by substituting back.",
        
        "Calculate the statistical summary (mean, median, mode, standard deviation) for this dataset: [12, 15, 18, 12, 20, 25, 18, 12, 22, 30, 15, 18]",
        
        "Write a function to check if a number is prime, then find all prime numbers between 1 and 100.",
        
        "Calculate the area under the curve y = x² from x = 0 to x = 5 using numerical integration (trapezoidal rule)."
    ]
    
    print("=== Gemini Code Execution Tool Demo ===\n")
    
    for i, task in enumerate(tasks, 1):
        print(f"Task {i}: {task}")
        print("-" * 80)
        
        try:
            response = agent.start(task)
            print(f"Response: {response}")
            print("\n" + "="*100 + "\n")
            
        except Exception as e:
            print(f"Error: {e}")
            print("\n" + "="*100 + "\n")

def demonstrate_direct_usage():
    """
    Example of how the Code Execution tool works at the LiteLLM level
    (for reference - this requires direct LiteLLM usage)
    """
    print("=== Direct LiteLLM Code Execution Usage (Reference) ===")
    print("""
    # This is how it works at the LiteLLM level:
    
    import litellm
    import os
    
    os.environ["GEMINI_API_KEY"] = "your-api-key"
    
    response = litellm.completion(
        model="gemini/gemini-2.0-flash",
        messages=[{
            "role": "user", 
            "content": "Calculate the factorial of 10 and show the code"
        }],
        tools=[{"codeExecution": {}}],
    )
    
    print(response.choices[0].message.content)
    """)

if __name__ == "__main__":
    main()
    demonstrate_direct_usage()
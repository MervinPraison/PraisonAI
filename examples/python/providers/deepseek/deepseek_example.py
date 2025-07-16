"""
Basic example of using DeepSeek with PraisonAI
"""

from praisonai import PraisonAI

def main():
    # Initialize PraisonAI with DeepSeek
    praison = PraisonAI(
        model="deepseek-chat",
        provider="deepseek",
        api_key="your-deepseek-api-key-here"  # Replace with your actual DeepSeek API key
    )
    
    # Create a simple agent
    agent = praison.create_agent(
        name="DeepSeek Agent",
        description="A basic agent using DeepSeek model"
    )
    
    # Example conversation
    response = agent.run("Hello! Can you help me with a mathematical problem?")
    print("Agent Response:", response)
    
    # Example with mathematical reasoning
    math_task = """
    Solve this calculus problem step by step:
    Find the derivative of f(x) = x^3 * e^(2x) using the product rule.
    """
    
    response = agent.run(math_task)
    print("\nMathematical Reasoning Response:")
    print(response)
    
    # Example with code optimization
    code_task = """
    Optimize this Python function for better performance:
    
    def find_duplicates(arr):
        duplicates = []
        for i in range(len(arr)):
            for j in range(i+1, len(arr)):
                if arr[i] == arr[j] and arr[i] not in duplicates:
                    duplicates.append(arr[i])
        return duplicates
    """
    
    response = agent.run(code_task)
    print("\nCode Optimization Response:")
    print(response)

if __name__ == "__main__":
    main() 
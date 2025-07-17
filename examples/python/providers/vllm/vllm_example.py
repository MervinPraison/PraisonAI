"""
Basic example of using vLLM with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with vLLM
agent = Agent(
    instructions="You are a helpful assistant",
    llm="vllm/meta-llama/Llama-3.1-8B-Instruct",
)

# Example conversation
response = agent.start("Hello! Can you help me with a mathematical problem?")

# Example with mathematical reasoning
math_task = """
Solve this calculus problem step by step:
Find the derivative of f(x) = x^3 * e^(2x) using the product rule.
"""

response = agent.start(math_task)

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

response = agent.start(code_task) 
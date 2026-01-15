"""
Sequential Thinking MCP Example.

This example demonstrates how to use the Sequential Thinking MCP server
with PraisonAI Agents to break down complex problems step by step.

Requirements:
    - Node.js and npx installed
    - pip install praisonaiagents[mcp]
    - OPENAI_API_KEY environment variable set

Usage:
    python sequential_thinking.py
"""

from praisonaiagents import Agent, MCP
import os


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Please set OPENAI_API_KEY environment variable")
        return
    
    # Create MCP instance with Sequential Thinking server
    # The server provides tools for step-by-step problem analysis
    sequential_mcp = MCP(
        "npx -y @modelcontextprotocol/server-sequential-thinking",
        timeout=60
    )
    
    # Create an agent with the Sequential Thinking tools
    agent = Agent(
        name="ProblemSolver",
        instructions="""You are an expert problem solver who breaks down complex problems 
        into manageable steps. When given a problem:
        1. Use the sequential thinking tool to analyze it step by step
        2. Provide clear, actionable steps
        3. Explain your reasoning at each step""",
        llm="openai/gpt-4o-mini",
        tools=sequential_mcp
    )
    
    # Example problems to solve
    problems = [
        "Break down the process of making a cup of tea",
        "How would you plan a weekend trip to a new city?",
        "What steps would you take to learn a new programming language?"
    ]
    
    print("=" * 60)
    print("Sequential Thinking MCP Example")
    print("=" * 60)
    
    for i, problem in enumerate(problems, 1):
        print(f"\n--- Problem {i} ---")
        print(f"Question: {problem}\n")
        
        response = agent.chat(problem)
        print(f"Response:\n{response}")
        print("-" * 40)
    
    # Clean up
    sequential_mcp.shutdown()
    print("\nDone!")


if __name__ == "__main__":
    main()

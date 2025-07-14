"""
Gemini Internal Tools Combined Example

This example demonstrates how to use all three of Gemini's built-in internal tools
together through PraisonAI:
1. Google Search - for real-time web information
2. URL Context - for analyzing web content
3. Code Execution - for computations and analysis

Prerequisites:
- Set GEMINI_API_KEY environment variable
- Use a Gemini model that supports internal tools (gemini-2.0-flash, etc.)

Features:
- Multi-tool agent combining search, content analysis, and computation
- Real-world research and analysis workflows
- Comprehensive data gathering and processing capabilities
"""

from praisonaiagents import Agent

# Ensure you have your Gemini API key set
# import os; os.environ["GEMINI_API_KEY"] = "your-api-key-here"

def main():
    # Create agent with all Gemini internal tools enabled
    agent = Agent(
        instructions="""You are an advanced research and analysis assistant with access to:
        1. Google Search - for finding current information
        2. URL Context - for analyzing web content 
        3. Code Execution - for calculations and data processing
        
        Use these tools strategically to provide comprehensive, well-researched, and 
        analytically sound responses. Always show your work and cite sources.""",
        
        llm="gemini/gemini-2.0-flash",
        
        # Enable all three Gemini internal tools
        tools=[
            {"googleSearch": {}},
            {"urlContext": {}}, 
            {"codeExecution": {}}
        ],
        
        verbose=True
    )
    
    # Complex tasks that benefit from multiple internal tools
    complex_tasks = [
        """Research the current market cap of the top 5 technology companies, 
        then calculate their combined market value and determine what percentage 
        each company represents of the total. Present the results in a formatted table.""",
        
        """Find recent research papers about large language models from arXiv, 
        analyze the abstracts of 2-3 papers, and calculate the average number 
        of authors across these papers.""",
        
        """Look up the current population of the 10 largest cities in the world, 
        then calculate statistical measures (mean, median, standard deviation) 
        and create a simple visualization of the data distribution.""",
        
        """Research the latest Python release notes, analyze the key new features, 
        and write example code demonstrating 2-3 of the most important new features.""",
        
        """Find information about recent climate data, analyze a specific dataset 
        or report, and perform calculations to show trends or comparisons over time."""
    ]
    
    print("=== Gemini Combined Internal Tools Demo ===\n")
    
    for i, task in enumerate(complex_tasks, 1):
        print(f"Complex Task {i}:")
        print(task)
        print("-" * 100)
        
        try:
            response = agent.start(task)
            print(f"Response: {response}")
            print("\n" + "="*120 + "\n")
            
        except Exception as e:
            print(f"Error: {e}")
            print("\n" + "="*120 + "\n")

def demonstrate_tool_synergy():
    """
    Example showing how the tools work together for a research workflow
    """
    print("=== Tool Synergy Example ===")
    
    agent = Agent(
        instructions="""You are a market research analyst. Use all available tools 
        to gather information, analyze content, and perform calculations as needed.""",
        
        llm="gemini/gemini-2.0-flash",
        tools=[
            {"googleSearch": {}},
            {"urlContext": {}}, 
            {"codeExecution": {}}
        ],
        verbose=True
    )
    
    # Multi-step research task
    research_query = """
    Conduct a mini market analysis on electric vehicle adoption:
    1. Search for recent statistics on global EV sales
    2. Find and analyze a recent report or article about EV market trends
    3. Calculate the year-over-year growth rate if you can find data for multiple years
    4. Provide a summary with key insights and numerical analysis
    """
    
    print("Research Query:", research_query)
    print("-" * 80)
    
    try:
        response = agent.start(research_query)
        print(f"Research Results: {response}")
        
    except Exception as e:
        print(f"Error: {e}")

def show_configuration_options():
    """
    Show different ways to configure the internal tools
    """
    print("\n=== Configuration Examples ===")
    print("""
    # Basic usage (all tools with default settings)
    tools=[
        {"googleSearch": {}},
        {"urlContext": {}},
        {"codeExecution": {}}
    ]
    
    # Can also be used individually
    tools=[{"googleSearch": {}}]  # Only Google Search
    tools=[{"urlContext": {}}]    # Only URL Context  
    tools=[{"codeExecution": {}}] # Only Code Execution
    
    # Mix with custom tools
    from praisonaiagents import Agent
    
    def custom_calculator(expression: str) -> str:
        '''Custom calculator function - safely evaluates basic math expressions'''
        import ast
        import operator
        
        # Define safe operations
        ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
        }
        
        def eval_expr(node):
            if isinstance(node, ast.Constant):  # Numbers
                return node.value
            elif isinstance(node, ast.BinOp):  # Binary operations
                return ops[type(node.op)](eval_expr(node.left), eval_expr(node.right))
            elif isinstance(node, ast.UnaryOp):  # Unary operations
                return ops[type(node.op)](eval_expr(node.operand))
            else:
                raise TypeError(f"Unsupported operation: {type(node)}")
        
        try:
            return str(eval_expr(ast.parse(expression, mode='eval').body))
        except Exception as e:
            return f"Error: {e}"
    
    agent = Agent(
        tools=[
            {"googleSearch": {}},        # Gemini internal tool
            {"codeExecution": {}},       # Gemini internal tool
            custom_calculator            # Custom external tool
        ]
    )
    """)

if __name__ == "__main__":
    main()
    print("\n" + "="*50)
    demonstrate_tool_synergy()
    show_configuration_options()
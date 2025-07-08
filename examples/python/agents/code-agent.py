"""
Code Agent Example

This example demonstrates a comprehensive code agent that can write, analyze, debug, and execute code.
It includes self-reflection for improving code quality and multiple specialized tools.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import CodeInterpreter

# Initialize code execution tool
code_interpreter = CodeInterpreter()

# Custom code analysis tool
def analyze_code_complexity(code: str) -> str:
    """Analyze code complexity and provide feedback."""
    lines = code.strip().split('\n')
    num_lines = len(lines)
    num_functions = sum(1 for line in lines if line.strip().startswith('def '))
    num_classes = sum(1 for line in lines if line.strip().startswith('class '))
    
    return f"""Code Analysis:
- Lines of code: {num_lines}
- Functions: {num_functions}
- Classes: {num_classes}
- Complexity: {'Simple' if num_lines < 50 else 'Moderate' if num_lines < 200 else 'Complex'}"""

# Create specialized code agents
code_writer = Agent(
    name="CodeWriter",
    role="Expert Python developer",
    goal="Write clean, efficient, and well-documented Python code",
    backstory="You are a senior Python developer with 10+ years of experience in writing production-quality code.",
    instructions="Write Python code that follows PEP 8 standards, includes proper error handling, and has clear documentation.",
    self_reflect=True,
    min_reflect=2,
    max_reflect=5
)

code_reviewer = Agent(
    name="CodeReviewer",
    role="Code quality expert",
    goal="Review code for bugs, security issues, and best practices",
    backstory="You are a code review specialist who ensures code quality and maintainability.",
    instructions="Review the provided code for potential issues, suggest improvements, and ensure it follows best practices.",
    tools=[analyze_code_complexity]
)

code_executor = Agent(
    name="CodeExecutor",
    role="Code execution specialist",
    goal="Safely execute and test Python code",
    backstory="You are responsible for running code and reporting results or errors.",
    instructions="Execute the provided code safely and report the output or any errors encountered.",
    tools=[code_interpreter]
)

# Example tasks
def demonstrate_code_agent():
    # Task 1: Write a function
    write_task = Task(
        name="write_function",
        description="Write a Python function that calculates the Fibonacci sequence up to n terms",
        expected_output="A well-documented Python function with error handling",
        agent=code_writer
    )
    
    # Task 2: Review the code
    review_task = Task(
        name="review_code",
        description="Review the Fibonacci function for quality and suggest improvements",
        expected_output="Detailed code review with suggestions",
        agent=code_reviewer,
        context=[write_task]
    )
    
    # Task 3: Execute and test
    execute_task = Task(
        name="execute_code",
        description="Execute the Fibonacci function with n=10 and verify it works correctly",
        expected_output="Execution results showing the first 10 Fibonacci numbers",
        agent=code_executor,
        context=[write_task]
    )
    
    # Create workflow
    workflow = PraisonAIAgents(
        agents=[code_writer, code_reviewer, code_executor],
        tasks=[write_task, review_task, execute_task],
        process="sequential",
        verbose=True
    )
    
    # Run the workflow
    result = workflow.start()
    return result

# Standalone code agent for general programming tasks
general_code_agent = Agent(
    name="GeneralCodeAgent",
    role="Full-stack programming assistant",
    goal="Help with any programming task including writing, debugging, and explaining code",
    backstory="You are an AI programming assistant with expertise in multiple languages and frameworks.",
    instructions="""You can:
1. Write code in any programming language
2. Debug and fix code issues
3. Explain code concepts
4. Refactor code for better performance
5. Add tests and documentation""",
    tools=[code_interpreter, analyze_code_complexity],
    self_reflect=True,
    min_reflect=1,
    max_reflect=3
)

if __name__ == "__main__":
    # Example 1: Run the multi-agent workflow
    print("=== Multi-Agent Code Workflow ===")
    result = demonstrate_code_agent()
    print(f"Workflow Result: {result}")
    
    # Example 2: Use the general code agent
    print("\n=== General Code Agent ===")
    response = general_code_agent.start("""
    Write a Python class for a simple Calculator with methods for:
    - Addition
    - Subtraction
    - Multiplication
    - Division (with error handling for division by zero)
    
    Then create a simple test to verify it works.
    """)
    print(response)
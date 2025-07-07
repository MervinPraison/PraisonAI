from praisonaiagents import Agent
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

# Create code agent
agent = Agent(
    instructions="""You are an expert Python developer who can:
1. Write clean, efficient, and well-documented Python code
2. Debug and fix code issues
3. Explain code concepts
4. Refactor code for better performance
5. Add tests and documentation

Always follow PEP 8 standards and include proper error handling.""",
    tools=[code_interpreter, analyze_code_complexity]
)

# Run the agent
agent.start("""
Write a Python class for a simple Calculator with methods for:
- Addition
- Subtraction
- Multiplication
- Division (with error handling for division by zero)

Then create a simple test to verify it works.
""")
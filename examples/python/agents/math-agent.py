"""
Math Agent Example

This example demonstrates a mathematical problem-solving agent that can handle various math tasks
including calculations, equation solving, and step-by-step explanations.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from typing import Dict, Any
import math
import re

# Custom math tools
def basic_calculator(expression: str) -> str:
    """Evaluate basic mathematical expressions safely."""
    try:
        # Remove any non-mathematical characters for safety
        safe_expr = re.sub(r'[^0-9+\-*/().,\s]', '', expression)
        result = eval(safe_expr)
        return f"Result: {result}"
    except Exception as e:
        return f"Error in calculation: {str(e)}"

def solve_quadratic(a: float, b: float, c: float) -> str:
    """Solve quadratic equation ax² + bx + c = 0."""
    discriminant = b**2 - 4*a*c
    
    if discriminant > 0:
        x1 = (-b + math.sqrt(discriminant)) / (2*a)
        x2 = (-b - math.sqrt(discriminant)) / (2*a)
        return f"Two real solutions: x₁ = {x1:.4f}, x₂ = {x2:.4f}"
    elif discriminant == 0:
        x = -b / (2*a)
        return f"One real solution: x = {x:.4f}"
    else:
        real_part = -b / (2*a)
        imag_part = math.sqrt(-discriminant) / (2*a)
        return f"Two complex solutions: x₁ = {real_part:.4f} + {imag_part:.4f}i, x₂ = {real_part:.4f} - {imag_part:.4f}i"

def calculate_statistics(numbers: list) -> str:
    """Calculate basic statistics for a list of numbers."""
    if not numbers:
        return "No numbers provided"
    
    n = len(numbers)
    mean = sum(numbers) / n
    sorted_nums = sorted(numbers)
    median = sorted_nums[n//2] if n % 2 else (sorted_nums[n//2-1] + sorted_nums[n//2]) / 2
    variance = sum((x - mean)**2 for x in numbers) / n
    std_dev = math.sqrt(variance)
    
    return f"""Statistics:
- Count: {n}
- Mean: {mean:.4f}
- Median: {median:.4f}
- Standard Deviation: {std_dev:.4f}
- Min: {min(numbers)}
- Max: {max(numbers)}"""

# Create specialized math agents
calculation_agent = Agent(
    name="CalculationAgent",
    role="Mathematical calculation specialist",
    goal="Perform accurate mathematical calculations and computations",
    backstory="You are an expert mathematician who can handle complex calculations with precision.",
    instructions="Perform the requested calculations step by step, showing your work clearly.",
    tools=[basic_calculator, solve_quadratic, calculate_statistics],
    self_reflect=True,
    min_reflect=1,
    max_reflect=2
)

problem_solver_agent = Agent(
    name="ProblemSolver",
    role="Mathematical problem solver",
    goal="Solve complex math problems with detailed explanations",
    backstory="You are a math teacher who excels at breaking down complex problems into understandable steps.",
    instructions="""When solving math problems:
1. Identify the type of problem
2. List the given information
3. Determine what needs to be found
4. Show each step of the solution
5. Verify the answer makes sense""",
    self_reflect=True,
    min_reflect=2,
    max_reflect=4
)

math_tutor_agent = Agent(
    name="MathTutor",
    role="Mathematics tutor and explainer",
    goal="Explain mathematical concepts clearly and help users understand math",
    backstory="You are a patient math tutor who can explain concepts at any level from elementary to advanced.",
    instructions="Explain mathematical concepts using simple language, provide examples, and check for understanding."
)

# Example workflow for solving complex problems
def solve_math_problem_workflow():
    # Task 1: Understand the problem
    understand_task = Task(
        name="understand_problem",
        description="""A farmer has a rectangular field. The length is 3 meters more than twice the width. 
        If the perimeter is 96 meters, what are the dimensions of the field?""",
        expected_output="Clear problem statement with identified variables and equations",
        agent=problem_solver_agent
    )
    
    # Task 2: Solve the problem
    solve_task = Task(
        name="solve_problem",
        description="Solve for the dimensions using the equations identified",
        expected_output="The width and length of the field with calculations shown",
        agent=calculation_agent,
        context=[understand_task]
    )
    
    # Task 3: Verify and explain
    verify_task = Task(
        name="verify_solution",
        description="Verify the solution is correct and explain why it makes sense",
        expected_output="Verification that the solution satisfies all conditions",
        agent=math_tutor_agent,
        context=[solve_task]
    )
    
    workflow = PraisonAIAgents(
        agents=[problem_solver_agent, calculation_agent, math_tutor_agent],
        tasks=[understand_task, solve_task, verify_task],
        process="sequential",
        verbose=True
    )
    
    return workflow.start()

# General math assistant combining all capabilities
math_assistant = Agent(
    name="MathAssistant",
    role="Comprehensive mathematics assistant",
    goal="Help with any mathematical task from basic arithmetic to complex problem solving",
    backstory="You are an AI math assistant with expertise in all areas of mathematics.",
    instructions="""You can help with:
1. Basic arithmetic and calculations
2. Algebra and equation solving
3. Geometry and trigonometry
4. Calculus and advanced mathematics
5. Statistics and probability
6. Math tutoring and explanations

Always show your work step by step.""",
    tools=[basic_calculator, solve_quadratic, calculate_statistics],
    self_reflect=True,
    min_reflect=1,
    max_reflect=3
)

if __name__ == "__main__":
    # Example 1: Basic calculation
    print("=== Basic Calculation ===")
    result = calculation_agent.start("Calculate: (15 + 23) * 4 - 18 / 3")
    print(result)
    
    # Example 2: Quadratic equation
    print("\n=== Quadratic Equation ===")
    result = calculation_agent.start("Solve the equation: 2x² - 5x + 3 = 0")
    print(result)
    
    # Example 3: Statistics
    print("\n=== Statistics ===")
    result = calculation_agent.start("Calculate statistics for: [12, 15, 18, 20, 22, 25, 28, 30]")
    print(result)
    
    # Example 4: Complex problem workflow
    print("\n=== Complex Problem Workflow ===")
    result = solve_math_problem_workflow()
    print(f"Workflow Result: {result}")
    
    # Example 5: General math assistance
    print("\n=== General Math Assistance ===")
    result = math_assistant.start("""
    I need help with this problem:
    A ball is thrown upward with an initial velocity of 20 m/s. 
    The height h(t) = 20t - 5t² where t is time in seconds.
    
    1. When does the ball reach maximum height?
    2. What is the maximum height?
    3. When does the ball hit the ground?
    """)
    print(result)
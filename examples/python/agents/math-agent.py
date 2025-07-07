from praisonaiagents import Agent
import ast
import math

# Custom math tools
def basic_calculator(expression: str) -> str:
    """Evaluate basic mathematical expressions safely."""
    try:
        # Use ast.literal_eval for safer evaluation
        # Note: This only supports basic literals, not complex expressions
        # For a production system, use a proper math expression parser
        result = ast.literal_eval(expression)
        return f"Result: {result}"
    except Exception:
        # For more complex expressions, provide manual calculation guidance
        return f"Please break down '{expression}' into simpler steps for calculation"

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

# Create math agent
agent = Agent(
    instructions="""You are a comprehensive mathematics assistant who can help with:
1. Basic arithmetic and calculations
2. Algebra and equation solving
3. Geometry and trigonometry
4. Calculus and advanced mathematics
5. Statistics and probability
6. Math tutoring and explanations

Always show your work step by step and explain your reasoning clearly.""",
    tools=[basic_calculator, solve_quadratic, calculate_statistics]
)

# Run the agent
agent.start("""
I need help with this problem:
A ball is thrown upward with an initial velocity of 20 m/s. 
The height h(t) = 20t - 5t² where t is time in seconds.

1. When does the ball reach maximum height?
2. What is the maximum height?
3. When does the ball hit the ground?
""")
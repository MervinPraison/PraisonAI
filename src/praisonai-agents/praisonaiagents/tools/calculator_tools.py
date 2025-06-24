"""Tools for performing calculations.

Usage:
from praisonaiagents.tools import calculator_tools
result = calculator_tools.evaluate("2 + 2 * 3")

or
from praisonaiagents.tools import evaluate, solve_equation, convert_units
result = evaluate("2 + 2 * 3")
"""

import logging
from typing import List, Dict, Optional, Any
from importlib import util
import math

class CalculatorTools:
    """Tools for performing calculations."""
    
    def __init__(self):
        """Initialize CalculatorTools."""
        self._check_dependencies()
        
    def _check_dependencies(self):
        """Check if required packages are installed."""
        missing = []
        for package in ['sympy', 'pint']:
            if util.find_spec(package) is None:
                missing.append(package)
        
        if missing:
            raise ImportError(
                f"Required packages not available. Please install: {', '.join(missing)}\n"
                f"Run: pip install {' '.join(missing)}"
            )

    def evaluate(
        self,
        expression: str,
        variables: Optional[Dict[str, float]] = None,
        precision: int = 10
    ) -> Dict[str, Any]:
        """Evaluate a mathematical expression."""
        try:
            if util.find_spec('sympy') is None:
                error_msg = "sympy package is not available. Please install it using: pip install sympy"
                logging.error(error_msg)
                return {"error": error_msg}

            # Import sympy only when needed
            import sympy

            # Replace common mathematical functions
            expression = expression.lower()
            replacements = {
                'sin(': 'math.sin(',
                'cos(': 'math.cos(',
                'tan(': 'math.tan(',
                'sqrt(': 'math.sqrt(',
                'log(': 'math.log(',
                'exp(': 'math.exp(',
                'pi': str(math.pi),
                'e': str(math.e)
            }
            for old, new in replacements.items():
                expression = expression.replace(old, new)
            
            # Create safe namespace
            safe_dict = {
                'math': math,
                '__builtins__': None
            }
            if variables:
                safe_dict.update(variables)
            
            # Evaluate expression
            result = eval(expression, safe_dict)
            
            # Round to specified precision
            if isinstance(result, (int, float)):
                return {"result": round(float(result), precision)}
            return {"error": "Invalid expression"}
        except Exception as e:
            error_msg = f"Error evaluating expression: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def solve_equation(
        self,
        equation: str,
        variable: str = 'x'
    ) -> Dict[str, Any]:
        """Solve a mathematical equation."""
        try:
            if util.find_spec('sympy') is None:
                error_msg = "sympy package is not available. Please install it using: pip install sympy"
                logging.error(error_msg)
                return {"error": error_msg}

            # Import sympy only when needed
            import sympy

            # Parse equation
            if '=' in equation:
                left, right = equation.split('=')
                equation = f"({left}) - ({right})"
            
            # Convert to SymPy expression
            x = sympy.Symbol(variable)
            expr = sympy.sympify(equation)
            
            # Solve equation
            solutions = sympy.solve(expr, x)
            
            # Convert complex solutions to real if possible
            real_solutions = []
            for sol in solutions:
                if sol.is_real:
                    real_solutions.append(float(sol))
            
            return {"solutions": real_solutions} if real_solutions else {"error": "No real solutions found"}
        except Exception as e:
            error_msg = f"Error solving equation: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def convert_units(
        self,
        value: float,
        from_unit: str,
        to_unit: str
    ) -> Dict[str, Any]:
        """Convert between different units."""
        try:
            if util.find_spec('pint') is None:
                error_msg = "pint package is not available. Please install it using: pip install pint"
                logging.error(error_msg)
                return {"error": error_msg}

            # Import pint only when needed
            import pint

            # Create quantity with source unit
            ureg = pint.UnitRegistry()
            quantity = value * ureg(from_unit)
            
            # Convert to target unit
            result = quantity.to(to_unit)
            
            return {"result": float(result.magnitude)}
        except Exception as e:
            error_msg = f"Error converting units: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def calculate_statistics(
        self,
        numbers: List[float]
    ) -> Dict[str, Any]:
        """Calculate basic statistics for a list of numbers."""
        try:
            if not numbers:
                return {"error": "No numbers provided"}
            
            n = len(numbers)
            mean = sum(numbers) / n
            
            # Calculate variance and std dev
            squared_diff_sum = sum((x - mean) ** 2 for x in numbers)
            variance = squared_diff_sum / (n - 1) if n > 1 else 0
            std_dev = math.sqrt(variance)
            
            # Calculate median
            sorted_nums = sorted(numbers)
            if n % 2 == 0:
                median = (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
            else:
                median = sorted_nums[n//2]
            
            return {
                "mean": mean,
                "median": median,
                "std_dev": std_dev,
                "variance": variance,
                "min": min(numbers),
                "max": max(numbers),
                "range": max(numbers) - min(numbers),
                "count": n
            }
        except Exception as e:
            error_msg = f"Error calculating statistics: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def calculate_financial(
        self,
        principal: float,
        rate: float,
        time: float,
        frequency: str = 'yearly'
    ) -> Dict[str, Any]:
        """Calculate financial metrics like compound interest."""
        try:
            # Convert rate to decimal
            rate = rate / 100
            
            # Get compounding frequency
            freq_map = {
                'yearly': 1,
                'semi-annual': 2,
                'quarterly': 4,
                'monthly': 12,
                'daily': 365
            }
            n = freq_map.get(frequency.lower(), 1)
            
            # Calculate compound interest
            amount = principal * (1 + rate/n)**(n*time)
            interest = amount - principal
            
            # Calculate simple interest
            simple_interest = principal * rate * time
            
            return {
                "final_amount": amount,
                "compound_interest": interest,
                "simple_interest": simple_interest,
                "difference": interest - simple_interest
            }
        except Exception as e:
            error_msg = f"Error calculating financial metrics: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

# Create instance for direct function access
_calculator_tools = CalculatorTools()
evaluate = _calculator_tools.evaluate
solve_equation = _calculator_tools.solve_equation
convert_units = _calculator_tools.convert_units
calculate_statistics = _calculator_tools.calculate_statistics
calculate_financial = _calculator_tools.calculate_financial

if __name__ == "__main__":
    print("\n==================================================")
    print("CalculatorTools Demonstration")
    print("==================================================\n")

    print("1. Basic Arithmetic")
    print("------------------------------")
    print("2 + 2 =", evaluate("2 + 2")["result"])
    print("5 * 6 =", evaluate("5 * 6")["result"])
    print("10 / 3 =", evaluate("10 / 3")["result"])
    print()

    print("2. Complex Expressions")
    print("------------------------------")
    print("(2 + 3) * 4 =", evaluate("(2 + 3) * 4")["result"])
    print("2^3 + 4 =", evaluate("2^3 + 4")["result"])
    print("sqrt(16) + 2 =", evaluate("sqrt(16) + 2")["result"])
    print()

    print("3. Solving Equations")
    print("------------------------------")
    result = solve_equation("x^2 - 5*x + 6 = 0")
    print("x^2 - 5*x + 6 = 0")
    print("Solutions:", result["solutions"])
    print()

    print("4. Unit Conversions")
    print("------------------------------")
    print("100 meters to kilometers:", convert_units(100, "meters", "kilometers")["result"])
    print("1 hour to minutes:", convert_units(1, "hours", "minutes")["result"])
    print("32 fahrenheit to celsius:", convert_units(32, "fahrenheit", "celsius")["result"])
    print()

    print("==================================================")
    print("Demonstration Complete")
    print("==================================================")

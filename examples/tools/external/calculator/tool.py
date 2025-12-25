"""Calculator Tool Example.

This example demonstrates how to use the Calculator tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"

Usage:
    python tool.py

Note: No API key required!
"""

from praisonai_tools import CalculatorTool


def main():
    # Initialize Calculator tool
    calc = CalculatorTool()
    
    # Example 1: Basic arithmetic
    print("=" * 60)
    print("Example 1: Basic Arithmetic")
    print("=" * 60)
    
    expressions = [
        "2 + 2",
        "10 * 5",
        "100 / 4",
        "2 ** 10",
        "(10 + 5) * 2 - 3"
    ]
    
    for expr in expressions:
        result = calc.evaluate(expr)
        print(f"  {expr} = {result.get('result', result)}")
    
    # Example 2: Percentage calculation
    print("\n" + "=" * 60)
    print("Example 2: Percentage Calculation")
    print("=" * 60)
    
    result = calc.evaluate("250 * 0.15")
    print(f"  15% of 250 = {result.get('result', result)}")
    
    result = calc.evaluate("1000 * (1 + 0.05) ** 3")
    print(f"  $1000 at 5% for 3 years = ${result.get('result', 0):.2f}")
    
    print("\n✅ Calculator tool working correctly!")


if __name__ == "__main__":
    main()

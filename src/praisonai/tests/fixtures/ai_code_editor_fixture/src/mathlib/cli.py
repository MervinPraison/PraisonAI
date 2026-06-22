"""Command-line interface for mathlib. MISSING version command."""
import sys
from .calculator import Calculator


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m mathlib.cli <command>")
        return
    
    command = sys.argv[1]
    
    if command == "add":
        if len(sys.argv) < 4:
            print("Usage: add <a> <b>")
            return
        a, b = float(sys.argv[2]), float(sys.argv[3])
        calc = Calculator()
        result = calc.add(a, b)
        print(f"{a} + {b} = {result}")
    
    # TODO: Add version command
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
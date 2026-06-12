# MathLib Test Fixture

This is a test fixture for the AI code editor smoke tests. It contains a simple Python project with intentional bugs and missing implementations to test the AI's ability to:

- Implement missing functions
- Fix bugs in existing code  
- Run tests and verify fixes
- Handle linting issues

## Structure

- `src/mathlib/` - Main package with intentional issues
- `tests/` - Test suite that should initially fail
- `pyproject.toml` - Project configuration

## Known Issues (Intentional)

1. `converter.py` - Missing implementations for temperature conversion
2. `calculator.py` - Division by zero not handled
3. `stats.py` - Empty list handling missing, mode not implemented  
4. `cli.py` - Version command missing
5. Various linting issues

The AI should be able to fix these issues through iterative prompting.
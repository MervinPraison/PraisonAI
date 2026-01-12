"""
Advanced Agent-Centric Test Scenarios.

5 complex scenarios where the agent must AUTONOMOUSLY figure out how to complete
the task using ONLY a single text prompt. No step-by-step instructions.

Scenarios:
- ADV_01: Bug Fix & Testing - Find bug, write tests, fix it
- ADV_02: Data Pipeline - Create JSON to CSV transformer
- ADV_03: API Client - Build REST client with error handling
- ADV_04: Documentation - Analyze code and generate docs
- ADV_05: Package Creation - Create complete Python package
"""

from typing import List

from ..runner import InteractiveScenario


# =============================================================================
# ADV_01: BUG FIX & TESTING
# =============================================================================

SCENARIO_ADV_01 = InteractiveScenario(
    id="adv_01",
    name="Bug Fix & Testing",
    description="Agent must find a bug, write a test that exposes it, fix it, and verify",
    prompts=[
        """I have a Python file called calculator.py with the following buggy code:

```python
def add(a, b):
    return a + b

def subtract(a, b):
    return a + b  # BUG: should be a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    return a / b
```

Your task:
1. Create this calculator.py file
2. Create a test file test_calculator.py with tests for ALL functions
3. Run the tests to find which one fails
4. Fix the bug in calculator.py
5. Run tests again to verify the fix works

Show me the final working code and test results."""
    ],
    expected_tools=["acp_create_file"],
    expected_files={
        "calculator.py": r"def subtract.*return a - b",
        "test_calculator.py": r"def test_|import.*calculator",
    },
    timeout=180,
)


# =============================================================================
# ADV_02: DATA PIPELINE
# =============================================================================

SCENARIO_ADV_02 = InteractiveScenario(
    id="adv_02",
    name="Data Pipeline",
    description="Agent must create a data transformation pipeline",
    prompts=[
        """Create a complete data processing pipeline that:

1. Creates a sample data file called 'users.json' with this content:
   [
     {"name": "Alice", "age": 30, "city": "NYC"},
     {"name": "Bob", "age": 25, "city": "LA"},
     {"name": "Charlie", "age": 35, "city": "Chicago"}
   ]

2. Creates a Python script called 'transform.py' that:
   - Reads the JSON file
   - Filters users older than 28
   - Converts to CSV format
   - Saves to 'output.csv'

3. Run the script to generate output.csv

4. Show me the contents of output.csv

The agent should figure out the best approach to accomplish this."""
    ],
    expected_tools=["acp_create_file"],
    expected_files={
        "users.json": r"Alice|Bob|Charlie",
        "transform.py": r"import json|csv|open",
    },
    expected_response=r"Alice|Charlie|csv|output",
    timeout=180,
)


# =============================================================================
# ADV_03: API CLIENT
# =============================================================================

SCENARIO_ADV_03 = InteractiveScenario(
    id="adv_03",
    name="API Client",
    description="Agent must build a REST API client with proper error handling",
    prompts=[
        """Create a Python module for making HTTP requests with proper error handling.

Requirements:
1. Create a file called 'api_client.py' with a class called 'APIClient' that has:
   - __init__(self, base_url) - stores the base URL
   - get(self, endpoint) - makes GET request, returns JSON response
   - post(self, endpoint, data) - makes POST request with JSON body
   - Proper error handling for network errors and HTTP errors
   - A timeout parameter (default 30 seconds)

2. Create a file called 'test_api_client.py' with unit tests that:
   - Test the class can be instantiated
   - Test error handling works (mock or check exception types)

3. Show me the complete implementation

The code should be production-quality with docstrings and type hints."""
    ],
    expected_tools=["acp_create_file"],
    expected_files={
        "api_client.py": r"class APIClient|def get|def post|except|timeout",
        "test_api_client.py": r"def test_|APIClient",
    },
    timeout=180,
)


# =============================================================================
# ADV_04: DOCUMENTATION GENERATOR
# =============================================================================

SCENARIO_ADV_04 = InteractiveScenario(
    id="adv_04",
    name="Documentation Generator",
    description="Agent must analyze code and generate comprehensive documentation",
    prompts=[
        """I need you to create a Python module and then generate documentation for it.

Step 1: Create a file called 'utils.py' with these utility functions:
- format_date(date_obj) - formats a date to 'YYYY-MM-DD'
- parse_csv_line(line) - splits a CSV line handling quoted fields
- slugify(text) - converts text to URL-friendly slug
- truncate(text, max_length) - truncates text with ellipsis

Each function should have proper implementation (not just pass).

Step 2: Create a file called 'README.md' that documents:
- Module overview
- Each function with description, parameters, return value, and example usage
- Installation/usage instructions

Make the documentation clear and professional."""
    ],
    expected_tools=["acp_create_file"],
    expected_files={
        "utils.py": r"def format_date|def parse_csv|def slugify|def truncate",
        "README.md": r"format_date|parse_csv|slugify|truncate|##|Usage",
    },
    timeout=180,
)


# =============================================================================
# ADV_05: COMPLETE PACKAGE
# =============================================================================

SCENARIO_ADV_05 = InteractiveScenario(
    id="adv_05",
    name="Complete Package",
    description="Agent must create a complete Python package structure",
    prompts=[
        """Create a complete Python package called 'mathtools' with proper structure.

The package should include:

1. Package structure:
   - mathtools/__init__.py (exports main functions)
   - mathtools/operations.py (basic math: add, subtract, multiply, divide)
   - mathtools/statistics.py (mean, median, mode functions)
   - tests/test_operations.py (tests for operations)
   - tests/test_statistics.py (tests for statistics)
   - pyproject.toml (modern Python packaging)
   - README.md (package documentation)

2. All functions should have:
   - Type hints
   - Docstrings
   - Proper implementation (not stubs)

3. Tests should be runnable with pytest

Create all files and show me the package structure."""
    ],
    expected_tools=["acp_create_file"],
    expected_files={
        "mathtools/__init__.py": r"from.*import|__all__",
        "mathtools/operations.py": r"def add|def subtract|def multiply|def divide",
        "mathtools/statistics.py": r"def mean|def median",
        "pyproject.toml": r"name.*=.*mathtools|project",
    },
    timeout=240,
)


# =============================================================================
# ALL SCENARIOS
# =============================================================================

ALL_ADVANCED_SCENARIOS: List[InteractiveScenario] = [
    SCENARIO_ADV_01,
    SCENARIO_ADV_02,
    SCENARIO_ADV_03,
    SCENARIO_ADV_04,
    SCENARIO_ADV_05,
]


def get_scenario_by_id(scenario_id: str) -> InteractiveScenario:
    """Get a scenario by its ID."""
    for s in ALL_ADVANCED_SCENARIOS:
        if s.id == scenario_id:
            return s
    raise ValueError(f"Scenario {scenario_id} not found")


__all__ = [
    "SCENARIO_ADV_01",
    "SCENARIO_ADV_02",
    "SCENARIO_ADV_03",
    "SCENARIO_ADV_04",
    "SCENARIO_ADV_05",
    "ALL_ADVANCED_SCENARIOS",
    "get_scenario_by_id",
]

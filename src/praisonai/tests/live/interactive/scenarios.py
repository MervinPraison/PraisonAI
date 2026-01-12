"""Interactive mode test scenarios.

20 scenarios covering all interactive mode capabilities:
- Basic chat (3)
- File operations (5)
- Code intelligence (4)
- Multi-step workflows (4)
- Multi-agent (2)
- Edge cases (2)
"""

from typing import List

from .runner import InteractiveScenario


# =============================================================================
# BASIC CHAT SCENARIOS (3)
# =============================================================================

SCENARIO_01_HELLO = InteractiveScenario(
    id="int_01",
    name="Basic Hello",
    description="Test basic chat response without tools",
    prompts=["Hello! What is 2 + 2?"],
    expected_tools=[],
    expected_response=r"4",
    timeout=30,
)

SCENARIO_02_REASONING = InteractiveScenario(
    id="int_02",
    name="Simple Reasoning",
    description="Test reasoning capability",
    prompts=["If I have 3 apples and give away 1, how many do I have left?"],
    expected_tools=[],
    expected_response=r"2",
    timeout=30,
)

SCENARIO_03_EXPLAIN = InteractiveScenario(
    id="int_03",
    name="Code Explanation",
    description="Test code explanation without file access",
    prompts=["Explain what this Python code does: print('Hello, World!')"],
    expected_tools=[],
    expected_response=r"print|Hello|output",
    timeout=30,
)


# =============================================================================
# FILE OPERATIONS SCENARIOS (5)
# =============================================================================

SCENARIO_04_CREATE_FILE = InteractiveScenario(
    id="int_04",
    name="Create File",
    description="Test creating a new file with content",
    prompts=["Create a file called hello.py with the content: print('hello world')"],
    expected_tools=["acp_create_file"],
    expected_files={"hello.py": r"print.*hello"},
    timeout=60,
)

SCENARIO_05_READ_FILE = InteractiveScenario(
    id="int_05",
    name="Read File",
    description="Test reading an existing file",
    prompts=["Read the file README.md and tell me what it says"],
    expected_tools=["read_file"],
    expected_response=r"Test Project|README",
    workspace_fixture="seeded",
    timeout=60,
)

SCENARIO_06_LIST_FILES = InteractiveScenario(
    id="int_06",
    name="List Files",
    description="Test listing files in directory",
    prompts=["List all files in the current directory"],
    expected_tools=["list_files"],
    expected_response=r"README|main\.py|config",
    workspace_fixture="seeded",
    timeout=60,
)

SCENARIO_07_EDIT_FILE = InteractiveScenario(
    id="int_07",
    name="Edit File",
    description="Test editing an existing file",
    prompts=[
        "Create a file called counter.py with: count = 1",
        "Edit counter.py to change count = 1 to count = 10",
    ],
    expected_tools=["acp_create_file", "acp_edit_file"],
    expected_files={"counter.py": r"count\s*=\s*10"},
    timeout=90,
)

SCENARIO_08_DELETE_FILE = InteractiveScenario(
    id="int_08",
    name="Delete File",
    description="Test deleting a file",
    prompts=[
        "Create a file called temp.txt with content: temporary",
        "Delete the file temp.txt",
    ],
    expected_tools=["acp_create_file", "acp_delete_file"],
    expected_response=r"deleted|removed",
    timeout=60,
)


# =============================================================================
# CODE INTELLIGENCE SCENARIOS (4)
# =============================================================================

SCENARIO_09_LIST_SYMBOLS = InteractiveScenario(
    id="int_09",
    name="List Symbols",
    description="Test listing symbols in a Python file",
    prompts=[
        "Create a file calc.py with:\ndef add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b",
        "List all functions in calc.py",
    ],
    expected_tools=["acp_create_file", "lsp_list_symbols"],
    expected_response=r"add|subtract",
    timeout=90,
)

SCENARIO_10_FIND_DEFINITION = InteractiveScenario(
    id="int_10",
    name="Find Definition",
    description="Test finding symbol definition",
    prompts=["Find where the function 'main' is defined in main.py"],
    expected_tools=["lsp_find_definition"],
    workspace_fixture="python_project",
    timeout=60,
)

SCENARIO_11_FIND_REFERENCES = InteractiveScenario(
    id="int_11",
    name="Find References",
    description="Test finding symbol references",
    prompts=["Find all references to the 'add' function in utils.py"],
    expected_tools=["lsp_find_references"],
    workspace_fixture="python_project",
    timeout=60,
)

SCENARIO_12_EXECUTE_COMMAND = InteractiveScenario(
    id="int_12",
    name="Execute Command",
    description="Test executing a shell command",
    prompts=["Run the command: echo 'Hello from shell'"],
    expected_tools=[],  # May use acp_execute_command or execute_command
    expected_response=r"Hello.*shell|echo",
    timeout=30,
)


# =============================================================================
# MULTI-STEP WORKFLOW SCENARIOS (4)
# =============================================================================

SCENARIO_13_CREATE_AND_READ = InteractiveScenario(
    id="int_13",
    name="Create and Read",
    description="Test creating a file then reading it back",
    prompts=[
        "Create a file called greeting.txt with: Hello, PraisonAI!",
        "Read the file greeting.txt and confirm its contents",
    ],
    expected_tools=["acp_create_file", "read_file"],
    expected_files={"greeting.txt": r"Hello.*PraisonAI"},
    expected_response=r"Hello.*PraisonAI",
    timeout=90,
)

SCENARIO_14_REFACTOR_WORKFLOW = InteractiveScenario(
    id="int_14",
    name="Refactor Workflow",
    description="Test a refactoring workflow: read, analyze, edit",
    prompts=[
        "Read main.py and tell me what it does",
        "Add a docstring to the main function in main.py",
    ],
    expected_tools=["read_file"],  # Edit tool varies
    expected_files={"main.py": r'""".*"""|docstring|Main'},
    workspace_fixture="python_project",
    timeout=120,
)

SCENARIO_15_COPY_FILE = InteractiveScenario(
    id="int_15",
    name="Copy File Content",
    description="Test reading one file and creating another with same content",
    prompts=[
        "Read the file main.py and show me its content",
        "Now create a new file called backup.py with a simple print statement",
    ],
    expected_tools=["read_file"],  # Create tool varies
    expected_files={"backup.py": r"print"},
    workspace_fixture="python_project",
    timeout=90,
)

SCENARIO_16_ANALYZE_AND_FIX = InteractiveScenario(
    id="int_16",
    name="Analyze and Fix",
    description="Test analyzing code and making improvements",
    prompts=[
        "Create a file buggy.py with:\ndef divide(a, b):\n    return a / b",
        "Fix buggy.py to handle division by zero by raising ValueError",
    ],
    expected_tools=["acp_create_file", "acp_edit_file"],
    expected_files={"buggy.py": r"ValueError|zero|if.*b.*==.*0"},
    timeout=90,
)


# =============================================================================
# MULTI-AGENT SCENARIOS (2)
# =============================================================================

SCENARIO_17_SIMPLE_HANDOFF = InteractiveScenario(
    id="int_17",
    name="Simple Task Delegation",
    description="Test handling a task that requires multiple steps",
    prompts=[
        "First, create a file called task.py with: # TODO: implement",
        "Then, edit task.py to add a function called process() that returns 'done'",
    ],
    expected_tools=["acp_create_file", "acp_edit_file"],
    expected_files={"task.py": r"def process.*return.*done"},
    timeout=120,
)

SCENARIO_18_RESEARCH_AND_CODE = InteractiveScenario(
    id="int_18",
    name="Research and Code",
    description="Test combining information gathering with code generation",
    prompts=[
        "List the files in the current directory",
        "Based on what you see, create a new file called summary.txt describing the project structure",
    ],
    expected_tools=["list_files", "acp_create_file"],
    expected_files={"summary.txt": r"file|directory|project"},
    workspace_fixture="seeded",
    timeout=90,
)


# =============================================================================
# EDGE CASE SCENARIOS (2)
# =============================================================================

SCENARIO_19_EMPTY_RESPONSE = InteractiveScenario(
    id="int_19",
    name="Handle Empty Input",
    description="Test handling minimal input gracefully",
    prompts=["Hi"],
    expected_tools=[],
    timeout=30,
)

SCENARIO_20_COMPLEX_PROMPT = InteractiveScenario(
    id="int_20",
    name="Complex Multi-Part Request",
    description="Test handling a complex request with multiple parts",
    prompts=[
        "Create a Python module called mathops.py with two functions: add(a, b) that returns a+b, and multiply(a, b) that returns a*b. Include docstrings for each function.",
    ],
    expected_tools=["acp_create_file"],
    expected_files={"mathops.py": r"def add.*def multiply|def multiply.*def add"},
    timeout=90,
)


# =============================================================================
# ALL SCENARIOS
# =============================================================================

ALL_SCENARIOS: List[InteractiveScenario] = [
    # Basic Chat (3)
    SCENARIO_01_HELLO,
    SCENARIO_02_REASONING,
    SCENARIO_03_EXPLAIN,
    # File Operations (5)
    SCENARIO_04_CREATE_FILE,
    SCENARIO_05_READ_FILE,
    SCENARIO_06_LIST_FILES,
    SCENARIO_07_EDIT_FILE,
    SCENARIO_08_DELETE_FILE,
    # Code Intelligence (4)
    SCENARIO_09_LIST_SYMBOLS,
    SCENARIO_10_FIND_DEFINITION,
    SCENARIO_11_FIND_REFERENCES,
    SCENARIO_12_EXECUTE_COMMAND,
    # Multi-step Workflows (4)
    SCENARIO_13_CREATE_AND_READ,
    SCENARIO_14_REFACTOR_WORKFLOW,
    SCENARIO_15_COPY_FILE,
    SCENARIO_16_ANALYZE_AND_FIX,
    # Multi-agent (2)
    SCENARIO_17_SIMPLE_HANDOFF,
    SCENARIO_18_RESEARCH_AND_CODE,
    # Edge Cases (2)
    SCENARIO_19_EMPTY_RESPONSE,
    SCENARIO_20_COMPLEX_PROMPT,
]


def get_scenarios_by_category(category: str) -> List[InteractiveScenario]:
    """Get scenarios by category."""
    categories = {
        "basic": [SCENARIO_01_HELLO, SCENARIO_02_REASONING, SCENARIO_03_EXPLAIN],
        "files": [SCENARIO_04_CREATE_FILE, SCENARIO_05_READ_FILE, SCENARIO_06_LIST_FILES,
                  SCENARIO_07_EDIT_FILE, SCENARIO_08_DELETE_FILE],
        "code": [SCENARIO_09_LIST_SYMBOLS, SCENARIO_10_FIND_DEFINITION,
                 SCENARIO_11_FIND_REFERENCES, SCENARIO_12_EXECUTE_COMMAND],
        "workflow": [SCENARIO_13_CREATE_AND_READ, SCENARIO_14_REFACTOR_WORKFLOW,
                     SCENARIO_15_COPY_FILE, SCENARIO_16_ANALYZE_AND_FIX],
        "multi": [SCENARIO_17_SIMPLE_HANDOFF, SCENARIO_18_RESEARCH_AND_CODE],
        "edge": [SCENARIO_19_EMPTY_RESPONSE, SCENARIO_20_COMPLEX_PROMPT],
    }
    return categories.get(category, [])

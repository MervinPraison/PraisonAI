"""Test script with forced verbose mode to verify PraisonAI's unique output UI."""
import sys
from rich.console import Console

# Force Rich to think we're in a TTY for testing
console = Console(force_terminal=True)

from praisonaiagents import Agent
from praisonaiagents.main import (
    display_interaction, 
    display_instruction, 
    display_tool_call,
    display_reasoning_steps,
    display_working_status,
    display_error,
    PRAISON_COLORS
)

print("=" * 70)
print("TESTING PRAISONAI UNIQUE VERBOSE OUTPUT UI")
print("=" * 70)

# Test 1: Display Agent Info panel
print("\n[TEST 1] Agent Info Panel (Sage Green border)")
display_instruction(
    message="Test instruction",
    console=console,
    agent_name="ResearchAgent",
    agent_role="Data Analyst",
    agent_tools=["search_web", "calculate", "read_file"]
)

# Test 2: Display interaction with semantic colors
print("\n[TEST 2] Task (Coral) + Response (Ocean Blue) panels")
display_interaction(
    message="What is 2+2?",
    response="2+2 equals 4. This is a basic arithmetic operation.",
    markdown=True,
    generation_time=1.5,
    console=console
)

# Test 3: Display interaction with metrics footer
print("\n[TEST 3] Response with Metrics Footer")
display_interaction(
    message="Explain quantum computing",
    response="Quantum computing uses qubits instead of classical bits.",
    markdown=True,
    generation_time=3.2,
    console=console,
    metrics={
        'tokens_in': 45,
        'tokens_out': 128,
        'cost': 0.0023,
        'model': 'gpt-4o-mini'
    }
)

# Test 4: Display tool call with timeline format
print("\n[TEST 4] Tool Activity Panel (Violet border, timeline format)")
display_tool_call(
    message="search_web(query='quantum computing')",
    console=console,
    tool_name="search_web",
    tool_input={"query": "quantum computing"},
    tool_output="Found 5 relevant articles",
    elapsed_time=0.8,
    success=True
)

# Test 5: Display tool call failure
print("\n[TEST 5] Tool Activity Panel (Failed call)")
display_tool_call(
    message="api_call failed",
    console=console,
    tool_name="api_call",
    tool_input={"endpoint": "/users", "method": "GET"},
    tool_output="Connection timeout",
    elapsed_time=5.0,
    success=False
)

# Test 6: Display reasoning steps with numbered circles
print("\n[TEST 6] Reasoning Steps (Numbered circles ①②③)")
display_reasoning_steps(
    steps=[
        "Identified query about arithmetic",
        "Retrieved basic math rules",
        "Calculated result: 2+2=4",
        "Formulated concise response"
    ],
    console=console
)

# Test 7: Display working status (static, shows format)
print("\n[TEST 7] Working Status (Amber border, pulsing dots)")
for phase in range(4):
    panel = display_working_status(phase=phase, console=console)
    console.print(panel)

# Test 8: Display error
print("\n[TEST 8] Error Panel (Red border)")
display_error(
    message="API rate limit exceeded. Please try again in 60 seconds.",
    console=console
)

print("\n" + "=" * 70)
print("COLORS BEING USED:")
for name, color in PRAISON_COLORS.items():
    console.print(f"  {name}: [bold {color}]████████[/] {color}")
print("=" * 70)

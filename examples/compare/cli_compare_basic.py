"""
CLI Compare Example - Basic Usage

This example demonstrates how to compare different CLI modes programmatically.
"""

from praisonai.cli.features.compare import (
    CompareHandler,
    get_mode_config,
    list_available_modes,
    parse_modes,
)

# List all available comparison modes
print("Available modes:")
for mode in list_available_modes():
    config = get_mode_config(mode)
    print(f"  - {mode}: {config}")

# Parse modes from comma-separated string
modes = parse_modes("basic,tools,planning")
print(f"\nParsed modes: {modes}")

# Create compare handler
handler = CompareHandler(verbose=True)

# Compare modes (this will run actual agent calls)
# Uncomment to run:
# result = handler.compare(
#     query="What is artificial intelligence?",
#     modes=["basic", "tools"],
#     model="gpt-4o-mini"
# )
# handler.print_result(result)

# Save results to file
# result = handler.execute(
#     query="Explain machine learning",
#     modes_str="basic,planning",
#     output_path="comparison_results.json"
# )

print("\nTo run comparison via CLI:")
print('  praisonai "What is AI?" --compare "basic,tools,planning"')
print('  praisonai "What is AI?" --compare "basic,research" --compare-output results.json')

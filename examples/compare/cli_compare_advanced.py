"""
CLI Compare Example - Advanced Usage

This example demonstrates advanced comparison features including
custom mode configurations and result analysis.
"""

from praisonai.cli.features.compare import (
    CompareHandler,
    CompareResult,
    ModeResult,
    get_mode_config,
    save_compare_result,
    format_comparison_table,
)

# Create custom mode configurations
custom_modes = {
    "fast": {"llm": "gpt-4o-mini"},
    "accurate": {"llm": "gpt-4o", "planning": True},
    "research": {"research": True, "web_search": True},
}

# Create handler with verbose output
handler = CompareHandler(output="verbose")

# Example: Manually create comparison results for analysis
# (useful for testing without API calls)
mock_result = CompareResult(
    query="What are the latest AI trends?",
    comparisons=[
        ModeResult(
            mode="basic",
            output="AI trends include LLMs, multimodal models, and agents.",
            execution_time_ms=1234.5,
            model_used="gpt-4o-mini",
            tools_used=[]
        ),
        ModeResult(
            mode="tools",
            output="Based on recent search results, AI trends in 2024 include...",
            execution_time_ms=2567.8,
            model_used="gpt-4o-mini",
            tools_used=["internet_search"]
        ),
        ModeResult(
            mode="research",
            output="Comprehensive research shows that AI trends...",
            execution_time_ms=5432.1,
            model_used="gpt-4o-mini",
            tools_used=["internet_search", "web_scraper"]
        ),
    ]
)

# Get summary statistics
summary = mock_result.get_summary()
print("Comparison Summary:")
print(f"  Fastest mode: {summary['fastest']} ({summary['fastest_time_ms']:.1f}ms)")
print(f"  Slowest mode: {summary['slowest']} ({summary['slowest_time_ms']:.1f}ms)")

# Format as table
print("\n" + format_comparison_table(mock_result))

# Convert to JSON for storage
print("\nJSON Output:")
print(mock_result.to_json())

# Save to file
# save_compare_result(mock_result, "advanced_comparison.json")

print("\n--- CLI Usage Examples ---")
print("""
# Basic comparison
praisonai "What is AI?" --compare "basic,tools"

# Compare with specific model
praisonai "Explain quantum computing" --compare "basic,planning,research" --model gpt-4o

# Save results to file
praisonai "Latest tech news" --compare "basic,tools,web_search" --compare-output results.json

# Verbose output
praisonai "Write a poem" --compare "basic,planning" --verbose
""")

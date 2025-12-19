"""
Cost Tracking Example for PraisonAI CLI.

Real-time token usage and cost monitoring.
Docs: https://docs.praison.ai/cli/cost-tracking
"""

from praisonai.cli.features import CostTrackerHandler

# Initialize tracker
handler = CostTrackerHandler()
tracker = handler.initialize(session_id="demo-session")

# Track some requests
handler.track_request("gpt-4o", input_tokens=1000, output_tokens=500)
handler.track_request("gpt-4o-mini", input_tokens=2000, output_tokens=800)
handler.track_request("claude-3-5-sonnet", input_tokens=1500, output_tokens=600)

# Get totals
print(f"Total tokens: {handler.get_tokens():,}")
print(f"Total cost: ${handler.get_cost():.4f}")

# Get detailed summary
summary = handler.get_summary()
print("\n=== Session Summary ===")
print(f"Session ID: {summary['session_id']}")
print(f"Total requests: {summary['total_requests']}")
print(f"Input tokens: {summary['total_input_tokens']:,}")
print(f"Output tokens: {summary['total_output_tokens']:,}")
print(f"Total cost: ${summary['total_cost']:.4f}")
print(f"Avg cost/request: ${summary['avg_cost_per_request']:.4f}")

# Display formatted (uses Rich if available)
handler.display_summary()

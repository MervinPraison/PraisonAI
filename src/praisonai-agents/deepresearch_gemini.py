"""
Gemini Deep Research Agent Example

Uses Google's deep-research-pro model via the Interactions API
for automated research with web search.

Supports two modes:
1. Polling (default): Checks status periodically, shows progress logs
2. Streaming: Real-time output with thinking summaries (recommended)

Requirements:
    - GEMINI_API_KEY or GOOGLE_API_KEY environment variable
    - google-genai >= 1.55.0 (pip install google-genai)
"""
from dotenv import load_dotenv
load_dotenv()

from praisonaiagents import DeepResearchAgent

agent = DeepResearchAgent(
    name="Gemini Researcher",
    instructions="""
    You are a professional researcher. Focus on:
    - Comprehensive analysis with multiple perspectives
    - Data-backed insights and trends
    - Clear structure with executive summary
    """,
    model="deep-research-pro",  # Auto-detected as Gemini
    verbose=True,
)

print(f"Agent: {agent}")
print(f"Provider: {agent.provider}")

# Streaming is enabled by default for real-time progress updates
# This shows thinking summaries and streams the report as it's generated
result = agent.research(
    "What is the current price of Ethereum?"
    # stream=True is the default, set stream=False to disable
)

# The report is already printed during streaming when verbose=True
# But we can also access it programmatically:
print("\n" + "=" * 60)
print(f"Report length: {len(result.report)} characters")
print(f"Interaction ID: {result.interaction_id}")
print(f"Reasoning steps captured: {len(result.reasoning_steps)}")
print("=" * 60)

"""
OpenAI Deep Research Agent Example

Uses OpenAI's o3-deep-research or o4-mini-deep-research models
via the Responses API for automated research with web search.

Supports two modes:
1. Non-streaming (default): Waits for completion, returns full report
2. Streaming: Real-time progress with reasoning summaries and web searches

Requirements:
    - OPENAI_API_KEY environment variable
"""
from dotenv import load_dotenv
load_dotenv()

from praisonaiagents import DeepResearchAgent

agent = DeepResearchAgent(
    name="Research Assistant",
    instructions="""
    You are a professional researcher. Focus on:
    - Data-rich insights with specific figures
    - Reliable sources and citations
    - Clear, structured responses
    """,
    model="o4-mini-deep-research",  # or "o3-deep-research" for higher quality
    verbose=True
)

print(f"Agent: {agent}")
print(f"Provider: {agent.provider}")

# Streaming is enabled by default for real-time progress updates
# Shows: reasoning summaries, web search queries, and report text as generated
result = agent.research(
    "What is the current price of Bitcoin?"
    # stream=True is the default, set stream=False to disable
)

# The report is already printed during streaming when verbose=True
# But we can also access it programmatically:
print("\n" + "=" * 60)
print(f"Report length: {len(result.report)} characters")
print(f"Citations: {len(result.citations)}")
print(f"Web searches: {len(result.web_searches)}")
print("=" * 60)
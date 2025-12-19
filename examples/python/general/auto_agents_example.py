"""
AutoAgents Example

AutoAgents automatically creates and manages AI agents based on high-level instructions.
It features dynamic agent count based on task complexity.

Documentation: https://docs.praison.ai/features/autoagents
CLI Reference: https://docs.praison.ai/nocode/auto

New Features:
- Dynamic agent count (1-4 based on task complexity)
- Workflow patterns: sequential, parallel, routing, orchestrator-workers, evaluator-optimizer
- Pattern recommendation based on task keywords
- Tool preservation from LLM suggestions
"""

from praisonaiagents import AutoAgents
from praisonaiagents.tools import duckduckgo

# Basic usage - AutoAgents analyzes complexity and creates optimal agents
agents = AutoAgents(
    instructions="Search for information about AI Agents",
    tools=[duckduckgo],
    process="sequential",  # or "hierarchical"
    verbose=True,
    max_agents=3  # Maximum number of agents to create
)

result = agents.start()
print(result)

# =============================================================================
# CLI Usage Examples (for reference)
# =============================================================================
# 
# # Auto-generate agents (dynamic count based on complexity)
# praisonai --auto "Write a haiku about spring"
# praisonai --auto "Research AI trends, analyze data, write report"
#
# # Auto-generate workflow with specific pattern
# praisonai workflow auto "Research and write" --pattern sequential
# praisonai workflow auto "Research from multiple sources" --pattern parallel
# praisonai workflow auto "Comprehensive analysis" --pattern orchestrator-workers
# praisonai workflow auto "Refine content quality" --pattern evaluator-optimizer
#
# # With framework selection
# praisonai --framework crewai --auto "Create a movie script"
# praisonai --framework autogen --auto "Create a movie script"
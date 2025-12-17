"""
Agentic Parallel Workflow Example

Demonstrates running multiple agents concurrently and
combining their results with an aggregator agent.
"""

from praisonaiagents import Agent, Workflow
from praisonaiagents.workflows import parallel

# Create parallel research agents
market_researcher = Agent(
    name="MarketResearcher",
    role="Market Research Analyst",
    goal="Research market trends and opportunities",
    instructions="Analyze market trends. Provide concise market insights."
)

competitor_researcher = Agent(
    name="CompetitorResearcher", 
    role="Competitive Intelligence Analyst",
    goal="Research competitor strategies",
    instructions="Analyze competitors. Provide key competitive insights."
)

customer_researcher = Agent(
    name="CustomerResearcher",
    role="Customer Research Analyst", 
    goal="Research customer needs and behaviors",
    instructions="Analyze customer segments. Provide customer insights."
)

# Create aggregator agent
aggregator = Agent(
    name="Aggregator",
    role="Research Synthesizer",
    goal="Synthesize research findings",
    instructions="Combine all research findings into a comprehensive summary."
)

# Create workflow with parallel execution
workflow = Workflow(
    name="Parallel Research Pipeline",
    steps=[
        parallel([market_researcher, competitor_researcher, customer_researcher]),
        aggregator
    ]
)

if __name__ == "__main__":
    print("=== Testing Agentic Parallel Workflow ===\n")
    
    # Run workflow - all researchers work in parallel, then aggregator summarizes
    result = workflow.start("Research the AI industry", verbose=True)
    
    print(f"\nFinal Summary:\n{result['output']}")

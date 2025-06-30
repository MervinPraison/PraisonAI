"""
Environment Variable Input Example for PraisonAI

This example demonstrates how to use environment variables combined with user input
to create flexible agent configurations that can be pre-configured via environment.
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents

# Set via environment or use default
default_topic = os.getenv("RESEARCH_TOPIC", "AI trends")
user_topic = input(f"Topic to research [{default_topic}]: ") or default_topic

# Get other configuration from environment
llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
max_retries = int(os.getenv("MAX_RETRIES", "3"))

# Create agent with environment-based configuration
agent = Agent(
    name="Researcher",
    role="Research Assistant",
    goal=f"Research {user_topic}",
    backstory="Expert researcher with configurable capabilities",
    llm={
        "model": llm_model,
        "temperature": temperature
    },
    max_retry_limit=max_retries
)

# Create task
task = Task(
    description=f"Research and summarize: {user_topic}",
    expected_output="Comprehensive summary with key findings",
    agent=agent
)

# Show configuration
print(f"\n🔧 Configuration:")
print(f"  - Topic: {user_topic}")
print(f"  - Model: {llm_model}")
print(f"  - Temperature: {temperature}")
print(f"  - Max Retries: {max_retries}")
print("\n" + "="*50 + "\n")

# Run agents
agents = PraisonAIAgents(agents=[agent], tasks=[task])
result = agents.start()

# Save to environment-specified location if provided
output_path = os.getenv("OUTPUT_PATH")
if output_path:
    output_file = os.path.join(output_path, f"{user_topic.replace(' ', '_')}_research.txt")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)
    print(f"\n📁 Results saved to: {output_file}")

print("\n✅ Research completed!")
"""
Basic Agent Skills Usage Example

This example demonstrates how to use Agent Skills with PraisonAI Agents.
Skills are modular capabilities that can be loaded and used by agents.
"""

from praisonaiagents import Agent, SkillManager

# Example 1: Using SkillManager directly
print("=" * 50)
print("Example 1: Using SkillManager directly")
print("=" * 50)

# Create a skill manager
manager = SkillManager()

# Discover skills from a directory
# This scans the directory for subdirectories containing SKILL.md files
skill_count = manager.discover(["./pdf-processing"], include_defaults=False)
print(f"Discovered {skill_count} skill(s)")

# List available skills
for skill in manager:
    print(f"  - {skill.properties.name}: {skill.properties.description[:50]}...")

# Generate prompt XML for system prompt injection
prompt_xml = manager.to_prompt()
print("\nGenerated prompt XML:")
print(prompt_xml)

# Example 2: Using skills with an Agent
print("\n" + "=" * 50)
print("Example 2: Using skills with an Agent")
print("=" * 50)

# Create an agent with skills
# Skills are lazy-loaded only when accessed
agent = Agent(
    name="PDF Assistant",
    instructions="You are a helpful assistant that can process PDF documents.",
    skills=["./pdf-processing"],  # Direct skill paths
)

# Access the skill manager through the agent
if agent.skill_manager:
    print(f"Agent has {len(agent.skill_manager)} skill(s) loaded")
    
    # Get the skills prompt for system prompt injection
    skills_prompt = agent.get_skills_prompt()
    print("\nAgent skills prompt:")
    print(skills_prompt)

# Example 3: Discovering skills from multiple directories
print("\n" + "=" * 50)
print("Example 3: Using skills_dirs for discovery")
print("=" * 50)

# Create an agent that discovers skills from directories
agent_with_discovery = Agent(
    name="Multi-Skill Agent",
    instructions="You are a versatile assistant with multiple skills.",
    skills_dirs=["./"],  # Scan current directory for skill subdirectories
)

if agent_with_discovery.skill_manager:
    print(f"Discovered {len(agent_with_discovery.skill_manager)} skill(s)")
    for name in agent_with_discovery.skill_manager.skill_names:
        print(f"  - {name}")

print("\n" + "=" * 50)
print("Examples complete!")
print("=" * 50)

"""
Example 4: Save Agent Output Manually

Capture the response and save it with full control.
"""

from praisonaiagents import Agent
from pathlib import Path

# Create agent
agent = Agent(
    name="StoryWriter",
    instructions="You are a creative writer who writes short stories."
)

# Get response
response = agent.start("Write a very short story about a robot learning to paint")

# Save manually with error handling
output_path = Path("stories/robot_story.txt")
output_path.parent.mkdir(parents=True, exist_ok=True)

try:
    output_path.write_text(response)
    print(f"✅ Saved to {output_path}")
except IOError as e:
    print(f"❌ Failed to save: {e}")

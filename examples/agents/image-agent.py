from praisonaiagents import Agent, Tools
from praisonaiagents.tools import duckduckgo

agent = Agent(instructions="You are a Image Analysis Agent", tools=[duckduckgo])
agent.start("I want to go London next week, find me a good hotel and flight")

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create Image Analysis Agent
image_agent = Agent(
    name="ImageAnalyst",
    role="Image Analysis Specialist",
    goal="Analyze images and videos to extract meaningful information",
    backstory="""You are an expert in computer vision and image analysis.
    You excel at describing images, detecting objects, and understanding visual content.""",
    llm="gpt-4o-mini",
    self_reflect=False
)

# 1. Task with Image URL
task1 = Task(
    name="analyze_landmark",
    description="Describe this famous landmark and its architectural features.",
    expected_output="Detailed description of the landmark's architecture and significance",
    agent=image_agent,
    images=["https://upload.wikimedia.org/wikipedia/commons/b/bf/Krakow_-_Kosciol_Mariacki.jpg"]
)

# 2. Task with Local Image File
task2 = Task(
    name="analyze_local_image",
    description="What objects can you see in this image? Describe their arrangement.",
    expected_output="Detailed description of objects and their spatial relationships",
    agent=image_agent,
    images=["image.jpg"] 
)

# Create PraisonAIAgents instance
agents = PraisonAIAgents(
    agents=[image_agent],
    tasks=[task1, task2],
    process="sequential",
    verbose=1
)

# Run all tasks
agents.start()
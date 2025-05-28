from praisonaiagents import Agent, Task, PraisonAIAgents

# Create Video Analysis Agent
video_agent = Agent(
    name="VideoAnalyst",
    role="Video Analysis Specialist",
    goal="Analyze images and videos to extract meaningful information",
    backstory="""You are an expert in computer vision and image analysis.
    You excel at describing images, detecting objects, and understanding visual content.""",
    llm="gpt-4o-mini",
    self_reflect=False
)

# Task with Video File
task1 = Task(
    name="analyze_video",
    description="""Watch this video and provide:
    1. A summary of the main events
    2. Key objects and people visible
    3. Any text or important information shown
    4. The overall context and setting""",
    expected_output="Comprehensive analysis of the video content",
    agent=video_agent,
    images=["video.mp4"]  
)

# Create PraisonAIAgents instance
agents = PraisonAIAgents(
    agents=[video_agent],
    tasks=[task1],
    process="sequential",
    verbose=1
)

# Run all tasks
agents.start()
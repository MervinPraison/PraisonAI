"""
Example 2: Save Agent Output Using Task.output_file

Task output is automatically saved to the specified file.
"""

from praisonaiagents import Agent, Task, Agents

# Create agent
writer = Agent(
    name="ContentWriter",
    role="Writer",
    goal="Create engaging content"
)

# Task with output_file - auto-saves result
task = Task(
    description="Write a short blog post about the benefits of AI assistants",
    expected_output="A well-structured blog post in markdown format",
    agent=writer,
    output_file="blog_post.md",
    create_directory=True
)

# Run
agents = AgentManager(agents=[writer], tasks=[task])
result = agents.start()

print("✅ Task completed!")
print("Output saved to: blog_post.md")

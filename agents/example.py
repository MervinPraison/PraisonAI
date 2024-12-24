import os
import logging
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from praisonaiagents import Agent, Task, Agents, error_logs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
    datefmt="[%X]"
)

def my_callback(output):
    logging.info(f"Callback function called after task execution: {output.description}")
    logging.info(f"Task output: {output}")

def main():
    # Make sure OPENAI_API_KEY is set
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Please set OPENAI_API_KEY environment variable")

    # Define tools
    search_tool = {
        "type": "function",
        "function": {
            "name": "search_tool",
            "description": "Use this to perform search queries",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    }
    get_weather_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                },
                "required": ["location"],
            },
        },
    }

    # Create agents
    researcher = Agent(
        name="Researcher",
        role="Senior Research Analyst",
        goal="Uncover cutting-edge developments in AI and data science",
        backstory="""You are an expert at a technology research group, 
        skilled in identifying trends and analyzing complex data.""",
        verbose=True,
        allow_delegation=False,
        tools=[search_tool],
        llm="gpt-4o",
        markdown=True
    )
    writer = Agent(
        name="Writer",
        role="Tech Content Strategist",
        goal="Craft compelling content on tech advancements",
        backstory="""You are a content strategist known for 
        making complex tech topics interesting and easy to understand.""",
        verbose=True,
        allow_delegation=True,
        llm="gpt-4o",
        tools=[get_weather_tool],
        markdown=True
    )

    # Create tasks
    task1 = Task(
        name="research_task",
        description="""Analyze 2024's AI advancements. 
        Find major trends, new technologies, and their effects.""",
        expected_output="""A detailed report on 2024 AI advancements""",
        agent=researcher,
        tools=[search_tool]
    )

    task2 = Task(
        name="writing_task",
        description="""Create a blog post about major AI advancements using the insights you have.
        Make it interesting, clear, and suited for tech enthusiasts. 
        It should be at least 4 paragraphs long. 
        Also, call the get_weather tool to get the weather in Paris.""",
        expected_output="A blog post of at least 4 paragraphs, and weather in Paris",
        agent=writer,
        context=[task1],
        callback=my_callback,
        tools=[get_weather_tool]
    )

    task3 = Task(
        name="json_task",
        description="""Create a json object with a title of "My Task" and content of "My content".""",
        expected_output="""JSON output with title and content""",
        agent=researcher,
    )

    task4 = Task(
        name="save_output_task",
        description="""Save the AI blog post to a file""",
        expected_output="""File saved successfully""",
        agent=writer,
        context=[task2],
        output_file='outputs/ai_blog_post.txt',
        create_directory=True
    )

    # Create and run agents manager
    agents = Agents(
        agents=[researcher, writer],
        tasks=[task1, task2, task3, task4],
        verbose=False,
        process="sequential",  # "sequential" or "hierarchical"
        manager_llm="gpt-4o"
    )

    result = agents.start()

    # Print results and error summary
    console = Console()
    
    # Print task results
    console.print("\n=== Task Results ===")
    for task_id, task_status in result['task_status'].items():
        console.print(f"Task {task_id}: {task_status}")
        if task_result := result['task_results'].get(task_id):
            console.print(f"Output: {task_result.raw[:200]}...")  # Show first 200 chars

    # Print task details
    console.print("\n=== Task Details ===")
    for i in range(4):
        console.print(agents.get_task_details(i))

    # Print agent details
    console.print("\n=== Agent Details ===")
    console.print(agents.get_agent_details('Researcher'))
    console.print(agents.get_agent_details('Writer'))

    # Print any errors
    if error_logs:
        console.print(Panel.fit(Text("Errors Encountered:", style="bold red"), title="Error Summary", border_style="red"))
        for err in error_logs:
            console.print(f"- {err}")
            if "parsing self-reflection json" in err:
                console.print("  Reason: The self-reflection JSON response was not valid JSON.")
            elif "Error: Task with ID" in err:
                console.print("  Reason: Task ID referenced does not exist.")
            elif "saving task output to file" in err:
                console.print("  Reason: Possible file permissions or invalid path.")
            else:
                console.print("  Reason not identified")

if __name__ == "__main__":
    main() 
from praisonaiagents import Agent, Task, PraisonAIAgents, error_logs
from duckduckgo_search import DDGS

def my_callback(output):
    print(f"Callback Task output: {output}")

def internet_search_tool(query) -> list:
    """
    Perform a search using DuckDuckGo.

    Args:
        query (str): The search query.

    Returns:
        list: A list of search result titles and URLs.
    """
    try:
        results = []
        ddgs = DDGS()
        for result in ddgs.text(keywords=query, max_results=10):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "snippet": result.get("body", "")
            })
        return results

    except Exception as e:
        print(f"Error during DuckDuckGo search: {e}")
        return []

# Create agents
researcher = Agent(
    name="Researcher",
    role="Senior Research Analyst",
    goal="Uncover cutting-edge developments in AI and data science",
    backstory="""You are an expert at a technology research group, 
    skilled in identifying trends and analyzing complex data.""",
    verbose=True,
    allow_delegation=False,
    tools=[internet_search_tool],
    llm="gpt-4o",
    markdown=True,
    reflect_llm="gpt-4o",
    min_reflect=2,
    max_reflect=4
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
    tools=[],
    markdown=True
)

# Create tasks
task1 = Task(
    name="research_task",
    description="""Analyze 2024's AI advancements. 
    Find major trends, new technologies, and their effects.""",
    expected_output="""A detailed report on 2024 AI advancements""",
    agent=researcher,
    tools=[internet_search_tool]
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
    tools=[]
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
agents = PraisonAIAgents(
    agents=[researcher, writer],
    tasks=[task1, task2, task3, task4],
    verbose=False,
    process="sequential",  # "sequential" or "hierarchical"
    manager_llm="gpt-4o"
)

result = agents.start()

# Print results and error summary
print("\n=== Task Results ===")
for task_id, task_status in result['task_status'].items():
    print(f"Task {task_id}: {task_status}")
    if task_result := result['task_results'].get(task_id):
        print(f"Output: {task_result.raw[:200]}...")  # Show first 200 chars

# Print task details
print("\n=== Task Details ===")
for i in range(4):
    print(agents.get_task_details(i))

# Print agent details
print("\n=== Agent Details ===")
print(agents.get_agent_details('Researcher'))
print(agents.get_agent_details('Writer'))

# Print any errors
if error_logs:
    print("\n=== Error Summary ===")
    for err in error_logs:
        print(f"- {err}")
        if "parsing self-reflection json" in err:
            print("  Reason: The self-reflection JSON response was not valid JSON.")
        elif "Error: Task with ID" in err:
            print("  Reason: Task ID referenced does not exist.")
        elif "saving task output to file" in err:
            print("  Reason: Possible file permissions or invalid path.")
        else:
            print("  Reason not identified")
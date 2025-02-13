from praisonaiagents import (
    Agent, 
    Task, 
    PraisonAIAgents, 
    error_logs, 
    register_display_callback,
    sync_display_callbacks,
    async_display_callbacks
)
from duckduckgo_search import DDGS
from rich.console import Console
import json
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    filename='ai_interactions.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Callback functions for different display types
def interaction_callback(message=None, response=None, markdown=None, generation_time=None):
    """Callback for display_interaction"""
    logging.info(f"""
    === INTERACTION ===
    Time: {datetime.now()}
    Generation Time: {generation_time}s
    Message: {message}
    Response: {response}
    Markdown: {markdown}
    """)

def error_callback(message=None):
    """Callback for display_error"""
    logging.error(f"""
    === ERROR ===
    Time: {datetime.now()}
    Message: {message}
    """)

def tool_call_callback(message=None):
    """Callback for display_tool_call"""
    logging.info(f"""
    === TOOL CALL ===
    Time: {datetime.now()}
    Message: {message}
    """)

def instruction_callback(message=None):
    """Callback for display_instruction"""
    logging.info(f"""
    === INSTRUCTION ===
    Time: {datetime.now()}
    Message: {message}
    """)

def self_reflection_callback(message=None):
    """Callback for display_self_reflection"""
    logging.info(f"""
    === SELF REFLECTION ===
    Time: {datetime.now()}
    Message: {message}
    """)

def generating_callback(content=None, elapsed_time=None):
    """Callback for display_generating"""
    logging.info(f"""
    === GENERATING ===
    Time: {datetime.now()}
    Content: {content}
    Elapsed Time: {elapsed_time}
    """)

# Register all callbacks
register_display_callback('interaction', interaction_callback)
register_display_callback('error', error_callback)
register_display_callback('tool_call', tool_call_callback)
register_display_callback('instruction', instruction_callback)
register_display_callback('self_reflection', self_reflection_callback)
# register_display_callback('generating', generating_callback)

def task_callback(output):
    """Callback for task completion"""
    logging.info(f"""
    === TASK COMPLETED ===
    Time: {datetime.now()}
    Description: {output.description}
    Agent: {output.agent}
    Output: {output.raw[:200]}...
    """)

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

def main():
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

    # Create tasks with callbacks
    task1 = Task(
        name="research_task",
        description="""Analyze 2024's AI advancements. 
        Find major trends, new technologies, and their effects.""",
        expected_output="""A detailed report on 2024 AI advancements""",
        agent=researcher,
        tools=[internet_search_tool],
        callback=task_callback
    )

    task2 = Task(
        name="writing_task",
        description="""Create a blog post about major AI advancements using the insights you have.
        Make it interesting, clear, and suited for tech enthusiasts. 
        It should be at least 4 paragraphs long.""",
        expected_output="A blog post of at least 4 paragraphs",
        agent=writer,
        context=[task1],
        callback=task_callback,
        tools=[]
    )

    task3 = Task(
        name="json_task",
        description="""Create a json object with a title of "My Task" and content of "My content".""",
        expected_output="""JSON output with title and content""",
        agent=researcher,
        callback=task_callback
    )

    task4 = Task(
        name="save_output_task",
        description="""Save the AI blog post to a file""",
        expected_output="""File saved successfully""",
        agent=writer,
        context=[task2],
        output_file='test.txt',
        create_directory=True,
        callback=task_callback
    )

    # Create and run agents manager
    agents = PraisonAIAgents(
        agents=[researcher, writer],
        tasks=[task1, task2, task3, task4],
        verbose=True,
        process="sequential",
        manager_llm="gpt-4o"
    )

    agents.start()

if __name__ == "__main__":
    main()

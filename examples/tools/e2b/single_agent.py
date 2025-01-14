from praisonaiagents import Agent, Task, PraisonAIAgents, error_logs
import json, os
from e2b_code_interpreter import Sandbox
import subprocess

def code_interpret(code: str):
    """
    A function to demonstrate running Python code dynamically using e2b_code_interpreter.
    """
    print(f"\n{'='*50}\n> Running following AI-generated code:\n{code}\n{'='*50}")
    exec_result = Sandbox().run_code(code)
    if exec_result.error:
        print("[Code Interpreter error]", exec_result.error)
        return {"error": str(exec_result.error)}
    else:
        results = []
        for result in exec_result.results:
            if hasattr(result, '__iter__'):
                results.extend(list(result))
            else:
                results.append(str(result))
        logs = {"stdout": list(exec_result.logs.stdout), "stderr": list(exec_result.logs.stderr)}
        return json.dumps({"results": results, "logs": logs})

def save_to_file(file_path: str, content: str):
    """
    Save the given content to the specified file path. Create the folder/file if it doesn't exist.
    """
    # Ensure the directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Write the content to the file
    with open(file_path, 'w') as file:
        file.write(content)

    return file_path

def run_terminal_command(command: str):
    """
    Run a terminal command and return its output.
    """
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"Command output: {result}")
        return {"stdout": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as e:
        return {"error": str(e), "stdout": e.stdout, "stderr": e.stderr}


# 1) Create Agents
web_scraper_agent = Agent(
    name="WebScraper",
    role="Web Scraper",
    goal="Extract URLs from https://news.ycombinator.com/",
    backstory="An expert in data extraction from websites, adept at navigating and retrieving detailed information and saving it to a file. and just check if the file is created using run_terminal_command tool",
    min_reflect=3,
    max_reflect=5,
    tools=[code_interpret, save_to_file, run_terminal_command],
    llm="gpt-4o"
)

task = Task(
    name="url_extraction_task",
    description="""Use code_interpret to run Python code that fetches https://news.ycombinator.com/
    and extracts first 20 URLs from the page, with full path, then outputs them in a txt file.""",
    expected_output="A list of URLs extracted from the source page in a txt file.",
    agent=web_scraper_agent,
)

agents = PraisonAIAgents(
    agents=[web_scraper_agent],
    tasks=[task],
    process="sequential"
)

result = agents.start()

print(result)   
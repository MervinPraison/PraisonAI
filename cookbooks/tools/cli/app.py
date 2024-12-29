from praisonaiagents import Agent, Task, PraisonAIAgents
import subprocess
import os

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

# Create System Operations Agent
system_ops_agent = Agent(
    name="SystemOps",
    role="System Operations Specialist",
    goal="Execute and manage complex system operations and commands",
    backstory="""You are an expert system administrator with deep knowledge of Unix/Linux systems.
    You excel at running complex system commands, managing processes, and handling system operations.
    You always validate commands before execution and ensure they are safe to run.""",
    min_reflect=6,
    max_reflect=10,
    tools=[run_terminal_command, save_to_file],
    llm="gpt-4o-mini"
)

# Create a complex task that tests various system operations
task = Task(
    name="system_analysis_task",
    description="""Perform a comprehensive system analysis by executing the following operations in sequence:
    1. Get system information (OS, kernel version)
    2. List 5 running processes and sort them by CPU usage
    3. Check disk space usage and list directories over 1GB
    4. Display current system load and memory usage
    5. List 5 network connections
    6. Create a summary report with all findings in a text file called system_report.txt
    
    Do it step by step. One task at a time. 
    Save only the Summary report in the file.
    Use appropriate commands for each step and ensure proper error handling.""",
    expected_output="A comprehensive system report containing all requested information saved in system_report.txt",
    agent=system_ops_agent,
)

agents = PraisonAIAgents(
    agents=[system_ops_agent],
    tasks=[task],
    process="sequential"
)

result = agents.start()
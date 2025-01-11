from praisonaiagents import Agent, Task, PraisonAIAgents
import json
from e2b_code_interpreter import Sandbox

def code_interpreter(code: str):
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

code_agent = Agent(
    name="code_agent",
    llm="gpt-4o-mini",
    backstory="Expert in writing Python scripts",
    self_reflect=False
)
execution_agent = Agent(
    name="execution_agent",
    llm="gpt-4o-mini",
    backstory="Expert in executing Python scripts",
    self_reflect=False,
    tools=[code_interpreter]
)

code_agent_task = Task(
    description="Write a simple Python script to print 'Hello, World!'",
    expected_output="A Python script that prints 'Hello, World!'",
    agent=code_agent
)
execution_agent_task = Task(
    description="Execute the Python script",
    expected_output="The output of the Python script",
    agent=execution_agent
)

agents = PraisonAIAgents(agents=[code_agent, execution_agent], tasks=[code_agent_task, execution_agent_task])
agents.start()
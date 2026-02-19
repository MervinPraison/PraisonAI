from praisonaiagents import Agent
from praisonaiagents.tools.shell_tools import execute_command
from praisonai.bots import HTTPApproval

agent = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=[execute_command],
    approval=HTTPApproval(host="127.0.0.1", port=8899),
)
# When approval is needed, open http://127.0.0.1:8899/approve/<request_id> in your browser
agent.start("Use the execute_command tool to run: cmd /c echo Approval test")

from praisonaiagents import Agent
from praisonaiagents.tools.shell_tools import execute_command
from praisonai.bots import TelegramApproval  

agent = Agent(
    name="assistant",
    instructions="Help users with system tasks",
    tools=[execute_command],
    approval=TelegramApproval(),
)
agent.start("Use the execute_command tool to run: cmd /c echo Approval test")

# ---
# title: "Azure Container Apps dynamic sessions Code runtime Tool"
# description: "Guide for using the Azure Container Apps dynamic sessions based code Interpreter tool with PraisonAI agents."
# icon: "code"
# ---

# ## Overview

# The Azure Container Apps dynamic sessions based code Interpreter tool is a tool that allows you to execute and run development environments using the AI Agents.

# ```bash
# pip install langchain-azure-dynamic-sessions langchain-openai langchainhub langchain langchain-community
# ```

# ```python
# from praisonaiagents import Agent, PraisonAIAgents
# from langchain_community.tools import BearlyInterpreterTool

# coder_agent = Agent(instructions="""for i in range(0,10):
#                                         print(f'The number is {i}')""", tools=[BearlyInterpreterTool])

# agents = PraisonAIAgents(agents=[coder_agent])
# agents.start()
# ```

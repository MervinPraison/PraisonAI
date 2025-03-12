from praisonaiagents import Agent, PraisonAIAgents
from langchain_community.tools import JinaSearch

import os 

os.environ["JINA_API_KEY"]=""


def invoke_jina_search(query: str):
    JinaSearchTool = JinaSearch()
    model_generated_tool_call = {
        "args": {"query": query},
        "id": "1",
        "name": JinaSearchTool.name,
        "type": "tool_call",
    }
    tool_msg = JinaSearchTool.invoke(model_generated_tool_call)
    return(tool_msg.content[:1000])

data_agent = Agent(instructions="Find 10 websites where I can learn coding for free", tools=[invoke_jina_search])
editor_agent = Agent(instructions="write a listicle blog ranking the best websites. The blog should contain a proper intro and conclusion")
agents = PraisonAIAgents(agents=[data_agent, editor_agent], process='hierarchical')
agents.start()


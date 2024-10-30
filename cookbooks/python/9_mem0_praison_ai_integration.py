# tools.py
from mem0 import Memory
from praisonai_tools import BaseTool

class AddMemoryTool(BaseTool):
    name: str = "Add Memory Tool"
    description: str = ("This tool allows storing a new memory with user ID and optional metadata.\n"
                        "Example:\n"
                        "   - Input: text='I am working on improving my tennis skills. Suggest some online courses.', user_id='alice', metadata={'category': 'hobbies'}\n"
                        "   - Output: Memory added with summary 'Improving her tennis skills. Looking for online suggestions.'")

    def _run(self, text: str, user_id: str, metadata: dict = None):
        m = Memory()
        result = m.add(text, user_id=user_id, metadata=metadata)
        return result

class GetAllMemoriesTool(BaseTool):
    name: str = "Get All Memories Tool"
    description: str = ("This tool retrieves all stored memories.\n"
                        "Example:\n"
                        "   - Input: action='get_all'\n"
                        "   - Output: List of all stored memories.")

    def _run(self):
        m = Memory()
        result = m.get_all()
        return result

class SearchMemoryTool(BaseTool):
    name: str = "Search Memory Tool"
    description: str = ("This tool searches for specific memories based on a query and user ID.\n"
                        "Example:\n"
                        "   - Input: query='What are Alice's hobbies?', user_id='alice'\n"
                        "   - Output: Search results related to Alice's hobbies.")

    def _run(self, query: str, user_id: str):
        m = Memory()
        result = m.search(query=query, user_id=user_id)
        return result

class UpdateMemoryTool(BaseTool):
    name: str = "Update Memory Tool"
    description: str = ("This tool updates an existing memory by memory ID and new data.\n"
                        "Example:\n"
                        "   - Input: memory_id='cb032b42-0703-4b9c-954d-77c36abdd660', data='Likes to play tennis on weekends'\n"
                        "   - Output: Memory updated to 'Likes to play tennis on weekends.'")

    def _run(self, memory_id: str, data: str):
        m = Memory()
        result = m.update(memory_id=memory_id, data=data)
        return result

class MemoryHistoryTool(BaseTool):
    name: str = "Memory History Tool"
    description: str = ("This tool gets the history of changes made to a specific memory by memory ID.\n"
                        "Example:\n"
                        "   - Input: memory_id='cb032b42-0703-4b9c-954d-77c36abdd660'\n"
                        "   - Output: History of the specified memory.")

    def _run(self, memory_id: str):
        m = Memory()
        result = m.history(memory_id=memory_id)
        return result


from duckduckgo_search import DDGS
from praisonai_tools import BaseTool

class InternetSearchTool(BaseTool):
    name: str = "InternetSearchTool"
    description: str = "Search Internet for relevant information based on a query or latest news"

    def _run(self, query: str):
        ddgs = DDGS()
        results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
        return results
    


# Example agent_yaml content

import os
import yaml
from praisonai import PraisonAI

agent_yaml = """
framework: "crewai"
topic: "personal memory management"
roles:
  data_analyst:
    role: "Data Analyst"
    backstory: "Skilled in analyzing data to find trends and insights."
    goal: "Analyze the data to provide useful insights and recommendations."
    tasks:
      research_ai_news:
        description: "Analyze the latest AI news from July 2024 and trends to provide insights and recommendations."
        expected_output: "Report with insights on the latest AI trends and personalized recommendations."
    tools:
      - "InternetSearchTool"
  user_support:
    role: "User Support"
    backstory: "Expert in assisting users with queries and issues related to memory management."
    goal: "Provide support to users for adding information to memories."
    tasks:
      support_users:
        description: "Assist users in adding information to memories."
        expected_output: "User queries resolved and memories managed effectively."
    tools:
      - "AddMemoryTool"
      - "GetAllMemoriesTool"
      - "SearchMemoryTool"

"""

# Create a PraisonAI instance with the agent_yaml content
praisonai = PraisonAI(agent_yaml=agent_yaml)

# Add OPENAI_API_KEY Secrets to Google Colab on the Left Hand Side 🔑 or Enter Manually Below
# os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY') or "ENTER OPENAI_API_KEY HERE"
openai_api_key = os.getenv("OPENAI_API_KEY")

# Run PraisonAI
result = praisonai.run()

# Print the result
print(result)
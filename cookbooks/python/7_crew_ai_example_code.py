# tools.py
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

agent_yaml = """framework: "crewai"
topic: "AI Advancements in 2024"
roles:
  researcher:
    role: "Senior Research Analyst"
    backstory: |
      You are an expert at a technology research group, skilled in identifying trends and analyzing complex data.
    goal: "Uncover cutting-edge developments in AI and data science"
    verbose: true
    allow_delegation: false
    tools:
      - "search_tool"
    tasks:
      task1:
        description: |
          Analyze 2024's AI advancements. Find major trends, new technologies, and their effects. Provide a detailed report.
        expected_output: "A detailed report on major AI trends, new technologies, and their effects in 2024."
  writer:
    role: "Tech Content Strategist"
    backstory: |
      You are a content strategist known for making complex tech topics interesting and easy to understand.
    goal: "Craft compelling content on tech advancements"
    verbose: true
    allow_delegation: true
    tasks:
      task2:
        description: |
          Create a blog post about major AI advancements using your insights. Make it interesting, clear, and suited for tech enthusiasts. It should be at least 4 paragraphs long.
        expected_output: "An engaging blog post of at least 4 paragraphs about major AI advancements, suitable for tech enthusiasts."
dependencies:
  - task: "task2"
    depends_on:
      - "task1"
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
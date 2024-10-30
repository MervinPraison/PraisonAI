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

agent_yaml = """
framework: "crewai"
topic: "AI in healthcare"

roles:
  manager:
    role: "Project Manager"
    backstory: |
      With a strategic mindset and a knack for leadership, you excel at guiding teams towards
      their goals, ensuring projects not only meet but exceed expectations.
    goal: "Coordinate the project to ensure a seamless integration of research findings into compelling narratives"
    verbose: true
    allow_delegation: true
    max_iter: 10
    max_rpm: 20
    tasks:
      manager_task:
        description: |
          Oversee the integration of research findings and narrative development to produce a final comprehensive
          report on AI in healthcare. Ensure the research is accurately represented and the narrative is engaging and informative.
        expected_output: "A final comprehensive report that combines the research findings and narrative on AI in healthcare."

  researcher:
    role: "Senior Researcher"
    backstory: |
      Driven by curiosity, you're at the forefront of innovation, eager to explore and share
      knowledge that could change the world.
    goal: "Uncover groundbreaking technologies around AI in healthcare"
    verbose: true
    tools:
      - "search_tool"
      - "ContentTools.read_content"
    tasks:
      list_ideas:
        description: "List of 5 interesting ideas to explore for an article about AI in healthcare."
        expected_output: "Bullet point list of 5 ideas for an article."
        async_execution: true
      list_important_history:
        description: "Research the history of AI in healthcare and identify the 5 most important events."
        expected_output: "Bullet point list of 5 important events."
        async_execution: true

  writer:
    role: "Writer"
    backstory: |
      With a flair for simplifying complex topics, you craft engaging narratives that captivate
      and educate, bringing new discoveries to light in an accessible manner.
    goal: "Narrate compelling tech stories around AI in healthcare"
    verbose: true
    tools:
      - "search_tool"
      - "ContentTools.read_content"
    tasks:
      write_article:
        description: |
          Compose an insightful article on AI in healthcare, including its history and the latest interesting ideas.
        expected_output: "A 4-paragraph article about AI in healthcare."
        context:
          - "list_ideas"
          - "list_important_history"
        callback: "callback_function"

dependencies:
  - task: "write_article"
    depends_on:
      - "list_ideas"
      - "list_important_history"

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
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
              topic: "News Analysis"

              roles:
                news_search_agent:
                  role: "News Searcher"
                  backstory: "Expert in analyzing and generating key points from news content for quick updates."
                  goal: "Generate key points for each news article from the latest news."
                  tools:
                    - "SearchNewsDB.news"
                  allow_delegation: true
                  tasks:
                    news_search_task:
                      description: "Search for 'AI 2024' and create key points for each news."
                      expected_output: "Key points for each news article related to 'AI 2024'."
                writer_agent:
                  role: "Writer"
                  backstory: "Expert in crafting engaging narratives from complex information."
                  goal: "Identify all the topics received. Use the Get News Tool to verify each topic to search. Use the Search tool for detailed exploration of each topic. Summarize the retrieved information in depth for every topic."
                  tools:
                    - "GetNews.news"
                    - "DuckDuckGoSearchRun"
                  allow_delegation: true
                  tasks:
                    writer_task:
                      description: |
                        Go step by step.
                        Step 1: Identify all the topics received.
                        Step 2: Use the Get News Tool to verify each topic by going through one by one.
                        Step 3: Use the Search tool to search for information on each topic one by one.
                        Step 4: Go through every topic and write an in-depth summary of the information retrieved.
                        Don't skip any topic.
                      expected_output: "An in-depth summary of the information retrieved for each topic."

              dependencies:
                - task: "writer_task"
                  depends_on:
                    - "news_search_task"

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
# tools.py
from langchain_community.utilities import WikipediaAPIWrapper
from praisonai_tools import BaseTool

class WikipediaSearchTool(BaseTool):
    name: str = "WikipediaSearchTool"
    description: str = "Search Wikipedia for relevant information based on a query."

    def _run(self, query: str):
        api_wrapper = WikipediaAPIWrapper(top_k_results=4, doc_content_chars_max=100)
        results = api_wrapper.load(query=query)
        return results

# Example agent_yaml content

import os
import yaml
from praisonai import PraisonAI

agent_yaml = """
framework: "crewai"
topic: "research about Nvidia growth"
roles:
  data_collector:
    role: "Data Collector"
    backstory: "An experienced researcher with the ability to efficiently collect and organize vast amounts of data."
    goal: "Gather information on Nvidia's growth by providing the Ticket Symbol to YahooFinanceNewsTool"
    tasks:
      data_collection_task:
        description: "Collect data on Nvidia's growth from various sources such as financial reports, news articles, and company announcements."
        expected_output: "A comprehensive document detailing data points on Nvidia's growth over the years."
    tools:
      - "WikipediaSearchTool"
  data_analyst:
    role: "Data Analyst"
    backstory: "Specializes in extracting insights from large datasets, proficient in quantitative and qualitative analysis."
    goal: "Analyze the collected data to identify trends and patterns"
    tasks:
      data_analysis_task:
        description: "Analyze the collected data to identify key trends and patterns in Nvidia's growth."
        expected_output: "An analytical report summarizing trends, patterns, and key growth metrics of Nvidia."
    tools: []
  report_preparer:
    role: "Report Preparer"
    backstory: "Experienced in creating detailed reports and presentations, turning analytical data into actionable insights."
    goal: "Generate a final report on Nvidia's growth"
    tasks:
      report_preparation_task:
        description: "Create a detailed report based on the analysis, highlighting Nvidia's growth trajectory."
        expected_output: "A polished, comprehensive report summarizing Nvidia's growth with visual aids and key insights."
    tools: []
dependencies: []

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
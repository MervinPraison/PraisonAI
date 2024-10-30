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

# Example agents_yaml content

import os
import yaml
from praisonai import PraisonAI

agents_yaml = """framework: "crewai"
topic: "Product Development"
roles:
  market_research_analyst:
    role: "Market Research Analyst"
    backstory: "Expert at understanding market demand, target audience, and competition for products like the product. Skilled in developing marketing strategies to reach a wide audience."
    goal: "Analyze the market demand for the product and suggest marketing strategies using InternetSearchTool."
    tasks:
      market_analysis_task:
        description: "Analyze the market demand for the product. Current month is Jan 2024. Write a report on the ideal customer profile and marketing strategies to reach the widest possible audience. Include at least 10 bullet points addressing key marketing areas. Search the internet using InternetSearchTool."
        expected_output: "Report on the ideal customer profile and marketing strategies, with at least 10 bullet points addressing key marketing areas."
    tools:
      - InternetSearchTool
  technology_expert:
    role: "Technology Expert"
    backstory: "Visionary in current and emerging technological trends, especially in products like the product. Identifies which technologies are best suited for different business models."
    goal: "Assess technological feasibilities and requirements for producing high-quality the product"
    tasks:
      technology_assessment_task:
        description: "Assess the technological aspects of manufacturing high-quality the product. Write a report detailing necessary technologies and manufacturing approaches. Include at least 10 bullet points on key technological areas."
        expected_output: "Report detailing necessary technologies and manufacturing approaches, including at least 10 bullet points on key technological areas."
  business_consultant:
    role: "Business Development Consultant"
    backstory: "Seasoned in shaping business strategies for products like the product. Understands scalability and potential revenue streams to ensure long-term sustainability."
    goal: "Evaluate the business model for the product, focusing on scalability and revenue streams"
    tasks:
      business_model_evaluation_task:
        description: "Summarize the market and technological reports and evaluate the business model for the product. Write a report on the scalability and revenue streams for the product. Include at least 10 bullet points on key business areas. Give Business Plan, Goals, and Timeline for the product launch. Current month is Jan 2024."
        expected_output: "Comprehensive business model evaluation report including scalability, revenue streams, at least 10 key business areas, Business Plan, Goals, and Timeline for the product launch."
      """


# Create a PraisonAI instance with the agent_yaml content and tools
praisonai = PraisonAI(
    agent_yaml=agents_yaml,
    tools=[InternetSearchTool]  # Just pass the class directly in a list
)

# Add OPENAI_API_KEY Secrets to Google Colab on the Left Hand Side 🔑 or Enter Manually Below
# os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY') or "ENTER OPENAI_API_KEY HERE"
openai_api_key = os.getenv("OPENAI_API_KEY")

# Run PraisonAI
result = praisonai.run()

# Print the result
print(result)
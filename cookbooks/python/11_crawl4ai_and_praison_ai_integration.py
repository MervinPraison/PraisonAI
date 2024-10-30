# tools.py
import os
from crawl4ai import WebCrawler
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from pydantic import BaseModel, Field
from praisonai_tools import BaseTool

class ModelFee(BaseModel):
    llm_model_name: str = Field(..., description="Name of the model.")
    input_fee: str = Field(..., description="Fee for input token for the model.")
    output_fee: str = Field(..., description="Fee for output token for the model.")

class ModelFeeTool(BaseTool):
    name: str = "ModelFeeTool"
    description: str = "Extracts model fees for input and output tokens from the given pricing page."

    def _run(self, url: str):
        crawler = WebCrawler()
        crawler.warmup()

        result = crawler.run(
            url=url,
            word_count_threshold=1,
            extraction_strategy= LLMExtractionStrategy(
                provider="openai/gpt-4o",
                api_token=os.getenv('OPENAI_API_KEY'), 
                schema=ModelFee.schema(),
                extraction_type="schema",
                instruction="""From the crawled content, extract all mentioned model names along with their fees for input and output tokens. 
                Do not miss any models in the entire content. One extracted model JSON format should look like this: 
                {"model_name": "GPT-4", "input_fee": "US$10.00 / 1M tokens", "output_fee": "US$30.00 / 1M tokens"}."""
            ),            
            bypass_cache=True,
        )
        return result.extracted_content
    


# Example agent_yaml content

import os
import yaml
from praisonai import PraisonAI

agent_yaml = """
framework: "crewai"
topic: "extract model pricing from websites"
roles:
  web_scraper:
    role: "Web Scraper"
    backstory: |
      An expert in web scraping with a deep understanding of extracting structured
      data from online sources.

      https://openai.com/api/pricing/
      https://www.anthropic.com/pricing
      https://cohere.com/pricing
    goal: "Gather model pricing data from various websites"
    tasks:
      scrape_model_pricing:
        description: "Scrape model pricing information from the provided list of websites."
        expected_output: "Raw HTML or JSON containing model pricing data."
    tools:
      - "ModelFeeTool"
  data_cleaner:
    role: "Data Cleaner"
    backstory: "Specialist in data cleaning, ensuring that all collected data is accurate and properly formatted."
    goal: "Clean and organize the scraped pricing data"
    tasks:
      clean_pricing_data:
        description: "Process the raw scraped data to remove any duplicates and inconsistencies, and convert it into a structured format."
        expected_output: "Cleaned and organized JSON or CSV file with model pricing data."
    tools: []
  data_analyzer:
    role: "Data Analyzer"
    backstory: "Data analysis expert focused on deriving actionable insights from structured data."
    goal: "Analyze the cleaned pricing data to extract insights"
    tasks:
      analyze_pricing_data:
        description: "Analyze the cleaned data to extract trends, patterns, and insights on model pricing."
        expected_output: "Detailed report summarizing model pricing trends and insights."
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
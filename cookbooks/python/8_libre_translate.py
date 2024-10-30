# tools.py
import requests
from praisonai_tools import BaseTool

class TranslatorTool(BaseTool):
    name: str = "Translator Tool"
    description: str = "Translate text from one language to another."

    def _run(self, q: str, target: str):
        url = "http://127.0.0.1:5000/translate"
        payload = {
            "q": q,
            "source": "auto",  # Automatically detect the source language
            "target": target
        }
        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            try:
                data = response.json()
                return data
            except requests.exceptions.JSONDecodeError:
                return "Failed to decode JSON from the response."
        else:
            return f"Request failed with status code: {response.status_code}"
        

# Example agent_yaml content

import os
import yaml
from praisonai import PraisonAI

agent_yaml = """
framework: "crewai"
topic: "Writing an article about AI"
roles:
  article_writer:
    role: "Article Writer"
    backstory: "Experienced writer with a deep understanding of artificial intelligence and technology trends."
    goal: "Write an informative and engaging article about AI."
    tasks:
      write_article:
        description: "Write a comprehensive article about the latest developments and implications of AI."
        expected_output: "A well-written article on AI in English."
  french_translator:
    role: "Translator"
    backstory: "Fluent in French with expertise in translating technical and non-technical content accurately."
    goal: "Translate the AI article into French."
    tasks:
      translate_to_french:
        description: "Translate the English article on AI into French."
        expected_output: "The AI article translated into French."
    tools:
      - "TranslatorTool"
  german_translator:
    role: "Translator"
    backstory: "Proficient in German with a strong background in technical translation."
    goal: "Translate the AI article into German."
    tasks:
      translate_to_german:
        description: "Translate the English article on AI into German."
        expected_output: "The AI article translated into German."
    tools:
      - "TranslatorTool"
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
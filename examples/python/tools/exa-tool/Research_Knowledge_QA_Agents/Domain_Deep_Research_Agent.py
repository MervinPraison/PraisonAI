#!/usr/bin/env python
# coding: utf-8

"""
Domain Deep Research Agent using PraisonAIAgents

This script performs deep research on a given topic and provides a structured report.
It is CI-friendly: it uses dummy data if API keys are not set.
"""

import os
from praisonaiagents import Agent

# Set up key (robust, CI-safe)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-..")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

def is_valid_key(key, prefix):
    return key and key != f"{prefix}-.." and key.startswith(prefix)

# Custom Tool: Dummy Deep Research Tool
class DummyDeepResearchTool:
    """
    Custom tool to simulate deep research for CI/public use.
    """
    def __init__(self, topic):
        self.topic = topic

    def research(self):
        # For demo/CI, just return a dummy report
        return f"## Research Report on {self.topic}\n\n- Key finding 1 about {self.topic}\n- Key finding 2 about {self.topic}\n- Key finding 3 about {self.topic}\n"

if __name__ == "__main__":
    # User input (for demo, hardcoded; in real use, use input() or widgets)
    topic = "Recent advances in quantum computing"

    # Use the custom tool
    tool = DummyDeepResearchTool(topic)
    dummy_report = tool.research()

    if not is_valid_key(OPENAI_API_KEY, "sk"):
        print("API key not set or is a placeholder. Using dummy research report for CI/testing.")
        print(dummy_report)
    else:
        prompt = f"""
        You are a domain research assistant. Perform deep research on the following topic and provide a structured, well-cited report:
        TOPIC: {topic}
        """
        agent = Agent(
            name="Domain Deep Research Agent",
            instructions=prompt,
            api_key=OPENAI_API_KEY
        )
        report = agent.start(prompt)
        print(report)
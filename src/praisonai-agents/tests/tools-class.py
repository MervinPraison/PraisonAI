from praisonaiagents import Agent, Task, PraisonAIAgents
import os
import requests
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class EXASearchTool(BaseModel):
    """Wrapper for EXA Search API."""
    search_url: str = "https://api.exa.ai/search"
    headers: Dict = {
        "accept": "application/json",
        "content-type": "application/json",
    }
    max_results: Optional[int] = None

    def run(self, query: str) -> str:
        """Run query through EXA and return concatenated results.
        
        Args:
            query (str): The search query to use
            
        Returns:
            str: The concatenated search results
        """
        payload = {
            "query": query,
            "type": "magic",
        }

        headers = self.headers.copy()
        headers["x-api-key"] = os.environ['EXA_API_KEY']

        response = requests.post(self.search_url, json=payload, headers=headers)
        results = response.json()
        
        if 'results' in results:
            return self._parse_results(results['results'])
        return ""

    def results(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """Run query through EXA and return metadata.
        
        Args:
            query (str): The search query to use
            max_results (Optional[int]): Maximum number of results to return
            
        Returns:
            List[Dict[str, Any]]: List of result dictionaries
        """
        payload = {
            "query": query,
            "type": "magic",
        }

        headers = self.headers.copy()
        headers["x-api-key"] = os.environ['EXA_API_KEY']

        response = requests.post(self.search_url, json=payload, headers=headers)
        results = response.json()
        
        if 'results' in results:
            return results['results'][:max_results] if max_results else results['results']
        return []

    def _parse_results(self, results: List[Dict[str, Any]]) -> str:
        """Parse results into a readable string format.
        
        Args:
            results (List[Dict[str, Any]]): List of result dictionaries
            
        Returns:
            str: Formatted string of results
        """
        strings = []
        for result in results:
            try:
                strings.append('\n'.join([
                    f"Title: {result['title']}",
                    f"Score: {result['score']}",
                    f"Url: {result['url']}",
                    f"ID: {result['id']}",
                    "---"
                ]))
            except KeyError:
                continue

        content = '\n'.join(strings)
        return f"\nSearch results: {content}\n"

# Create an agent with the tool
agent = Agent(
    name="SearchAgent",
    role="Research Assistant",
    goal="Search for information about 'AI Agents Framework'",
    backstory="I am an AI assistant that can search GitHub.",
    tools=[EXASearchTool],
    self_reflect=False
)

# Create tasks to demonstrate both tools
task = Task(
    name="search_task",
    description="Search for information about 'AI Agents Framework'",
    expected_output="Information about AI Agents Framework",
    agent=agent
)

# Create and start the workflow
agents = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    verbose=True
)

agents.start()
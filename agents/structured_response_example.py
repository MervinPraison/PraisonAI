from praisonaiagents import Agent
from pydantic import BaseModel
from typing import List, Optional

# Define structured output models
class SearchResult(BaseModel):
    title: str
    url: Optional[str]
    snippet: str

class AnalysisReport(BaseModel):
    topic: str
    key_findings: List[str]
    search_results: List[SearchResult]
    summary: str
    confidence_score: float

def get_structured_analysis(query: str, verbose: bool = True) -> AnalysisReport:
    """
    Performs a search and returns a structured analysis using an AI agent.
    
    Args:
        query (str): The search query or topic to analyze
        verbose (bool): Whether to show detailed output
        
    Returns:
        AnalysisReport: A structured report containing the analysis
    """
    # Create an agent with search capabilities
    agent = Agent(
        name="StructuredAnalyst",
        role="Research Analyst",
        goal="Analyze topics and provide structured reports",
        backstory="Expert at gathering information and providing structured analysis",
        verbose=verbose,
        self_reflect=True,  # Enable self-reflection for better quality
        markdown=True,
        llm="gpt-4o-mini"
    )
    
    # Create the analysis prompt
    prompt = f"""
Analyze the following topic: "{query}"

Provide a structured analysis in JSON format that matches this schema:
{{
    "topic": "string",
    "key_findings": ["string"],
    "search_results": [
        {{
            "title": "string",
            "url": "string",
            "snippet": "string"
        }}
    ],
    "summary": "string",
    "confidence_score": float (0-1)
}}

Requirements:
1. Include at least 3 key findings
2. Include at least 2 relevant search results
3. Provide a comprehensive summary
4. Set confidence score based on quality of sources (0-1)

Return ONLY the JSON object, no other text.
"""
    
    # Get structured response from agent
    response = agent.chat(
        prompt=prompt,
        output_json=AnalysisReport  # This ensures response matches our model
    )
    
    return AnalysisReport.model_validate_json(response)

if __name__ == "__main__":
    # Example usage
    analysis = get_structured_analysis("Latest developments in AI agents and autonomous systems")
    print(analysis)
    # Print the structured results
    print("\n=== Structured Analysis Report ===")
    print(f"Topic: {analysis.topic}")
    print("\nKey Findings:")
    for i, finding in enumerate(analysis.key_findings, 1):
        print(f"{i}. {finding}")
    
    print("\nSearch Results:")
    for result in analysis.search_results:
        print(f"\nTitle: {result.title}")
        print(f"URL: {result.url}")
        print(f"Snippet: {result.snippet}")
    
    print(f"\nSummary: {analysis.summary}")
    print(f"Confidence Score: {analysis.confidence_score:.2f}") 
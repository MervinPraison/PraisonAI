from praisonaiagents import Agent, Task, PraisonAIAgents
from pydantic import BaseModel
from typing import List, Dict
from gitingest import ingest

class CodeMetrics(BaseModel):
    category: str
    score: int
    findings: List[str]

class CodeAnalysisReport(BaseModel):
    overall_quality: int
    code_metrics: List[CodeMetrics]
    architecture_score: int
    maintainability_score: int
    performance_score: int
    security_score: int
    test_coverage: int
    key_strengths: List[str]
    improvement_areas: List[str]
    tech_stack: List[str]
    recommendations: List[str]
    complexity_metrics: Dict[str, int]
    best_practices: List[Dict[str, str]]
    potential_risks: List[str]
    documentation_quality: int

code_analyzer = Agent(
    role="Code Analysis Expert",
    goal="Provide comprehensive code evaluation and recommendations",
    backstory="""Expert code analyst specializing in architecture review, 
    best practices, and technical debt assessment.""",
    verbose=True
)

code_analysis_task = Task(
    description="""Analyze code repository and provide structured evaluation:
    
    1. Overall Quality (0-100)
    2. Core Metrics Analysis:
       - Architecture and Design
       - Code Maintainability
       - Performance Optimization
       - Security Practices
       - Test Coverage
    3. Technical Assessment:
       - Technology Stack Review
       - Code Complexity Analysis
       - Best Practices Adherence
       - Risk Assessment
    4. Recommendations:
       - Key Improvements
       - Architecture Suggestions
       - Security Enhancements""",
    expected_output="Detailed code analysis report with metrics and recommendations",
    agent=code_analyzer,
    output_pydantic=CodeAnalysisReport
)

def analyze_code(code_source: str) -> CodeAnalysisReport:
    """
    Analyze code from directory path or GitHub URL
    """
    # Ingest code content
    summary, tree, content = ingest(code_source)
    
    # Concatenate context into structured format
    context_text = f"""
    CODE REPOSITORY ANALYSIS
    =======================
    
    SUMMARY
    -------
    {summary}
    
    REPOSITORY STRUCTURE
    -------------------
    {tree}
    
    SOURCE CODE
    -----------
    {content}
    """
    
    # Initialize and run analysis
    agents = PraisonAIAgents(
        agents=[code_analyzer],
        tasks=[code_analysis_task]
    )
    
    return agents.start(context_text)

if __name__ == "__main__":
    # Example usage
    code_source = "https://github.com/openai/openai-python/tree/main/src/openai/cli/_api/chat"  # GitHub URL or local directory
    result = analyze_code(code_source)
    print(result) 
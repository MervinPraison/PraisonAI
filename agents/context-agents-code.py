from praisonaiagents import Agent, Task, PraisonAIAgents
from pydantic import BaseModel
from typing import List, Dict

class SkillMetrics(BaseModel):
    name: str
    score: int
    comments: str

class CVAnalysisReport(BaseModel):
    overall_score: int
    skill_metrics: List[SkillMetrics]
    experience_score: int
    education_score: int
    presentation_score: int
    achievement_impact_score: int
    market_readiness: int
    key_strengths: List[str]
    areas_for_improvement: List[str]
    market_fit: str
    recommendations: List[str]
    technical_skills: List[Dict[str, int]]
    soft_skills: List[Dict[str, int]]
    skill_gaps: List[str]
    key_achievements: List[str]
    impact_metrics: List[Dict[str, str]]
    areas_of_expertise: List[str]

# Create single CV analysis agent
cv_analyzer = Agent(
    role="CV Analysis Expert",
    goal="Provide comprehensive CV evaluation and recommendations",
    backstory="""You are an expert CV analyst with deep knowledge of industry requirements, 
    market trends, and talent assessment. You excel at evaluating skills, experience, 
    and providing actionable recommendations.""",
    verbose=True
)

# Single comprehensive analysis task
cv_analysis_task = Task(
    description="""Perform a detailed CV analysis with scoring metrics and provide output in the following format:

    1. Overall Score (0-100):
       - Calculate based on weighted average of all metrics
    
    2. Individual Skill Metrics:
       - For each major skill found in CV:
         * Name of skill
         * Score (0-100)
         * Specific feedback/comments
    
    3. Core Metrics (0-100 each):
       - Experience Score: Based on relevance and years
       - Education Score: Based on relevance and level
       - Presentation Score: CV format, clarity, structure
       - Achievement Impact Score: Measurable results
       - Market Readiness: Current market fit
    
    4. Technical Skills:
       - List each skill with proficiency score (0-100)
       - Example: {"Python": 85, "AWS": 70}
    
    5. Soft Skills:
       - List each skill with proficiency score (0-100)
       - Example: {"Communication": 90, "Leadership": 75}
    
    6. Detailed Analysis:
       - Key Strengths: Top 3-5 standout points
       - Areas for Improvement: 3-5 specific points
       - Market Fit: Current industry alignment
       - Skill Gaps: Missing critical skills for target role
       - Key Achievements: Quantifiable accomplishments
       - Impact Metrics: {"metric": "value"}
       - Areas of Expertise: Primary domains of expertise
    
    7. Recommendations:
       - 3-5 actionable steps for improvement
       
    Provide clear justification for all scores and ensure feedback is specific and actionable.""",
    expected_output="Structured CV analysis report with detailed metrics and scoring justification",
    agent=cv_analyzer,
    output_pydantic=CVAnalysisReport
)

# Create and run the agent
agents = PraisonAIAgents(
    agents=[cv_analyzer],
    tasks=[cv_analysis_task]
)

# Read and pass CV content through start()
with open('cv.txt', 'r') as file:
    cv_content = file.read()

# Start the analysis by passing CV content
result = agents.start(cv_content)

print(result)
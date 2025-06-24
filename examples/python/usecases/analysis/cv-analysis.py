from praisonaiagents import Agent, Task, PraisonAIAgents
from pydantic import BaseModel
from typing import List, Dict

# Define structured output models
class SkillAnalysis(BaseModel):
    technical_skills: List[str]
    soft_skills: List[str]
    skill_gaps: List[str]
    recommendations: List[str]

class ExperienceAnalysis(BaseModel):
    key_achievements: List[str]
    impact_metrics: List[Dict[str, str]]
    areas_of_expertise: List[str]
    improvement_suggestions: List[str]

class CVAnalysisReport(BaseModel):
    overall_score: int
    key_strengths: List[str]
    areas_for_improvement: List[str]
    market_fit: str
    recommendations: List[str]
    skill_analysis: SkillAnalysis
    experience_analysis: ExperienceAnalysis

# Create specialized agents
skill_analyst = Agent(
    role="Skills Analysis Expert",
    goal="Analyze technical and soft skills in CV",
    backstory="""You are an experienced skills analyst with deep knowledge of industry requirements 
    and current market trends. You excel at identifying valuable skills and potential skill gaps.""",
    verbose=True
)

experience_analyst = Agent(
    role="Experience Analysis Expert",
    goal="Analyze professional experience and achievements",
    backstory="""You are an expert in evaluating professional experience and achievements. 
    You can identify impactful contributions and quantifiable results.""",
    verbose=True
)

cv_evaluator = Agent(
    role="Senior CV Evaluator",
    goal="Provide comprehensive CV evaluation and recommendations",
    backstory="""You are a senior CV evaluation expert with years of experience in talent assessment. 
    You provide detailed analysis and actionable recommendations for CV improvement.""",
    verbose=True
)

# Create tasks with structured outputs
skills_analysis_task = Task(
    description="""Analyze the CV's technical and soft skills. Identify skill gaps and provide recommendations 
    for skill development based on current market trends.""",
    expected_output="Detailed analysis of skills with recommendations",
    agent=skill_analyst,
    output_pydantic=SkillAnalysis,
    context=["test"],
)

experience_analysis_task = Task(
    description="""Evaluate professional experience, achievements, and impact. 
    Identify key accomplishments and areas of expertise.""",
    expected_output="Comprehensive analysis of professional experience",
    agent=experience_analyst,
    output_pydantic=ExperienceAnalysis
)

final_evaluation_task = Task(
    description="""Review all analyses and provide a comprehensive evaluation of the CV. 
    Include overall assessment, key strengths, areas for improvement, and specific recommendations.""",
    expected_output="Final CV evaluation report",
    agent=cv_evaluator,
    context=[skills_analysis_task, experience_analysis_task],
    output_pydantic=CVAnalysisReport
)

# Create and run the agents
agents = PraisonAIAgents(
    agents=[skill_analyst, experience_analyst, cv_evaluator],
    tasks=[skills_analysis_task, experience_analysis_task, final_evaluation_task],
    process="sequential",
    verbose=True
)

# Start the analysis
result = agents.start()

# Access the structured results
print("\nCV Analysis Results:")
print(f"\nOverall Score: {result.pydantic.overall_score}/100")
print("\nKey Strengths:")
for strength in result.pydantic.key_strengths:
    print(f"- {strength}")

print("\nSkill Analysis:")
print("\nTechnical Skills:")
for skill in result.pydantic.skill_analysis.technical_skills:
    print(f"- {skill}")

print("\nExperience Highlights:")
for achievement in result.pydantic.experience_analysis.key_achievements:
    print(f"- {achievement}")

print("\nRecommendations:")
for recommendation in result.pydantic.recommendations:
    print(f"- {recommendation}")

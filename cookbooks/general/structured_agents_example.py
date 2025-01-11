from praisonaiagents import Agent, Task, PraisonAIAgents, Tools
from pydantic import BaseModel

class AnalysisReport(BaseModel):
    title: str
    findings: str
    summary: str

# Create a researcher agent
researcher = Agent(
    name="AIResearcher",
    role="Technology Research Analyst",
    goal="Analyze and structure information about AI developments",
    backstory="Expert analyst specializing in AI technology trends",
    verbose=True,
    llm="gpt-4o-mini",
    tools=[Tools.internet_search],
    self_reflect=False
)

# Create an analyst agent
analyst = Agent(
    name="DataAnalyst",
    role="Data Insights Specialist",
    goal="Structure and analyze research findings",
    backstory="Senior data analyst with expertise in pattern recognition",
    verbose=True,
    llm="gpt-4o-mini",
    self_reflect=False
)

# Define structured tasks
research_task = Task(
    name="gather_research",
    description="Research recent AI developments in 2024",
    agent=researcher,
    expected_output="Research findings"
)

analysis_task = Task(
    name="analyze_findings",
    description="Analyze research findings and create structured report. No additional text or explanation.",
    agent=analyst,
    output_json=AnalysisReport,
    expected_output="JSON object"
)

# Initialize and run agents
agents = PraisonAIAgents(
    agents=[researcher, analyst],
    tasks=[research_task, analysis_task],
    process="sequential",
    verbose=True
)
result = agents.start()
print(result)
